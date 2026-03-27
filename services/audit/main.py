from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from services.shared.problem import instance_from_request, problem_detail
from services.shared.types import AuditEvent, AuditEventIn

from .chain import compute_event_hash
from .signer import Keypair, load_or_generate, verify_signature, sign_event_hash
from .store import (
    AuditEventRow,
    connect,
    get_event,
    get_last_hash,
    init_db,
    insert_event,
    list_events,
    list_sessions,
    session_events,
    stats_last_24h,
)
from .verifier import verify_chain


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


app = FastAPI(title="ATBMS Audit Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_conn = connect()
init_db(_conn)
_keys: Keypair = load_or_generate()


def _row_to_event(row: Any) -> AuditEvent:
    return AuditEvent(
        event_id=row["event_id"],
        timestamp=row["timestamp"],
        agent_id=row["agent_id"],
        session_id=row["session_id"],
        event_type=row["event_type"],
        tool_name=row["tool_name"],
        tool_args=json.loads(row["tool_args"]) if row["tool_args"] else None,
        policy_result=row["policy_result"],
        anomaly_scores=json.loads(row["anomaly_scores"]) if row["anomaly_scores"] else None,
        reason=row["reason"],
        prev_hash=row["prev_hash"],
        event_hash=row["event_hash"],
        signature=row["signature"],
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.post("/events", response_model=AuditEvent)
def write_event(body: AuditEventIn, request: Request) -> Any:
    try:
        event_id = str(uuid.uuid4())
        prev = get_last_hash(_conn)
        payload = body.model_dump()
        payload["event_id"] = event_id
        event_hash = compute_event_hash(prev, payload)
        signature = sign_event_hash(_keys.private_key, event_hash)

        row = AuditEventRow(
            event_id=event_id,
            timestamp=body.timestamp,
            agent_id=body.agent_id,
            session_id=body.session_id,
            event_type=body.event_type,
            tool_name=body.tool_name,
            tool_args=body.tool_args,
            policy_result=body.policy_result,
            anomaly_scores=body.anomaly_scores,
            reason=body.reason,
            prev_hash=prev,
            event_hash=event_hash,
            signature=signature,
        )
        insert_event(_conn, row)
        return _row_to_event(get_event(_conn, event_id))
    except Exception as e:
        return problem_detail(
            status=500,
            title="Audit write failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/events", response_model=list[AuditEvent])
def get_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    tool_name: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
) -> Any:
    try:
        rows = list_events(
            _conn,
            limit=limit,
            offset=offset,
            agent_id=agent_id,
            session_id=session_id,
            event_type=event_type,
            tool_name=tool_name,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        return [_row_to_event(r) for r in rows]
    except Exception as e:
        return problem_detail(
            status=500,
            title="Audit query failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/events/{event_id}", response_model=AuditEvent)
def get_event_by_id(event_id: str, request: Request) -> Any:
    row = get_event(_conn, event_id)
    if not row:
        return problem_detail(
            status=404,
            title="Not Found",
            detail=f"Event {event_id} not found",
            instance=instance_from_request(request),
        )
    return _row_to_event(row)


@app.get("/sessions")
def sessions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    try:
        rows = list_sessions(_conn, limit=limit, offset=offset)
        return [
            {
                "session_id": r["session_id"],
                "first_ts": r["first_ts"],
                "last_ts": r["last_ts"],
                "agent_id": r["agent_id"],
                "call_count": int(r["call_count"]),
                "block_count": int(r["block_count"]),
            }
            for r in rows
        ]
    except Exception as e:
        return problem_detail(
            status=500,
            title="Sessions query failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/sessions/{session_id}", response_model=list[AuditEvent])
def session_detail(session_id: str, request: Request) -> Any:
    try:
        rows = session_events(_conn, session_id)
        return [_row_to_event(r) for r in rows]
    except Exception as e:
        return problem_detail(
            status=500,
            title="Session query failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/verify")
def verify(request: Request, session_id: Optional[str] = None) -> Any:
    try:
        return verify_chain(_conn, session_id=session_id)
    except Exception as e:
        return problem_detail(
            status=500,
            title="Verification failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/stats")
def stats(request: Request) -> Any:
    try:
        rows = stats_last_24h(_conn)
        return [{"hour": r["hour_bucket"], "event_type": r["event_type"], "count": int(r["count"])} for r in rows]
    except Exception as e:
        return problem_detail(
            status=500,
            title="Stats failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/public-key")
def public_key_pem() -> dict[str, str]:
    pub_path = os.path.join(os.getenv("KEY_DIR", "/config/keys"), "public.pem")
    with open(pub_path, "r", encoding="utf-8") as f:
        return {"public_key_pem": f.read()}


@app.get("/signature/verify")
def verify_sig(event_id: str, request: Request) -> Any:
    row = get_event(_conn, event_id)
    if not row:
        return problem_detail(
            status=404,
            title="Not Found",
            detail=f"Event {event_id} not found",
            instance=instance_from_request(request),
        )
    ok = verify_signature(_keys.public_key, row["event_hash"], row["signature"])
    return {"event_id": event_id, "verified": ok}


@app.get("/demo")
def demo(request: Request) -> Any:
    """
    Populate the audit log with realistic-looking events.
    This is safe to call multiple times; it appends new events.
    """
    try:
        agent_ids = [
            "demo-agent-1",
            "demo-agent-2",
        ]
        sessions = [str(uuid.uuid4()) for _ in range(3)]
        tools = ["read_file", "web_search", "list_directory", "http_request", "bash_exec"]
        event_types = ["TOOL_CALL", "POLICY_DECISION", "RESPONSE_FLAGGED", "AUTH_EVENT", "ANOMALY_FLAG"]

        for _ in range(30):
            agent_id = random.choice(agent_ids)
            session_id = random.choice(sessions)
            tool = random.choice(tools)
            policy = random.choice(["ALLOW", "ALLOW", "ALLOW", "BLOCK", "REQUIRE_APPROVAL"])
            et = random.choice(event_types)
            reason = None
            if policy == "BLOCK":
                et = "POLICY_BLOCK"
                reason = "Blocked by policy"
            elif policy == "REQUIRE_APPROVAL":
                et = "ESCALATION"
                reason = "Requires human approval"
            elif et == "RESPONSE_FLAGGED":
                reason = "Potential prompt injection detected"

            body = AuditEventIn(
                timestamp=utc_now_iso(),
                agent_id=agent_id,
                session_id=session_id,
                event_type=et,  # type: ignore[arg-type]
                tool_name=tool,
                tool_args={"path": "/workspace/README.md"} if tool == "read_file" else {"url": "https://evil.example.com"},
                policy_result=policy,  # type: ignore[arg-type]
                anomaly_scores={"stac": random.randint(0, 100)} if et == "ANOMALY_FLAG" else None,
                reason=reason,
            )
            write_event(body, request)

        return {"ok": True, "appended": 30}
    except Exception as e:
        return problem_detail(
            status=500,
            title="Demo failed",
            detail=str(e),
            instance=instance_from_request(request),
        )

