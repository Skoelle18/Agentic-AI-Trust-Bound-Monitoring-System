from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class OPAResult:
    effect: str
    reason: str
    rule_id: str


class OPAEngine:
    def __init__(self) -> None:
        self.opa_url = os.getenv("OPA_URL", "http://localhost:8181")
        self.policy_path = os.getenv("OPA_POLICY_PATH", "/config/policies")
        self._proc: Optional[subprocess.Popen[bytes]] = None
        self.http = httpx.AsyncClient(timeout=5.0)

    def start_if_needed(self) -> None:
        """
        Best-effort: if OPA_URL points to localhost and `opa` exists, spawn it.
        In Docker Compose we typically run a dedicated OPA container and set OPA_URL,
        so this becomes a no-op.
        """
        if os.getenv("OPA_EXTERNAL", "").lower() == "true":
            return
        if "localhost" not in self.opa_url and "127.0.0.1" not in self.opa_url:
            return
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                ["opa", "run", "--server", "--addr", ":8181", self.policy_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._proc = None

    async def evaluate(self, input_: dict[str, Any]) -> OPAResult:
        self.start_if_needed()
        try:
            r = await self.http.post(f"{self.opa_url}/v1/data/atbms", json={"input": input_})
            r.raise_for_status()
            data = r.json().get("result") or {}
            effect = data.get("effect") or ("ALLOW" if data.get("allow") else "BLOCK")
            return OPAResult(effect=effect, reason=data.get("reason") or "", rule_id=data.get("rule_id") or "")
        except Exception:
            # degraded allow to keep system moving
            return OPAResult(effect="ALLOW", reason="OPA unavailable (degraded allow)", rule_id="opa_degraded_allow")

