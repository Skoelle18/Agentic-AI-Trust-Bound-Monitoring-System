from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import jwt
import redis
import yaml
from jwt import PyJWKClient

from services.shared.types import EvaluateRequest

from .injection import scan, strip_injection
from .rate_limiter import SlidingWindowRateLimiter
from .session import SessionStore


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Decision:
    effect: str
    reason: str
    rule_id: str
    approval_id: Optional[str] = None


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)


class ProxyCore:
    def __init__(self) -> None:
        self.registry_url = os.getenv("REGISTRY_URL", "http://registry:8001")
        self.policy_url = os.getenv("POLICY_URL", "http://policy:8002")
        self.audit_url = os.getenv("AUDIT_URL", "http://audit:8004")
        self.upstream_mcp = os.getenv("UPSTREAM_MCP_URL", "http://example-mcp:9999/mcp")
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.prototype_mode = os.getenv("PROTOTYPE_MODE", "true").lower() == "true"

        self.http = httpx.AsyncClient(timeout=10.0)
        self.redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        self.ratelimiter = SlidingWindowRateLimiter(self.redis, max_calls=30, window_seconds=60)
        self.sessions = SessionStore(self.redis, ttl_seconds=4 * 3600)

        self.event_bus = EventBus()
        self.stats_events: deque[tuple[float, str]] = deque()  # (ts, kind)

        self.allowlist = self._load_allowlist()
        self.jwk_client = PyJWKClient(f"{self.registry_url}/jwks.json")

    def _load_allowlist(self) -> dict[str, Any]:
        path = os.getenv("ALLOWLIST_PATH", "/config/allowlist.yaml")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {"tools": []}

    def _tool_injection_action(self, tool_name: Optional[str]) -> str:
        if not tool_name:
            return "WARN"
        for t in self.allowlist.get("tools", []):
            if t.get("name") == tool_name:
                return str(t.get("injection_action", "WARN")).upper()
        return "WARN"

    def _stats_record(self, kind: str) -> None:
        now = time.time()
        self.stats_events.append((now, kind))
        cutoff = now - 7 * 24 * 3600
        while self.stats_events and self.stats_events[0][0] < cutoff:
            self.stats_events.popleft()

    def proxy_stats(self) -> dict[str, Any]:
        now = time.time()

        def window(seconds: int) -> dict[str, int]:
            total = allowed = blocked = flagged = 0
            for ts, kind in self.stats_events:
                if ts < now - seconds:
                    continue
                total += 1
                if kind == "allowed":
                    allowed += 1
                elif kind == "blocked":
                    blocked += 1
                elif kind == "flagged":
                    flagged += 1
            return {"total": total, "allowed": allowed, "blocked": blocked, "flagged": flagged}

        return {
            "1h": window(3600),
            "24h": window(24 * 3600),
            "7d": window(7 * 24 * 3600),
        }

    def verify_jwt(self, token: str) -> dict[str, Any]:
        signing_key = self.jwk_client.get_signing_key_from_jwt(token).key
        return jwt.decode(token, signing_key, algorithms=["RS256"], options={"require": ["exp", "iat"]})

    async def evaluate_policy(self, *, agent_id: str, tool_name: str, args: dict[str, Any], claims: dict[str, Any]) -> Decision:
        req = EvaluateRequest(
            agent_id=agent_id,
            tool_name=tool_name,
            args=args,
            agent_tags=claims.get("tags", []) or [],
            tool_manifest=claims.get("tool_manifest", []) or [],
        ).model_dump()
        try:
            r = await self.http.post(f"{self.policy_url}/evaluate", json=req)
            if r.status_code >= 500:
                raise RuntimeError(f"policy {r.status_code}")
            data = r.json()
            return Decision(
                effect=data.get("effect", "UNKNOWN"),
                reason=data.get("reason", ""),
                rule_id=data.get("rule_id", ""),
                approval_id=data.get("approval_id"),
            )
        except Exception:
            return Decision(effect="ALLOW", reason="Policy service unavailable (graceful allow)", rule_id="degraded_allow")

    async def write_audit(self, event: dict[str, Any]) -> None:
        try:
            await self.http.post(f"{self.audit_url}/events", json=event)
        except Exception:
            pass

    def _mk_audit_event(
        self,
        *,
        event_type: str,
        agent_id: Optional[str],
        session_id: Optional[str],
        tool_name: Optional[str],
        tool_args: Optional[dict[str, Any]],
        policy_result: Optional[str],
        reason: Optional[str],
        anomaly_scores: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": utc_now_iso(),
            "agent_id": agent_id,
            "session_id": session_id,
            "event_type": event_type,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "policy_result": policy_result,
            "anomaly_scores": anomaly_scores,
            "reason": reason,
        }

    def _jsonrpc_err(self, id_: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

    async def handle_mcp(self, *, token: str, body: dict[str, Any], session_id: str) -> tuple[int, dict[str, Any], dict[str, str]]:
        claims = self.verify_jwt(token)
        agent_id = str(claims.get("agent_id"))
        if not agent_id:
            return 401, self._jsonrpc_err(body.get("id"), -32001, "Invalid token: missing agent_id"), {}

        method = body.get("method")
        if method != "tools/call":
            # passthrough
            try:
                r = await self.http.post(self.upstream_mcp, json=body)
                return r.status_code, r.json(), {"X-ATBMS-Session": session_id}
            except Exception:
                return 200, {"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True, "mock": True}}, {
                    "X-ATBMS-Session": session_id
                }

        params = body.get("params") or {}
        tool_name = params.get("name") or params.get("tool") or params.get("tool_name")
        args = params.get("arguments") or params.get("args") or {}
        if not isinstance(tool_name, str) or not isinstance(args, dict):
            return 400, self._jsonrpc_err(body.get("id"), -32602, "Malformed tools/call params"), {}

        decision = await self.evaluate_policy(agent_id=agent_id, tool_name=tool_name, args=args, claims=claims)
        if decision.effect == "BLOCK":
            self._stats_record("blocked")
            evt = self._mk_audit_event(
                event_type="POLICY_BLOCK",
                agent_id=agent_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_args=args,
                policy_result="BLOCK",
                reason=decision.reason or "Blocked",
            )
            self.event_bus.publish(evt)
            asyncio.create_task(self.write_audit(evt))
            return 403, self._jsonrpc_err(body.get("id"), -32003, f"Blocked: {decision.reason}"), {"X-ATBMS-Session": session_id}

        if decision.effect == "REQUIRE_APPROVAL":
            self._stats_record("blocked")
            evt = self._mk_audit_event(
                event_type="ESCALATION",
                agent_id=agent_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_args=args,
                policy_result="REQUIRE_APPROVAL",
                reason=decision.reason or "Requires approval",
            )
            self.event_bus.publish(evt)
            asyncio.create_task(self.write_audit(evt))
            return 202, {"approval_id": decision.approval_id or str(uuid.uuid4()), "status": "PENDING"}, {
                "X-ATBMS-Session": session_id
            }

        allowed, _remaining = self.ratelimiter.allow(f"rate:{agent_id}:{tool_name}")
        if not allowed:
            self._stats_record("blocked")
            evt = self._mk_audit_event(
                event_type="POLICY_BLOCK",
                agent_id=agent_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_args=args,
                policy_result="BLOCK",
                reason="Rate limit exceeded",
            )
            self.event_bus.publish(evt)
            asyncio.create_task(self.write_audit(evt))
            return 429, self._jsonrpc_err(body.get("id"), -32029, "Rate limit exceeded"), {"X-ATBMS-Session": session_id}

        # session tracking
        sess = self.sessions.get(session_id) or {
            "agent_id": agent_id,
            "start_time": utc_now_iso(),
            "tool_calls": [],
            "capability_sources": {},
        }
        sess["tool_calls"].append({"ts": utc_now_iso(), "tool": tool_name, "args": args})
        self.sessions.upsert(session_id, sess)

        call_evt = self._mk_audit_event(
            event_type="TOOL_CALL",
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=args,
            policy_result="ALLOW",
            reason="Allowed",
        )
        self.event_bus.publish(call_evt)
        asyncio.create_task(self.write_audit(call_evt))

        # forward upstream
        try:
            upstream_resp = await self.http.post(self.upstream_mcp, json=body)
            resp_json = upstream_resp.json()
            status = upstream_resp.status_code
        except Exception:
            if not self.prototype_mode:
                return 502, self._jsonrpc_err(body.get("id"), -32050, "Upstream MCP unreachable"), {"X-ATBMS-Session": session_id}
            status = 200
            resp_json = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True, "mock": True, "tool": tool_name}}

        finding = scan(resp_json)
        headers: dict[str, str] = {"X-ATBMS-Session": session_id}
        if finding:
            action = self._tool_injection_action(tool_name)
            self._stats_record("flagged")
            flagged_evt = self._mk_audit_event(
                event_type="RESPONSE_FLAGGED",
                agent_id=agent_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_args=args,
                policy_result="ALLOW",
                reason=f"Prompt injection detected: {finding.category}",
                anomaly_scores={"injection": {"category": finding.category, "snippet": finding.snippet}},
            )
            self.event_bus.publish(flagged_evt)
            asyncio.create_task(self.write_audit(flagged_evt))

            if action == "BLOCK":
                return 403, self._jsonrpc_err(body.get("id"), -32012, "Response blocked due to injection"), headers
            if action == "STRIP":
                resp_json = strip_injection(resp_json)
            headers["X-ATBMS-Warning"] = f"injection:{finding.category}"

        self._stats_record("allowed")
        return status, resp_json, headers

