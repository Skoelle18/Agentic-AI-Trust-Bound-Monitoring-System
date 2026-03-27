from __future__ import annotations

import os
from typing import Any


def discover_agents_from_env() -> list[dict[str, Any]]:
    """
    Optional bootstrap mechanism:
    ATBMS_BOOTSTRAP_AGENTS='[{"display_name":"...","model":"...","owner":"...","tags":["..."],"tool_manifest":["..."],"system_prompt":"..."}]'
    """
    raw = os.getenv("ATBMS_BOOTSTRAP_AGENTS")
    if not raw:
        return []
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []

