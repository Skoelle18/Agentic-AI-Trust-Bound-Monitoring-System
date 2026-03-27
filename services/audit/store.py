from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id        TEXT UNIQUE NOT NULL,
  timestamp       TEXT NOT NULL,
  agent_id        TEXT,
  session_id      TEXT,
  event_type      TEXT NOT NULL,
  tool_name       TEXT,
  tool_args       TEXT,
  policy_result   TEXT,
  anomaly_scores  TEXT,
  reason          TEXT,
  prev_hash       TEXT NOT NULL,
  event_hash      TEXT NOT NULL,
  signature       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_tool ON events(tool_name);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  first_ts   TEXT NOT NULL,
  last_ts    TEXT NOT NULL,
  agent_id   TEXT
);

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'events table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'events table is append-only');
END;
"""


@dataclass
class AuditEventRow:
    event_id: str
    timestamp: str
    agent_id: Optional[str]
    session_id: Optional[str]
    event_type: str
    tool_name: Optional[str]
    tool_args: Optional[dict[str, Any]]
    policy_result: Optional[str]
    anomaly_scores: Optional[dict[str, Any]]
    reason: Optional[str]
    prev_hash: str
    event_hash: str
    signature: str


def _db_path() -> str:
    return os.getenv("AUDIT_DB_PATH", "/data/audit.db")


def connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT event_hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
    return str(row["event_hash"]) if row else "GENESIS"


def insert_event(conn: sqlite3.Connection, row: AuditEventRow) -> None:
    conn.execute(
        """
        INSERT INTO events (
          event_id, timestamp, agent_id, session_id, event_type, tool_name,
          tool_args, policy_result, anomaly_scores, reason,
          prev_hash, event_hash, signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.event_id,
            row.timestamp,
            row.agent_id,
            row.session_id,
            row.event_type,
            row.tool_name,
            json.dumps(row.tool_args, separators=(",", ":"), ensure_ascii=False) if row.tool_args is not None else None,
            row.policy_result,
            json.dumps(row.anomaly_scores, separators=(",", ":"), ensure_ascii=False)
            if row.anomaly_scores is not None
            else None,
            row.reason,
            row.prev_hash,
            row.event_hash,
            row.signature,
        ),
    )
    if row.session_id:
        existing = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (row.session_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE sessions SET last_ts = ?, agent_id = COALESCE(agent_id, ?) WHERE session_id = ?",
                (row.timestamp, row.agent_id, row.session_id),
            )
        else:
            conn.execute(
                "INSERT INTO sessions(session_id, first_ts, last_ts, agent_id) VALUES (?, ?, ?, ?)",
                (row.session_id, row.timestamp, row.timestamp, row.agent_id),
            )
    conn.commit()


def list_events(
    conn: sqlite3.Connection,
    *,
    limit: int,
    offset: int,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    tool_name: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
) -> list[sqlite3.Row]:
    where = []
    params: list[Any] = []
    if agent_id:
        where.append("agent_id = ?")
        params.append(agent_id)
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    if tool_name:
        where.append("tool_name = ?")
        params.append(tool_name)
    if from_ts:
        where.append("timestamp >= ?")
        params.append(from_ts)
    if to_ts:
        where.append("timestamp <= ?")
        params.append(to_ts)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    return conn.execute(
        f"SELECT * FROM events {clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()


def get_event(conn: sqlite3.Connection, event_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()


def list_sessions(conn: sqlite3.Connection, *, limit: int, offset: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT s.session_id, s.first_ts, s.last_ts, s.agent_id,
               (SELECT COUNT(1) FROM events e WHERE e.session_id = s.session_id) AS call_count,
               (SELECT COUNT(1) FROM events e WHERE e.session_id = s.session_id AND e.policy_result = 'BLOCK') AS block_count
        FROM sessions s
        ORDER BY s.last_ts DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def session_events(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
        (session_id,),
    ).fetchall()


def stats_last_24h(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT substr(timestamp, 1, 13) AS hour_bucket,
               event_type,
               COUNT(1) AS count
        FROM events
        WHERE timestamp >= datetime('now', '-24 hours')
        GROUP BY hour_bucket, event_type
        ORDER BY hour_bucket ASC
        """
    ).fetchall()

