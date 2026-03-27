import { useEffect, useMemo, useState } from "react";
import { api, type Agent, type Escalation } from "../lib/api";

const tabs = ["PENDING", "APPROVED", "DENIED", "EXPIRED"] as const;

export default function EscalationQueue() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tab, setTab] = useState<(typeof tabs)[number]>("PENDING");
  const [items, setItems] = useState<Escalation[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const agentName = useMemo(() => {
    const m = new Map(agents.map((a) => [a.agent_id, a.display_name]));
    return (id: string) => m.get(id) || id;
  }, [agents]);

  const load = async () => {
    setErr(null);
    try {
      const [aa, es] = await Promise.all([api.listAgents(), api.listEscalations(tab)]);
      setAgents(aa);
      setItems(es);
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [tab]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xl font-semibold">Escalation Queue</div>
          {err ? <div className="text-xs text-red mt-1">{err}</div> : <div className="text-xs text-muted mt-1">{items.length} items</div>}
        </div>
        <div className="flex gap-2">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-xs px-3 py-2 rounded border ${tab === t ? "bg-bg border-blue/60 text-blue" : "border-border text-muted hover:bg-bg"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {items.map((e) => (
          <div key={e.id} className="bg-surface border border-border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="font-semibold">
                {agentName(e.agent_id)} · <span className="font-mono text-xs">{e.tool_name}</span>
              </div>
              <span className="text-xs px-2 py-1 rounded border border-border text-muted">{e.status}</span>
            </div>
            <div className="text-xs text-muted mt-2">{e.reason}</div>
            <pre className="text-xs font-mono bg-bg border border-border rounded p-2 mt-3 overflow-auto max-h-[180px]">{JSON.stringify(e.tool_args, null, 2)}</pre>

            {e.status === "PENDING" ? (
              <div className="mt-3 flex gap-2 items-center">
                <button
                  className="text-xs px-3 py-2 rounded border border-green/40 bg-green/10 hover:border-green"
                  onClick={async () => {
                    await api.approveEscalation(e.id);
                    await load();
                  }}
                >
                  Approve
                </button>
                <button
                  className="text-xs px-3 py-2 rounded border border-red/40 bg-red/10 hover:border-red"
                  onClick={async () => {
                    const reason = prompt("Deny reason?");
                    if (!reason) return;
                    await api.denyEscalation(e.id, reason);
                    await load();
                  }}
                >
                  Deny
                </button>
                <div className="ml-auto text-xs text-muted">created {new Date(e.created_at).toLocaleString()}</div>
              </div>
            ) : (
              <div className="mt-3 text-xs text-muted">
                resolved by {e.resolved_by || "—"} at {e.resolved_at ? new Date(e.resolved_at).toLocaleString() : "—"} · note: {e.note || "—"}
              </div>
            )}
          </div>
        ))}
        {items.length === 0 ? <div className="text-xs text-muted">No escalations.</div> : null}
      </div>
    </div>
  );
}

