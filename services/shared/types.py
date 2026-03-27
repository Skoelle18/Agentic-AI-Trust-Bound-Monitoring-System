from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


EventType = Literal[
    "TOOL_CALL",
    "POLICY_BLOCK",
    "ANOMALY_FLAG",
    "AUTH_EVENT",
    "RESPONSE_FLAGGED",
    "POLICY_DECISION",
    "ESCALATION",
]

PolicyResult = Literal["ALLOW", "BLOCK", "REQUIRE_APPROVAL", "UNKNOWN"]


class AuditEventIn(BaseModel):
    timestamp: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    event_type: EventType
    tool_name: Optional[str] = None
    tool_args: Optional[dict[str, Any]] = None
    policy_result: Optional[PolicyResult] = None
    anomaly_scores: Optional[dict[str, Any]] = None
    reason: Optional[str] = None


class AuditEvent(AuditEventIn):
    event_id: str
    prev_hash: str
    event_hash: str
    signature: str


class EvaluateRequest(BaseModel):
    agent_id: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    agent_tags: list[str] = Field(default_factory=list)
    tool_manifest: list[str] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    effect: PolicyResult
    reason: str
    rule_id: str


class ProxyStats(BaseModel):
    window: Literal["1h", "24h", "7d"]
    total: int
    allowed: int
    blocked: int
    flagged: int

