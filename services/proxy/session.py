from __future__ import annotations

import json
from typing import Any, Optional

import redis


class SessionStore:
    def __init__(self, r: redis.Redis, *, ttl_seconds: int = 4 * 3600) -> None:
        self.r = r
        self.ttl = ttl_seconds

    def get(self, session_id: str) -> Optional[dict[str, Any]]:
        raw = self.r.get(f"session:{session_id}")
        return json.loads(raw) if raw else None

    def upsert(self, session_id: str, session: dict[str, Any]) -> None:
        self.r.setex(f"session:{session_id}", self.ttl, json.dumps(session, separators=(",", ":"), ensure_ascii=False))

