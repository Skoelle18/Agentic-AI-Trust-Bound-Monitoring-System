from __future__ import annotations

import hashlib
import json
from typing import Any


def plan_hash(plan: list[dict[str, Any]]) -> str:
    blob = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

