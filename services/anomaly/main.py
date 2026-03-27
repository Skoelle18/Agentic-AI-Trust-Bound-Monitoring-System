from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from services.shared.problem import instance_from_request, problem_detail

from .baseline import BaselineStore, utc_now_iso
from .coherence import score_against_plan
from .drift import update_and_score
from .stac import check as stac_check
from .temporal import out_of_hours


def parse_ts(ts_iso: str) -> datetime:
    return datetime.fromisoformat(ts_iso).astimezone(timezone.utc)


app = FastAPI(title="ATBMS Anomaly Engine", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

audit_url = os.getenv("AUDIT_URL", "http://audit:8004")
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

http = httpx.AsyncClient(timeout=8.0)
store = BaselineStore()

# rolling state
velocity: dict[str, deque[datetime]] = defaultdict(lambda: deque(maxlen=2000))  # agent_id -> timestamps
session_window: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=10))  # session_id -> tool names
hourly_counts: dict[tuple[str, str, str], int] = defaultdict(int)  # (hour_bucket, agent_id, tool_name) -> count
latest_scores: dict[str, dict[str, Any]] = defaultdict(dict)  # agent_id -> module -> score payload


def insert_alert(*, agent_id: Optional[str], session_id: Optional[str], module: str, alert_type: str, score: float, detail: str) -> str:
    aid = str(uuid.uuid4())
    store.conn.execute(
        """
        INSERT INTO anomaly_events(id, timestamp, agent_id, session_id, module, alert_type, score, detail, dismissed, dismissed_at, dismissed_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL)
        """,
        (aid, utc_now_iso(), agent_id, session_id, module, alert_type, float(score), detail),
    )
    store.conn.commit()
    return aid


async def poll_loop() -> None:
    last_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat()
    while True:
        try:
            events = (await http.get(f"{audit_url}/events", params={"from_ts": last_ts, "limit": 500})).json()
            # audit returns DESC; process ASC for temporal windows
            if isinstance(events, list):
                events = list(reversed(events))
            for e in events or []:
                ts = e.get("timestamp")
                if ts:
                    last_ts = ts
                if e.get("event_type") != "TOOL_CALL":
                    continue
                agent_id = e.get("agent_id") or "unknown"
                session_id = e.get("session_id") or "unknown"
                tool = e.get("tool_name") or "unknown"

                # velocity spike: >10 calls in last 60 seconds
                t = parse_ts(ts)
                dq = velocity[agent_id]
                dq.append(t)
                cutoff = t - timedelta(seconds=60)
                while dq and dq[0] < cutoff:
                    dq.popleft()
                if len(dq) > 10:
                    insert_alert(
                        agent_id=agent_id,
                        session_id=session_id,
                        module="temporal",
                        alert_type="velocity_spike",
                        score=min(100.0, 40.0 + (len(dq) - 10) * 5.0),
                        detail=f"{len(dq)} calls in last 60s",
                    )

                # out of hours
                toh = out_of_hours(ts)
                if toh.triggered:
                    insert_alert(agent_id=agent_id, session_id=session_id, module="temporal", alert_type="out_of_hours", score=55.0, detail=toh.detail)

                # hourly baseline drift
                hour_bucket = ts[:13]
                hourly_counts[(hour_bucket, agent_id, tool)] += 1
                count = hourly_counts[(hour_bucket, agent_id, tool)]
                _, drift_res = update_and_score(store=store, agent_id=agent_id, tool_name=tool, current_hourly_count=count)
                if drift_res.triggered:
                    insert_alert(agent_id=agent_id, session_id=session_id, module="drift", alert_type="DRIFT_ALERT", score=min(100.0, abs(drift_res.z) * 15.0), detail=drift_res.detail)

                # STAC
                sw = session_window[session_id]
                sw.append(tool)
                st = stac_check(list(sw))
                if st.triggered:
                    insert_alert(
                        agent_id=agent_id,
                        session_id=session_id,
                        module="stac",
                        alert_type="STAC_ALERT",
                        score=min(100.0, 70.0 + st.confidence * 30.0),
                        detail=f"{st.detail}: {' -> '.join(st.matched or [])}",
                    )

                # Plan coherence heuristic (reads approved plan tools list from event if present)
                approved_tools = set((e.get("anomaly_scores") or {}).get("approved_plan_tools") or [])
                coh = score_against_plan(approved_plan_tools=approved_tools, tool_name=tool, args=e.get("tool_args") or {})
                if not coh.coherent and coh.score < 0.4:
                    insert_alert(agent_id=agent_id, session_id=session_id, module="coherence", alert_type="COHERENCE_ALERT", score=100.0 * (1.0 - coh.score), detail=coh.reason)

                latest_scores[agent_id]["temporal"] = {"score": min(100.0, len(dq) * 4.0), "updated_at": utc_now_iso()}
                latest_scores[agent_id]["stac"] = {"score": 95.0 if st.triggered else 5.0, "updated_at": utc_now_iso()}
                latest_scores[agent_id]["drift"] = {"score": min(100.0, abs(drift_res.z) * 10.0), "updated_at": utc_now_iso()}
                latest_scores[agent_id]["coherence"] = {"score": 100.0 * (1.0 - coh.score), "updated_at": utc_now_iso()}
        except Exception:
            pass
        await asyncio.sleep(5)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(poll_loop())


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/scores/{agent_id}")
def scores(agent_id: str) -> dict[str, Any]:
    return {"agent_id": agent_id, "modules": latest_scores.get(agent_id, {})}


@app.get("/scores/{agent_id}/history")
def scores_history(agent_id: str) -> dict[str, Any]:
    # prototype: history can be derived from anomaly_events; for demo we keep light
    rows = store.conn.execute(
        "SELECT timestamp, module, score FROM anomaly_events WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 500",
        (agent_id,),
    ).fetchall()
    return {"agent_id": agent_id, "points": [{"timestamp": r["timestamp"], "module": r["module"], "score": float(r["score"])} for r in rows]}


@app.get("/alerts")
def alerts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    dismissed: Optional[bool] = None,
) -> Any:
    try:
        where = ""
        params: list[Any] = []
        if dismissed is True:
            where = "WHERE dismissed = 1"
        elif dismissed is False:
            where = "WHERE dismissed = 0"
        rows = store.conn.execute(
            f"SELECT * FROM anomaly_events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "agent_id": r["agent_id"],
                "session_id": r["session_id"],
                "module": r["module"],
                "alert_type": r["alert_type"],
                "score": float(r["score"]),
                "detail": r["detail"],
                "dismissed": bool(r["dismissed"]),
                "dismissed_at": r["dismissed_at"],
                "dismissed_by": r["dismissed_by"],
            }
            for r in rows
        ]
    except Exception as e:
        return problem_detail(status=500, title="Alerts query failed", detail=str(e), instance=instance_from_request(request))


@app.get("/alerts/{alert_id}")
def alert_detail(alert_id: str, request: Request) -> Any:
    row = store.conn.execute("SELECT * FROM anomaly_events WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Alert not found", instance=instance_from_request(request))
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "agent_id": row["agent_id"],
        "session_id": row["session_id"],
        "module": row["module"],
        "alert_type": row["alert_type"],
        "score": float(row["score"]),
        "detail": row["detail"],
        "dismissed": bool(row["dismissed"]),
        "dismissed_at": row["dismissed_at"],
        "dismissed_by": row["dismissed_by"],
    }


@app.post("/alerts/{alert_id}/dismiss")
def dismiss(alert_id: str, request: Request, body: dict[str, Any] | None = None) -> Any:
    try:
        store.conn.execute(
            "UPDATE anomaly_events SET dismissed = 1, dismissed_at = ?, dismissed_by = ? WHERE id = ?",
            (utc_now_iso(), (body or {}).get("dismissed_by", "admin@example.com"), alert_id),
        )
        store.conn.commit()
        return {"ok": True}
    except Exception as e:
        return problem_detail(status=500, title="Dismiss failed", detail=str(e), instance=instance_from_request(request))


@app.get("/baselines")
def baselines() -> Any:
    rows = store.list_all()
    return [
        {
            "agent_id": r["agent_id"],
            "tool_name": r["tool_name"],
            "mean_hourly": float(r["mean_hourly"]),
            "stddev_hourly": float(r["stddev_hourly"]),
            "sample_count": int(r["sample_count"]),
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


@app.get("/baselines/{agent_id}")
def baselines_agent(agent_id: str) -> Any:
    rows = store.list_agent(agent_id)
    return [
        {
            "agent_id": r["agent_id"],
            "tool_name": r["tool_name"],
            "mean_hourly": float(r["mean_hourly"]),
            "stddev_hourly": float(r["stddev_hourly"]),
            "sample_count": int(r["sample_count"]),
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


@app.delete("/baselines/{agent_id}")
def baselines_reset(agent_id: str) -> dict[str, Any]:
    deleted = store.delete_agent(agent_id)
    return {"ok": True, "deleted": deleted}


@app.get("/demo")
async def demo() -> dict[str, Any]:
    # best-effort: kick the audit demo so there are events to detect
    try:
        await http.get(f"{audit_url}/demo")
    except Exception:
        pass
    return {"ok": True}

