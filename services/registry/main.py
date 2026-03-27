from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from services.shared.problem import instance_from_request, problem_detail

from .attestation import system_prompt_hash, verify_hash
from .auth import issue_attestation_jwt, jwk_from_public_pem, load_or_generate_rsa
from .blast_radius import compute_blast_radius, load_allowlist
from .discovery import discover_agents_from_env
from .models import AgentCreate, AgentOut, AgentUpdate, AttestRequest, AttestResponse


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> str:
    return os.getenv("REGISTRY_DB_PATH", "/data/registry.db")


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
  agent_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  model TEXT NOT NULL,
  system_prompt_hash TEXT NOT NULL,
  tool_manifest TEXT NOT NULL,
  owner TEXT NOT NULL,
  tags TEXT NOT NULL,
  status TEXT NOT NULL,
  last_attested TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
"""


app = FastAPI(title="ATBMS Registry", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conn = connect()
conn.executescript(SCHEMA)
conn.commit()

keys = load_or_generate_rsa()
allowlist = None


def _row_to_agent(row: sqlite3.Row) -> AgentOut:
    return AgentOut(
        agent_id=row["agent_id"],
        display_name=row["display_name"],
        model=row["model"],
        system_prompt_hash=row["system_prompt_hash"],
        tool_manifest=json.loads(row["tool_manifest"]),
        owner=row["owner"],
        tags=json.loads(row["tags"]),
        status=row["status"],
        last_attested=row["last_attested"],
        created_at=row["created_at"],
    )


@app.on_event("startup")
def _bootstrap() -> None:
    # optional bootstrap from env
    for a in discover_agents_from_env():
        try:
            agent_id = a.get("agent_id") or str(uuid.uuid4())
            existing = conn.execute("SELECT agent_id FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
            if existing:
                continue
            sp = a.get("system_prompt", "")
            conn.execute(
                """
                INSERT INTO agents(agent_id, display_name, model, system_prompt_hash, tool_manifest, owner, tags, status, last_attested, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    a.get("display_name", "Bootstrap Agent"),
                    a.get("model", "unknown"),
                    system_prompt_hash(sp),
                    json.dumps(a.get("tool_manifest", [])),
                    a.get("owner", "unknown@example.com"),
                    json.dumps(a.get("tags", [])),
                    a.get("status", "ACTIVE"),
                    None,
                    utc_now_iso(),
                ),
            )
            conn.commit()
        except Exception:
            continue


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/jwks.json")
def jwks() -> dict[str, Any]:
    return {"keys": [jwk_from_public_pem(keys.public_pem, keys.kid)]}


@app.get("/allowlist")
def get_allowlist(request: Request) -> Any:
    """
    Convenience endpoint for UI: returns parsed allowlist.yaml.
    """
    global allowlist
    try:
        if allowlist is None:
            allowlist = load_allowlist(os.getenv("ALLOWLIST_PATH", "/config/allowlist.yaml"))
        return allowlist
    except Exception as e:
        return problem_detail(status=500, title="Allowlist load failed", detail=str(e), instance=instance_from_request(request))


@app.post("/agents", response_model=AgentOut)
def create_agent(body: AgentCreate, request: Request) -> Any:
    try:
        agent_id = str(uuid.uuid4())
        prompt_hash = system_prompt_hash(body.system_prompt)
        created = utc_now_iso()
        conn.execute(
            """
            INSERT INTO agents(agent_id, display_name, model, system_prompt_hash, tool_manifest, owner, tags, status, last_attested, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                body.display_name,
                body.model,
                prompt_hash,
                json.dumps(body.tool_manifest),
                body.owner,
                json.dumps(body.tags),
                "ACTIVE",
                None,
                created,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return _row_to_agent(row)
    except Exception as e:
        return problem_detail(
            status=500,
            title="Create agent failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/agents", response_model=list[AgentOut])
def list_agents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = None,
    tag: Optional[str] = None,
) -> Any:
    try:
        where = []
        params: list[Any] = []
        if status:
            where.append("status = ?")
            params.append(status)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(f"SELECT * FROM agents {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
        agents = [_row_to_agent(r) for r in rows]
        if tag:
            agents = [a for a in agents if tag in a.tags]
        return agents
    except Exception as e:
        return problem_detail(
            status=500,
            title="List agents failed",
            detail=str(e),
            instance=instance_from_request(request),
        )


@app.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, request: Request) -> Any:
    row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not row:
        return problem_detail(
            status=404,
            title="Not Found",
            detail=f"Agent {agent_id} not found",
            instance=instance_from_request(request),
        )
    return _row_to_agent(row)


@app.patch("/agents/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: str, body: AgentUpdate, request: Request) -> Any:
    row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Agent not found", instance=instance_from_request(request))
    agent = _row_to_agent(row)
    data = body.model_dump(exclude_unset=True)
    updated = agent.model_copy(update=data)
    try:
        conn.execute(
            """
            UPDATE agents
            SET display_name = ?, model = ?, tool_manifest = ?, owner = ?, tags = ?, status = ?
            WHERE agent_id = ?
            """,
            (
                updated.display_name,
                updated.model,
                json.dumps(updated.tool_manifest),
                updated.owner,
                json.dumps(updated.tags),
                updated.status,
                agent_id,
            ),
        )
        conn.commit()
        row2 = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return _row_to_agent(row2)
    except Exception as e:
        return problem_detail(status=500, title="Update failed", detail=str(e), instance=instance_from_request(request))


@app.delete("/agents/{agent_id}", response_model=AgentOut)
def delete_agent(agent_id: str, request: Request) -> Any:
    row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Agent not found", instance=instance_from_request(request))
    try:
        conn.execute("UPDATE agents SET status = 'SUSPENDED' WHERE agent_id = ?", (agent_id,))
        conn.commit()
        row2 = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return _row_to_agent(row2)
    except Exception as e:
        return problem_detail(status=500, title="Delete failed", detail=str(e), instance=instance_from_request(request))


@app.post("/agents/{agent_id}/attest", response_model=AttestResponse)
def attest(agent_id: str, body: AttestRequest, request: Request) -> Any:
    row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Agent not found", instance=instance_from_request(request))
    agent = _row_to_agent(row)
    if agent.status != "ACTIVE":
        return problem_detail(status=403, title="Forbidden", detail="Agent is not ACTIVE", instance=instance_from_request(request))
    if not verify_hash(agent.system_prompt_hash, body.system_prompt_hash):
        return problem_detail(status=403, title="Forbidden", detail="System prompt hash mismatch", instance=instance_from_request(request))
    if sorted(body.tool_manifest) != sorted(agent.tool_manifest):
        return problem_detail(status=403, title="Forbidden", detail="Tool manifest mismatch", instance=instance_from_request(request))
    token, exp = issue_attestation_jwt(
        private_pem=keys.private_pem,
        kid=keys.kid,
        agent_id=agent.agent_id,
        tool_manifest=agent.tool_manifest,
        tags=agent.tags,
    )
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).replace(microsecond=0).isoformat()
    conn.execute("UPDATE agents SET last_attested = ? WHERE agent_id = ?", (utc_now_iso(), agent_id))
    conn.commit()
    return AttestResponse(token=token, expires_at=expires_at)


@app.get("/agents/{agent_id}/blast-radius")
def blast_radius(agent_id: str, request: Request) -> Any:
    global allowlist
    row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not row:
        return problem_detail(status=404, title="Not Found", detail="Agent not found", instance=instance_from_request(request))
    agent = _row_to_agent(row)
    try:
        if allowlist is None:
            allowlist = load_allowlist(os.getenv("ALLOWLIST_PATH", "/config/allowlist.yaml"))
        return compute_blast_radius(agent_id=agent.agent_id, tool_manifest=agent.tool_manifest, allowlist=allowlist)
    except Exception as e:
        return problem_detail(status=500, title="Blast radius failed", detail=str(e), instance=instance_from_request(request))


@app.get("/demo")
def demo(request: Request) -> Any:
    """
    Populate the registry with a couple demo agents.
    """
    try:
        existing = conn.execute("SELECT COUNT(1) AS c FROM agents").fetchone()
        if existing and int(existing["c"]) >= 2:
            return {"ok": True, "already": True}

        demo_agents = [
            AgentCreate(
                display_name="Demo Recon Agent",
                model="claude-sonnet-4-6",
                owner="security@example.com",
                tool_manifest=["list_directory", "read_file", "web_search", "http_request"],
                system_prompt="You are a helpful security agent. Follow policies.",
                tags=["untrusted"],
            ),
            AgentCreate(
                display_name="Demo Ops Agent",
                model="gpt-5.2",
                owner="ops@example.com",
                tool_manifest=["read_file", "write_file", "run_query", "web_search"],
                system_prompt="You are an ops agent. Do not exfiltrate data.",
                tags=["trusted"],
            ),
        ]

        created = []
        for a in demo_agents:
            created.append(create_agent(a, request))
        return {"ok": True, "created": [c.agent_id for c in created]}
    except Exception as e:
        return problem_detail(status=500, title="Demo failed", detail=str(e), instance=instance_from_request(request))

