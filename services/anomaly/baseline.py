from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> str:
    return os.getenv("ANOMALY_DB_PATH", "/data/anomaly.db")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines(
  agent_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  mean_hourly REAL NOT NULL,
  stddev_hourly REAL NOT NULL,
  sample_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(agent_id, tool_name)
);

CREATE TABLE IF NOT EXISTS anomaly_events(
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  agent_id TEXT,
  session_id TEXT,
  module TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  score REAL NOT NULL,
  detail TEXT NOT NULL,
  dismissed INTEGER NOT NULL DEFAULT 0,
  dismissed_at TEXT,
  dismissed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_dismissed ON anomaly_events(dismissed);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON anomaly_events(timestamp);
"""


@dataclass
class Baseline:
    agent_id: str
    tool_name: str
    mean_hourly: float
    stddev_hourly: float
    sample_count: int
    updated_at: str


class BaselineStore:
    def __init__(self) -> None:
        self.conn = connect()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def get(self, agent_id: str, tool_name: str) -> Optional[Baseline]:
        row = self.conn.execute(
            "SELECT * FROM baselines WHERE agent_id = ? AND tool_name = ?",
            (agent_id, tool_name),
        ).fetchone()
        if not row:
            return None
        return Baseline(
            agent_id=row["agent_id"],
            tool_name=row["tool_name"],
            mean_hourly=float(row["mean_hourly"]),
            stddev_hourly=float(row["stddev_hourly"]),
            sample_count=int(row["sample_count"]),
            updated_at=row["updated_at"],
        )

    def upsert(self, b: Baseline) -> None:
        self.conn.execute(
            """
            INSERT INTO baselines(agent_id, tool_name, mean_hourly, stddev_hourly, sample_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, tool_name)
            DO UPDATE SET mean_hourly=excluded.mean_hourly, stddev_hourly=excluded.stddev_hourly,
                         sample_count=excluded.sample_count, updated_at=excluded.updated_at
            """,
            (b.agent_id, b.tool_name, b.mean_hourly, b.stddev_hourly, b.sample_count, b.updated_at),
        )
        self.conn.commit()

    def list_all(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM baselines ORDER BY updated_at DESC").fetchall()

    def list_agent(self, agent_id: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM baselines WHERE agent_id = ? ORDER BY updated_at DESC", (agent_id,)).fetchall()

    def delete_agent(self, agent_id: str) -> int:
        cur = self.conn.execute("DELETE FROM baselines WHERE agent_id = ?", (agent_id,))
        self.conn.commit()
        return int(cur.rowcount)

