import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type Agent, type AuditEvent, type SessionSummary } from "../lib/api";

function trunc(s: string, n = 10) {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

export default function SessionExplorer() {
  const [sp] = useSearchParams();
  const agentFilter = sp.get("agent_id") || "";

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selected, setSelected] = useState<SessionSummary | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [verify, setVerify] = useState<{ valid: boolean; total_events: number; first_broken_at: number | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      setErr(null);
      try {
        const [ss, aa] = await Promise.all([api.listSessions(), api.listAgents()]);
        if (!alive) return;
        setSessions(agentFilter ? ss.filter((s) => s.agent_id === agentFilter) : ss);
        setAgents(aa);
      } catch (e: any) {
        if (!alive) return;
        setErr(e?.message || String(e));
      }
    };
    load();
    return () => {
      alive = false;
    };
  }, [agentFilter]);

  const agentName = useMemo(() => {
    const m = new Map(agents.map((a) => [a.agent_id, a.display_name]));
    return (id?: string | null) => (id && m.get(id)) || id || "—";
  }, [agents]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      if (!selected) return;
      setVerify(null);
      try {
        const ev = await api.sessionEvents(selected.session_id);
        if (!alive) return;
        setEvents(ev);
      } catch (e: any) {
        if (!alive) return;
        setErr(e?.message || String(e));
      }
    };
    load();
    return () => {
      alive = false;
    };
  }, [selected?.session_id]);

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-4 bg-surface border border-border rounded-lg overflow-hidden">
        <div className="p-3 border-b border-border">
          <div className="text-sm font-semibold">Sessions</div>
          <div className="text-xs text-muted mt-1">{agentFilter ? `Filtered to agent ${trunc(agentFilter, 14)}` : `${sessions.length} sessions`}</div>
          {err ? <div className="text-xs text-red mt-2">{err}</div> : null}
        </div>
        <div className="max-h-[72vh] overflow-auto">
          {sessions.map((s) => {
            const danger = s.block_count > 0;
            return (
              <button
                key={s.session_id}
                onClick={() => setSelected(s)}
                className={`w-full text-left p-3 border-b border-border hover:bg-bg ${selected?.session_id === s.session_id ? "bg-bg" : ""}`}
              >
                <div className="flex items-center justify-between">
                  <div className="text-xs font-mono">{trunc(s.session_id, 14)}</div>
                  <span className={`w-2 h-2 rounded-full ${danger ? "bg-red" : "bg-green"}`} />
                </div>
                <div className="text-xs text-muted mt-1">{agentName(s.agent_id)}</div>
                <div className="text-xs text-muted mt-1">
                  calls <span className="text-text">{s.call_count}</span> · blocks <span className={danger ? "text-red" : "text-green"}>{s.block_count}</span>
                </div>
              </button>
            );
          })}
          {sessions.length === 0 ? <div className="p-3 text-xs text-muted">No sessions.</div> : null}
        </div>
      </div>

      <div className="col-span-8">
        {!selected ? (
          <div className="text-muted text-sm">Select a session to inspect.</div>
        ) : (
          <div className="bg-surface border border-border rounded-lg overflow-hidden">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold">Session {trunc(selected.session_id, 18)}</div>
                <div className="text-xs text-muted mt-1">{agentName(selected.agent_id)}</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="px-3 py-2 text-xs rounded border border-border hover:border-blue/60"
                  onClick={async () => {
                    const v = await api.verifyChain(selected.session_id);
                    setVerify(v);
                  }}
                >
                  Verify Hash Chain
                </button>
              </div>
            </div>
            {verify ? (
              <div className={`p-3 border-b border-border text-xs ${verify.valid ? "text-green" : "text-red"}`}>
                {verify.valid ? `✓ Chain intact — ${verify.total_events} events verified` : `✗ Chain broken at event #${verify.first_broken_at}`}
              </div>
            ) : null}
            <div className="p-3">
              <div className="flex flex-col gap-3">
                {events.map((e) => {
                  const danger = e.event_type === "POLICY_BLOCK" || e.policy_result === "BLOCK";
                  const flagged = e.event_type === "RESPONSE_FLAGGED";
                  const badge = danger ? "bg-red/20 text-red border-red/40" : flagged ? "bg-yellow/20 text-yellow border-yellow/40" : "bg-green/15 text-green border-green/40";
                  return (
                    <div key={e.event_id} className="border border-border rounded-lg bg-bg p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs text-muted">{new Date(e.timestamp).toLocaleString()}</div>
                        <span className={`text-xs px-2 py-1 rounded border ${badge}`}>{e.event_type}</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between">
                        <div className="text-sm font-mono">{e.tool_name || "—"}</div>
                        <div className="text-xs text-muted">{e.policy_result || ""}</div>
                      </div>
                      {e.reason ? <div className="text-xs text-muted mt-2">{e.reason}</div> : null}
                    </div>
                  );
                })}
                {events.length === 0 ? <div className="text-xs text-muted">No events.</div> : null}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

