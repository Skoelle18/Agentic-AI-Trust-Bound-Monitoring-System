from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


AgentStatus = Literal["ACTIVE", "SUSPENDED", "PENDING_REVIEW"]


class AgentCreate(BaseModel):
    display_name: str
    model: str
    system_prompt: str
    tool_manifest: list[str] = Field(default_factory=list)
    owner: str
    tags: list[str] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    display_name: Optional[str] = None
    model: Optional[str] = None
    tool_manifest: Optional[list[str]] = None
    owner: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[AgentStatus] = None


class AgentOut(BaseModel):
    agent_id: str
    display_name: str
    model: str
    system_prompt_hash: str
    tool_manifest: list[str]
    owner: str
    tags: list[str]
    status: AgentStatus
    last_attested: Optional[str] = None
    created_at: str


class AttestRequest(BaseModel):
    system_prompt_hash: str
    tool_manifest: list[str]


class AttestResponse(BaseModel):
    token: str
    expires_at: str


class BlastRadiusGraph(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]

