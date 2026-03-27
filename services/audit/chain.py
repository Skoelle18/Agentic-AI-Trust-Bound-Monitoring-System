from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_event_hash(prev_hash: str, event_payload: dict[str, Any]) -> str:
    blob = (prev_hash + canonical_json(event_payload)).encode("utf-8")
    return sha256_hex(blob)

