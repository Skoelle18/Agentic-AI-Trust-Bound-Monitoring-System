import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Alert, type AuditEvent, type ProxyStatsWindow, type SessionSummary } from "../lib/api";
import { useSSE } from "../lib/sse";
import StatCard from "../components/StatCard";
import EventRow from "../components/EventRow";

const PROXY_STREAM = (import.meta.env.VITE_PROXY_URL as string) + "/api/stream";

function trunc(id: string, n = 8) {
  return id.length > n ? `${id.slice(0, n)}…` : id;
}

export default function LiveFeed() {
  const { events, connected } = useSSE(PROXY_STREAM);
  const [stats, setStats] = useState<ProxyStatsWindow[]>([]);
  const [filter, setFilter] = useState<"ALL" | "ALLOW" | "BLOCK" | "FLAGGED">("ALL");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.proxyStats();
        if (!alive) return;
        setStats(s.windows);
      } catch (e: any) {
        if (!alive) return;
        setErr(e?.message || String(e));
      }
      try {
        const ss = await api.listSessions();
        if (!alive) return;
        setSessions(ss.slice(0, 5));
      } catch {}
      try {
        const as = await api.listAlerts(false);
        if (!alive) return;
        setAlerts(as.slice(0, 3));
      } catch {}
    };
    tick();
    const id = setInterval(tick, 10000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (events as AuditEvent[])
      .filter((e) => {
        if (filter === "BLOCK") return e.event_type === "POLICY_BLOCK" || e.policy_result === "BLOCK" || e.policy_result === "REQUIRE_APPROVAL";
        if (filter === "FLAGGED") return e.event_type === "RESPONSE_FLAGGED";
        if (filter === "ALLOW") return !(e.event_type === "POLICY_BLOCK" || e.event_type === "RESPONSE_FLAGGED") && e.policy_result !== "BLOCK";
        return true;
      })
      .filter((e) => {
        if (!term) return true;
        return (e.tool_name || "").toLowerCase().includes(term) || (e.reason || "").toLowerCase().includes(term);
      });
  }, [events, filter, q]);

  const topTools = useMemo(() => {
    const counts = new Map<string, number>();
    for (const e of events as AuditEvent[]) {
      const t = e.tool_name || "—";
      counts.set(t, (counts.get(t) || 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([tool, count]) => ({ tool, count }));
  }, [events]);

  const stat1h = stats.find((w) => w.window === "1h");

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-9">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-xl font-semibold">Live Feed</div>
            <div className="text-xs text-muted mt-1">
              SSE: <span className={connected ? "text-green" : "text-red"}>{connected ? "connected" : "disconnected"}</span>
              {err ? <span className="ml-2 text-red">{err}</span> : null}
            </div>
          </div>
          <button
            onClick={async () => {
              setErr(null);
              try {
                await api.runDemo();
              } catch (e: any) {
                setErr(e?.message || String(e));
              }
            }}
            className="px-4 py-2 rounded bg-blue/20 border border-blue/40 hover:border-blue text-sm"
          >
            Run Demo
          </button>
        </div>

        <div className="grid grid-cols-4 gap-4">
          <StatCard title="Total (1h)" value={stat1h?.total ?? 0} subtitle="proxy counters" />
          <StatCard title="Allowed (1h)" value={stat1h?.allowed ?? 0} accent="green" />
          <StatCard title="Blocked/Approval (1h)" value={stat1h?.blocked ?? 0} accent="red" />
          <StatCard title="Flagged (1h)" value={stat1h?.flagged ?? 0} accent="yellow" />
        </div>

        <div className="mt-4 bg-surface border border-border rounded-lg">
          <div className="p-3 flex items-center gap-3 border-b border-border">
            <div className="flex gap-2">
              {(["ALL", "ALLOW", "BLOCK", "FLAGGED"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 text-xs rounded border ${
                    filter === f ? "bg-bg border-blue/60 text-blue" : "bg-surface border-border text-muted hover:bg-bg"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search tool or reason…"
              className="ml-auto w-[320px] bg-bg border border-border rounded px-3 py-2 text-sm outline-none focus:border-blue/60"
            />
            <span className="text-xs text-muted">{filtered.length} events</span>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-left">
              <thead className="text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="px-3 py-2">Timestamp</th>
                  <th className="px-3 py-2">Decision</th>
                  <th className="px-3 py-2">Agent</th>
                  <th className="px-3 py-2">Tool</th>
                  <th className="px-3 py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 200).map((e) => (
                  <EventRow key={(e as any).event_id || `${e.timestamp}-${e.tool_name}`} e={e} onClick={() => setSelected(e)} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="col-span-3 flex flex-col gap-4">
        <div className="bg-surface border border-border rounded-lg p-3">
          <div className="text-sm font-semibold mb-2">Top Tools</div>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topTools} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="tool" tick={{ fill: "#7d8590", fontSize: 10 }} width={90} />
                <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d", color: "#e6edf3" }} />
                <Bar dataKey="count" fill="#58a6ff" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-surface border border-border rounded-lg p-3">
          <div className="text-sm font-semibold mb-2">Recent Sessions</div>
          <div className="flex flex-col gap-2">
            {sessions.map((s) => (
              <div key={s.session_id} className="bg-bg border border-border rounded p-2">
                <div className="text-xs font-mono">{trunc(s.session_id, 12)}</div>
                <div className="text-xs text-muted mt-1">
                  calls: <span className="text-text">{s.call_count}</span> blocks:{" "}
                  <span className={s.block_count > 0 ? "text-red" : "text-green"}>{s.block_count}</span>
                </div>
              </div>
            ))}
            {sessions.length === 0 ? <div className="text-xs text-muted">No sessions yet.</div> : null}
          </div>
        </div>

        <div className="bg-surface border border-border rounded-lg p-3">
          <div className="text-sm font-semibold mb-2">Active Alerts</div>
          <div className="flex flex-col gap-2">
            {alerts.map((a) => (
              <div key={a.id} className="bg-bg border border-border rounded p-2">
                <div className="text-xs">
                  <span className="text-yellow">{a.alert_type}</span> <span className="text-muted">({a.module})</span>
                </div>
                <div className="text-xs text-muted mt-1 truncate">{a.detail}</div>
                <button
                  className="mt-2 text-xs px-2 py-1 rounded border border-border hover:border-blue/60"
                  onClick={async () => {
                    await api.dismissAlert(a.id);
                    setAlerts((prev) => prev.filter((x) => x.id !== a.id));
                  }}
                >
                  Dismiss
                </button>
              </div>
            ))}
            {alerts.length === 0 ? <div className="text-xs text-muted">No active alerts.</div> : null}
          </div>
        </div>
      </div>

      {selected ? (
        <div className="fixed top-0 right-0 h-full w-[420px] bg-surface border-l border-border p-4 overflow-auto">
          <div className="flex items-center justify-between">
            <div className="font-semibold">Event Detail</div>
            <button className="text-xs px-2 py-1 rounded border border-border hover:border-blue/60" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <div className="text-xs text-muted mt-2">{selected.timestamp}</div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div className="bg-bg border border-border rounded p-2">
              <div className="text-muted">Agent</div>
              <div className="font-mono">{selected.agent_id || "—"}</div>
            </div>
            <div className="bg-bg border border-border rounded p-2">
              <div className="text-muted">Session</div>
              <div className="font-mono">{selected.session_id || "—"}</div>
            </div>
            <div className="bg-bg border border-border rounded p-2">
              <div className="text-muted">Type</div>
              <div>{selected.event_type}</div>
            </div>
            <div className="bg-bg border border-border rounded p-2">
              <div className="text-muted">Policy</div>
              <div>{selected.policy_result || "—"}</div>
            </div>
          </div>
          <div className="mt-3">
            <div className="text-xs text-muted mb-1">Tool args</div>
            <pre className="text-xs bg-bg border border-border rounded p-2 overflow-auto max-h-[200px]">
              {JSON.stringify(selected.tool_args ?? {}, null, 2)}
            </pre>
          </div>
          <div className="mt-3">
            <div className="text-xs text-muted mb-1">Hash chain</div>
            <div className="text-xs font-mono bg-bg border border-border rounded p-2">
              <div>
                <span className="text-muted">prev</span>: <span className="text-purple">{selected.prev_hash.slice(0, 20)}…</span>
              </div>
              <div className="mt-1">
                <span className="text-muted">hash</span>: <span className="text-purple">{selected.event_hash.slice(0, 20)}…</span>
              </div>
              <div className="mt-2 text-muted">ECDSA signature: <span className="text-purple">present</span></div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

