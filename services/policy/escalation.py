from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> str:
    return os.getenv("POLICY_DB_PATH", "/data/policy.db")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS escalations (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  tool_args TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT,
  note TEXT,
  timeout_minutes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status);
CREATE INDEX IF NOT EXISTS idx_escalations_created ON escalations(created_at);
"""


class EscalationStore:
    def __init__(self) -> None:
        self.conn = connect()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def create(
        self,
        *,
        agent_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        reason: str,
        timeout_minutes: int = 15,
    ) -> str:
        eid = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO escalations(id, agent_id, tool_name, tool_args, reason, status, created_at, resolved_at, resolved_by, note, timeout_minutes)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?, NULL, NULL, NULL, ?)
            """,
            (eid, agent_id, tool_name, json.dumps(tool_args), reason, utc_now_iso(), timeout_minutes),
        )
        self.conn.commit()
        return eid

    def get(self, eid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM escalations WHERE id = ?", (eid,)).fetchone()

    def list(self, *, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute(
                "SELECT * FROM escalations WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM escalations ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

    def resolve(self, *, eid: str, status: str, resolved_by: str, note: Optional[str]) -> None:
        self.conn.execute(
            """
            UPDATE escalations
            SET status = ?, resolved_at = ?, resolved_by = ?, note = ?
            WHERE id = ?
            """,
            (status, utc_now_iso(), resolved_by, note, eid),
        )
        self.conn.commit()

    def expire_old(self) -> int:
        rows = self.conn.execute("SELECT id, created_at, timeout_minutes FROM escalations WHERE status = 'PENDING'").fetchall()
        expired = 0
        for r in rows:
            created = datetime.fromisoformat(r["created_at"])
            timeout = int(r["timeout_minutes"])
            if datetime.now(timezone.utc) > created + timedelta(minutes=timeout):
                self.resolve(eid=r["id"], status="EXPIRED", resolved_by="system", note="Timed out")
                expired += 1
        return expired

