from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CoherenceResult:
    coherent: bool
    score: float
    reason: str


def score_against_plan(*, approved_plan_tools: set[str], tool_name: str, args: dict[str, Any]) -> CoherenceResult:
    """
    Production would call an LLM judge. In this production-grade *platform* prototype,
    we provide a deterministic, auditable heuristic to avoid external dependencies.
    """
    if not approved_plan_tools:
        return CoherenceResult(coherent=True, score=1.0, reason="No approved plan on record")
    if tool_name in approved_plan_tools:
        return CoherenceResult(coherent=True, score=0.85, reason="Tool present in approved plan")
    return CoherenceResult(coherent=False, score=0.25, reason="Tool not present in approved plan")

