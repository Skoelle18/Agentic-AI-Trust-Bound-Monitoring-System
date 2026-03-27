import { useEffect, useMemo, useState } from "react";
import PolicyEditor from "../components/PolicyEditor";
import { api, type Agent, type Escalation } from "../lib/api";

export default function PolicyManager() {
  const [rego, setRego] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [pending, setPending] = useState<Escalation[]>([]);
  const [resolved, setResolved] = useState<Escalation[]>([]);
  const [tab, setTab] = useState<"PENDING" | "RESOLVED">("PENDING");
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const [test, setTest] = useState({ agent_id: "", tool_name: "read_file", args: '{ "path": "/workspace/README.md" }' });

  const agentById = useMemo(() => new Map(agents.map((a) => [a.agent_id, a])), [agents]);

  const load = async () => {
    setErr(null);
    try {
      const [p, a, esPending, esAll] = await Promise.all([api.getPolicies(), api.listAgents(), api.listEscalations("PENDING"), api.listEscalations()]);
      setRego(p.rego);
      setAgents(a);
      setPending(esPending);
      setResolved(esAll.filter((e) => e.status !== "PENDING").slice(0, 20));
      if (!test.agent_id && a[0]) setTest((t) => ({ ...t, agent_id: a[0].agent_id }));
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-xl font-semibold">Policy Manager</div>
            {err ? <div className="text-xs text-red mt-1">{err}</div> : ok ? <div className="text-xs text-green mt-1">{ok}</div> : <div className="text-xs text-muted mt-1">OPA policy is live-editable</div>}
          </div>
          <button
            className="px-4 py-2 rounded bg-blue/20 border border-blue/40 hover:border-blue text-sm"
            onClick={async () => {
              setOk(null);
              setErr(null);
              try {
                await api.putPolicies(rego);
                setOk("Saved & deployed.");
              } catch (e: any) {
                setErr(e?.message || String(e));
              }
            }}
          >
            Save & Deploy
          </button>
        </div>

        <PolicyEditor value={rego} onChange={setRego} />

        <div className="bg-surface border border-border rounded-lg p-3 mt-4">
          <div className="text-sm font-semibold mb-2">Test Call</div>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs">
              <div className="text-muted mb-1">Agent</div>
              <select className="w-full bg-bg border border-border rounded px-2 py-2" value={test.agent_id} onChange={(e) => setTest({ ...test, agent_id: e.target.value })}>
                {agents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs">
              <div className="text-muted mb-1">Tool</div>
              <input className="w-full bg-bg border border-border rounded px-2 py-2 font-mono" value={test.tool_name} onChange={(e) => setTest({ ...test, tool_name: e.target.value })} />
            </label>
          </div>
          <div className="mt-3">
            <div className="text-xs text-muted mb-1">Args (JSON)</div>
            <textarea className="w-full h-[110px] bg-bg border border-border rounded px-2 py-2 font-mono text-xs" value={test.args} onChange={(e) => setTest({ ...test, args: e.target.value })} />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <button
              className="px-3 py-2 text-xs rounded border border-border hover:border-blue/60"
              onClick={async () => {
                setOk(null);
                setErr(null);
                try {
                  const agent = agentById.get(test.agent_id);
                  const args = JSON.parse(test.args || "{}");
                  const res = await api.evaluate({
                    agent_id: test.agent_id,
                    tool_name: test.tool_name,
                    args,
                    agent_tags: agent?.tags || [],
                    tool_manifest: agent?.tool_manifest || [],
                  });
                  setOk(`Result: ${res.effect} (${res.rule_id})`);
                } catch (e: any) {
                  setErr(e?.message || String(e));
                }
              }}
            >
              Evaluate
            </button>
            <div className="text-xs text-muted">Uses live `/evaluate`</div>
          </div>
        </div>
      </div>

      <div className="col-span-6">
        <div className="bg-surface border border-border rounded-lg overflow-hidden">
          <div className="p-3 border-b border-border flex items-center justify-between">
            <div className="text-sm font-semibold">Escalation Queue</div>
            <div className="flex gap-2">
              <button
                className={`text-xs px-3 py-1.5 rounded border ${tab === "PENDING" ? "bg-bg border-blue/60 text-blue" : "border-border text-muted hover:bg-bg"}`}
                onClick={() => setTab("PENDING")}
              >
                Pending ({pending.length})
              </button>
              <button
                className={`text-xs px-3 py-1.5 rounded border ${tab === "RESOLVED" ? "bg-bg border-blue/60 text-blue" : "border-border text-muted hover:bg-bg"}`}
                onClick={() => setTab("RESOLVED")}
              >
                Resolved
              </button>
            </div>
          </div>
          <div className="p-3 flex flex-col gap-3 max-h-[82vh] overflow-auto">
            {(tab === "PENDING" ? pending : resolved).map((e) => (
              <div key={e.id} className="bg-bg border border-border rounded p-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">
                    {agentById.get(e.agent_id)?.display_name || e.agent_id} · <span className="font-mono text-xs">{e.tool_name}</span>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded border ${e.status === "PENDING" ? "border-yellow/40 text-yellow bg-yellow/10" : "border-border text-muted"}`}>{e.status}</span>
                </div>
                <div className="text-xs text-muted mt-1">{e.reason}</div>
                <pre className="text-xs font-mono bg-surface border border-border rounded p-2 mt-2 overflow-auto max-h-[140px]">{JSON.stringify(e.tool_args, null, 2)}</pre>
                {e.status === "PENDING" ? (
                  <div className="mt-2 flex items-center gap-2">
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
                    <div className="ml-auto text-xs text-muted">timeout: {e.timeout_minutes}m</div>
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-muted">
                    resolved by {e.resolved_by || "—"} at {e.resolved_at ? new Date(e.resolved_at).toLocaleString() : "—"}
                  </div>
                )}
              </div>
            ))}
            {(tab === "PENDING" ? pending : resolved).length === 0 ? <div className="text-xs text-muted">No items.</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

