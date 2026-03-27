export type AgentStatus = "ACTIVE" | "SUSPENDED" | "PENDING_REVIEW";

export type Agent = {
  agent_id: string;
  display_name: string;
  model: string;
  system_prompt_hash: string;
  tool_manifest: string[];
  owner: string;
  tags: string[];
  status: AgentStatus;
  last_attested?: string | null;
  created_at: string;
};

export type BlastRadiusGraph = {
  nodes: { id: string; type: string; label: string }[];
  edges: { source: string; target: string; label: string }[];
};

export type AuditEvent = {
  event_id: string;
  timestamp: string;
  agent_id?: string | null;
  session_id?: string | null;
  event_type: string;
  tool_name?: string | null;
  tool_args?: any;
  policy_result?: string | null;
  anomaly_scores?: any;
  reason?: string | null;
  prev_hash: string;
  event_hash: string;
  signature: string;
};

export type SessionSummary = {
  session_id: string;
  first_ts: string;
  last_ts: string;
  agent_id?: string | null;
  call_count: number;
  block_count: number;
};

export type ProxyStatsWindow = { window: "1h" | "24h" | "7d"; total: number; allowed: number; blocked: number; flagged: number };

export type Escalation = {
  id: string;
  agent_id: string;
  tool_name: string;
  tool_args: any;
  reason: string;
  status: "PENDING" | "APPROVED" | "DENIED" | "EXPIRED";
  created_at: string;
  resolved_at?: string | null;
  resolved_by?: string | null;
  note?: string | null;
  timeout_minutes: number;
};

export type Alert = {
  id: string;
  timestamp: string;
  agent_id?: string | null;
  session_id?: string | null;
  module: string;
  alert_type: string;
  score: number;
  detail: string;
  dismissed: boolean;
  dismissed_at?: string | null;
  dismissed_by?: string | null;
};

export type Allowlist = {
  tools: { name: string; upstream_system?: string; description?: string; injection_action?: string }[];
  systems?: Record<string, any>;
};

const REGISTRY = import.meta.env.VITE_REGISTRY_URL as string;
const PROXY = import.meta.env.VITE_PROXY_URL as string;
const POLICY = import.meta.env.VITE_POLICY_URL as string;
const ANOMALY = import.meta.env.VITE_ANOMALY_URL as string;
const AUDIT = import.meta.env.VITE_AUDIT_URL as string;

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      detail = j.detail || j.title || detail;
    } catch {}
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: async () => {
    const [registry, proxy, policy, anomaly, audit] = await Promise.allSettled([
      http<{ ok: boolean }>(`${REGISTRY}/health`),
      http<{ ok: boolean }>(`${PROXY}/health`),
      http<{ ok: boolean }>(`${POLICY}/health`),
      http<{ ok: boolean }>(`${ANOMALY}/health`),
      http<{ ok: boolean }>(`${AUDIT}/health`),
    ]);
    return { registry, proxy, policy, anomaly, audit };
  },

  // Proxy
  proxyStats: async () => http<{ windows: ProxyStatsWindow[] }>(`${PROXY}/api/proxy-stats`),
  runDemo: async () => http<any>(`${PROXY}/api/demo`),

  // Registry
  listAgents: async () => http<Agent[]>(`${REGISTRY}/agents?limit=200&offset=0`),
  allowlist: async () => http<Allowlist>(`${REGISTRY}/allowlist`),
  getAgent: async (agent_id: string) => http<Agent>(`${REGISTRY}/agents/${agent_id}`),
  createAgent: async (body: { display_name: string; model: string; owner: string; tags: string[]; tool_manifest: string[]; system_prompt: string }) =>
    http<Agent>(`${REGISTRY}/agents`, { method: "POST", body: JSON.stringify(body) }),
  updateAgent: async (agent_id: string, body: Partial<Agent>) => http<Agent>(`${REGISTRY}/agents/${agent_id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteAgent: async (agent_id: string) => http<Agent>(`${REGISTRY}/agents/${agent_id}`, { method: "DELETE" }),
  attest: async (agent_id: string, body: { system_prompt_hash: string; tool_manifest: string[] }) =>
    http<{ token: string; expires_at: string }>(`${REGISTRY}/agents/${agent_id}/attest`, { method: "POST", body: JSON.stringify(body) }),
  blastRadius: async (agent_id: string) => http<BlastRadiusGraph>(`${REGISTRY}/agents/${agent_id}/blast-radius`),

  // Policy
  getPolicies: async () => http<{ rego: string }>(`${POLICY}/policies`),
  putPolicies: async (rego: string) => http<{ ok: boolean }>(`${POLICY}/policies`, { method: "PUT", body: JSON.stringify({ rego }) }),
  evaluate: async (body: { agent_id: string; tool_name: string; args: any; agent_tags: string[]; tool_manifest: string[] }) =>
    http<any>(`${POLICY}/evaluate`, { method: "POST", body: JSON.stringify(body) }),
  listEscalations: async (status?: string) => http<Escalation[]>(`${POLICY}/escalations?limit=200&offset=0${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  approveEscalation: async (id: string, note?: string) =>
    http<{ ok: boolean }>(`${POLICY}/escalations/${id}/approve`, { method: "POST", body: JSON.stringify({ note, resolved_by: "ui@atbms" }) }),
  denyEscalation: async (id: string, reason: string) =>
    http<{ ok: boolean }>(`${POLICY}/escalations/${id}/deny`, { method: "POST", body: JSON.stringify({ reason, resolved_by: "ui@atbms" }) }),

  // Audit
  listEvents: async (params: { limit?: number; offset?: number; agent_id?: string; session_id?: string; event_type?: string; tool_name?: string; from_ts?: string; to_ts?: string }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    });
    return http<AuditEvent[]>(`${AUDIT}/events?${q.toString()}`);
  },
  listSessions: async () => http<SessionSummary[]>(`${AUDIT}/sessions?limit=200&offset=0`),
  sessionEvents: async (session_id: string) => http<AuditEvent[]>(`${AUDIT}/sessions/${session_id}`),
  verifyChain: async (session_id?: string) => http<{ valid: boolean; total_events: number; first_broken_at: number | null }>(`${AUDIT}/verify${session_id ? `?session_id=${encodeURIComponent(session_id)}` : ""}`),

  // Anomaly
  listAlerts: async (dismissed?: boolean) =>
    http<Alert[]>(`${ANOMALY}/alerts?limit=200&offset=0${dismissed === undefined ? "" : `&dismissed=${dismissed}`}`),
  dismissAlert: async (id: string) => http<{ ok: boolean }>(`${ANOMALY}/alerts/${id}/dismiss`, { method: "POST", body: JSON.stringify({ dismissed_by: "ui@atbms" }) }),
  baselines: async () => http<any[]>(`${ANOMALY}/baselines`),
  resetBaselines: async (agent_id: string) => http<{ ok: boolean; deleted: number }>(`${ANOMALY}/baselines/${agent_id}`, { method: "DELETE" }),
  scores: async (agent_id: string) => http<any>(`${ANOMALY}/scores/${agent_id}`),
  scoreHistory: async (agent_id: string) => http<any>(`${ANOMALY}/scores/${agent_id}/history`),
};

