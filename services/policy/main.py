from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
import redis
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from services.shared.problem import instance_from_request, problem_detail
from services.shared.types import EvaluateRequest, EvaluateResponse

from .engine import OPAEngine
from .escalation import EscalationStore
from .plan_validator import plan_hash


def _policies_file() -> str:
    return os.getenv("POLICY_FILE", "/config/policies/main.rego")


app = FastAPI(title="ATBMS Policy Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

opa = OPAEngine()
escalations = EscalationStore()
r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
http = httpx.AsyncClient(timeout=5.0)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.post("/evaluate")
async def evaluate(body: EvaluateRequest, request: Request) -> Any:
    try:
        escalations.expire_old()
        res = await opa.evaluate(body.model_dump())
        if res.effect == "REQUIRE_APPROVAL":
            eid = escalations.create(
                agent_id=body.agent_id,
                tool_name=body.tool_name,
                tool_args=body.args,
                reason=res.reason or "Approval required",
                timeout_minutes=int(os.getenv("ESCALATION_TIMEOUT_MINUTES", "15")),
            )
            return {"effect": "REQUIRE_APPROVAL", "reason": res.reason, "rule_id": res.rule_id, "approval_id": eid}
        if res.effect == "BLOCK":
            return EvaluateResponse(effect="BLOCK", reason=res.reason or "Blocked", rule_id=res.rule_id or "block").model_dump()
        return EvaluateResponse(effect="ALLOW", reason=res.reason or "Allowed", rule_id=res.rule_id or "allow").model_dump()
    except Exception as e:
        return problem_detail(status=500, title="Evaluation failed", detail=str(e), instance=instance_from_request(request))


@app.post("/plan/validate")
async def validate_plan(request: Request, body: dict[str, Any]) -> Any:
    """
    Body: { agent_id, plan: [{tool, args, reason}] }
    """
    try:
        agent_id = body.get("agent_id")
        plan = body.get("plan") or []
        approved_steps = []
        blocked_steps = []
        for step in plan:
            tool = step.get("tool")
            args = step.get("args") or {}
            req = {"agent_id": agent_id, "tool_name": tool, "args": args, "agent_tags": body.get("agent_tags", []), "tool_manifest": body.get("tool_manifest", [])}
            res = await opa.evaluate(req)
            if res.effect == "BLOCK":
                blocked_steps.append({**step, "reason": res.reason})
            else:
                approved_steps.append(step)
        approved = len(blocked_steps) == 0
        if approved:
            h = plan_hash(approved_steps)
            r.setex(f"approved_plan:{agent_id}", 4 * 3600, h)
        return {"approved": approved, "approved_steps": approved_steps, "blocked_steps": blocked_steps}
    except Exception as e:
        return problem_detail(status=500, title="Plan validation failed", detail=str(e), instance=instance_from_request(request))


@app.get("/escalations")
def list_escalations(
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    try:
        escalations.expire_old()
        rows = escalations.list(status=status, limit=limit, offset=offset)
        out = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "agent_id": row["agent_id"],
                    "tool_name": row["tool_name"],
                    "tool_args": json.loads(row["tool_args"]),
                    "reason": row["reason"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "resolved_at": row["resolved_at"],
                    "resolved_by": row["resolved_by"],
                    "note": row["note"],
                    "timeout_minutes": int(row["timeout_minutes"]),
                }
            )
        return out
    except Exception as e:
        return problem_detail(status=500, title="Escalations query failed", detail=str(e), instance=instance_from_request(request))


@app.get("/escalations/{eid}")
def get_escalation(eid: str, request: Request) -> Any:
    row = escalations.get(eid)
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Escalation not found", instance=instance_from_request(request))
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "tool_name": row["tool_name"],
        "tool_args": json.loads(row["tool_args"]),
        "reason": row["reason"],
        "status": row["status"],
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
        "note": row["note"],
        "timeout_minutes": int(row["timeout_minutes"]),
    }


@app.post("/escalations/{eid}/approve")
def approve(eid: str, request: Request, body: dict[str, Any] | None = None) -> Any:
    row = escalations.get(eid)
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Escalation not found", instance=instance_from_request(request))
    if row["status"] != "PENDING":
        return problem_detail(status=409, title="Conflict", detail="Escalation not pending", instance=instance_from_request(request))
    note = (body or {}).get("note")
    escalations.resolve(eid=eid, status="APPROVED", resolved_by=(body or {}).get("resolved_by", "admin@example.com"), note=note)
    return {"ok": True}


@app.post("/escalations/{eid}/deny")
def deny(eid: str, request: Request, body: dict[str, Any] | None = None) -> Any:
    row = escalations.get(eid)
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Escalation not found", instance=instance_from_request(request))
    if row["status"] != "PENDING":
        return problem_detail(status=409, title="Conflict", detail="Escalation not pending", instance=instance_from_request(request))
    reason = (body or {}).get("reason")
    if not reason:
        return problem_detail(status=400, title="Bad Request", detail="Deny requires reason", instance=instance_from_request(request))
    escalations.resolve(eid=eid, status="DENIED", resolved_by=(body or {}).get("resolved_by", "admin@example.com"), note=reason)
    return {"ok": True}


@app.get("/policies")
def get_policies(request: Request) -> Any:
    try:
        with open(_policies_file(), "r", encoding="utf-8") as f:
            return {"rego": f.read()}
    except Exception as e:
        return problem_detail(status=500, title="Read policy failed", detail=str(e), instance=instance_from_request(request))


@app.put("/policies")
async def put_policies(request: Request, body: dict[str, Any]) -> Any:
    rego = body.get("rego")
    if not isinstance(rego, str) or not rego.strip():
        return problem_detail(status=400, title="Bad Request", detail="Missing rego text", instance=instance_from_request(request))
    try:
        os.makedirs(os.path.dirname(_policies_file()), exist_ok=True)
        with open(_policies_file(), "w", encoding="utf-8") as f:
            f.write(rego)
        # Best-effort hot reload: upload policy to OPA API if reachable.
        try:
            await http.put(f"{opa.opa_url}/v1/policies/atbms", content=rego.encode("utf-8"), headers={"Content-Type": "text/plain"})
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        return problem_detail(status=500, title="Update policy failed", detail=str(e), instance=instance_from_request(request))


@app.get("/demo")
def demo(request: Request) -> Any:
    try:
        # create a couple pending escalations
        for _ in range(3):
            escalations.create(agent_id="demo-agent-1", tool_name="http_request", tool_args={"url": "https://evil.example.com"}, reason="Demo escalation")
        return {"ok": True}
    except Exception as e:
        return problem_detail(status=500, title="Demo failed", detail=str(e), instance=instance_from_request(request))

