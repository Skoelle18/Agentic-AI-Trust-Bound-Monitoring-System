from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .chain import compute_event_hash


def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
    tool_args = json.loads(row["tool_args"]) if row["tool_args"] else None
    anomaly_scores = json.loads(row["anomaly_scores"]) if row["anomaly_scores"] else None
    return {
        "event_id": row["event_id"],
        "timestamp": row["timestamp"],
        "agent_id": row["agent_id"],
        "session_id": row["session_id"],
        "event_type": row["event_type"],
        "tool_name": row["tool_name"],
        "tool_args": tool_args,
        "policy_result": row["policy_result"],
        "anomaly_scores": anomaly_scores,
        "reason": row["reason"],
    }


def verify_chain(conn: sqlite3.Connection, session_id: Optional[str] = None) -> dict[str, Any]:
    where = "WHERE session_id = ?" if session_id else ""
    params = (session_id,) if session_id else ()
    rows = conn.execute(
        f"SELECT * FROM events {where} ORDER BY id ASC",
        params,
    ).fetchall()
    prev = "GENESIS"
    for idx, row in enumerate(rows, start=1):
        payload = _row_payload(row)
        expected = compute_event_hash(prev, payload)
        if row["prev_hash"] != prev or row["event_hash"] != expected:
            return {"valid": False, "total_events": len(rows), "first_broken_at": idx}
        prev = row["event_hash"]
    return {"valid": True, "total_events": len(rows), "first_broken_at": None}

