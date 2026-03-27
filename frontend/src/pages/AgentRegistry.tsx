import { useEffect, useMemo, useState } from "react";
import AgentCard from "../components/AgentCard";
import BlastRadiusGraph from "../components/BlastRadiusGraph";
import { api, type Agent, type Allowlist, type BlastRadiusGraph as Graph } from "../lib/api";

async function sha256Hex(s: string): Promise<string> {
  const enc = new TextEncoder().encode(s);
  const buf = await crypto.subtle.digest("SHA-256", enc);
  const bytes = Array.from(new Uint8Array(buf));
  return bytes.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default function AgentRegistry() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [allowlist, setAllowlist] = useState<Allowlist | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [blast, setBlast] = useState<{ agent: Agent; graph: Graph } | null>(null);

  const [form, setForm] = useState({
    display_name: "",
    model: "gpt-5.2",
    owner: "",
    tags: "trusted",
    tools: [] as string[],
    system_prompt: "",
  });

  const toolOptions = useMemo(() => allowlist?.tools?.map((t) => t.name) || [], [allowlist]);

  const load = async () => {
    setErr(null);
    try {
      const [a, al] = await Promise.all([api.listAgents(), api.allowlist()]);
      setAgents(a);
      setAllowlist(al);
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xl font-semibold">Agent Registry</div>
          {err ? <div className="text-xs text-red mt-1">{err}</div> : <div className="text-xs text-muted mt-1">{agents.length} agents</div>}
        </div>
        <button onClick={() => setOpen(true)} className="px-4 py-2 rounded bg-blue/20 border border-blue/40 hover:border-blue text-sm">
          Register New Agent
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {agents.map((a) => (
          <AgentCard
            key={a.agent_id}
            agent={a}
            onBlast={async () => {
              setErr(null);
              try {
                const g = await api.blastRadius(a.agent_id);
                setBlast({ agent: a, graph: g });
              } catch (e: any) {
                setErr(e?.message || String(e));
              }
            }}
            onSessions={() => {
              window.location.href = `/sessions?agent_id=${encodeURIComponent(a.agent_id)}`;
            }}
            onToggle={async () => {
              const next = a.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
              await api.updateAgent(a.agent_id, { status: next } as any);
              await load();
            }}
          />
        ))}
      </div>

      {open ? (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-6">
          <div className="w-full max-w-[860px] bg-surface border border-border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="font-semibold">Register New Agent</div>
              <button className="text-xs px-2 py-1 rounded border border-border hover:border-blue/60" onClick={() => setOpen(false)}>
                Close
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 mt-4">
              <label className="text-sm">
                <div className="text-xs text-muted mb-1">Display Name</div>
                <input className="w-full bg-bg border border-border rounded px-3 py-2" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
              </label>
              <label className="text-sm">
                <div className="text-xs text-muted mb-1">Model</div>
                <input className="w-full bg-bg border border-border rounded px-3 py-2" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
              </label>
              <label className="text-sm">
                <div className="text-xs text-muted mb-1">Owner Email</div>
                <input className="w-full bg-bg border border-border rounded px-3 py-2" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} />
              </label>
              <label className="text-sm">
                <div className="text-xs text-muted mb-1">Tags (comma-separated)</div>
                <input className="w-full bg-bg border border-border rounded px-3 py-2" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
              </label>
            </div>

            <div className="mt-4">
              <div className="text-xs text-muted mb-2">Tool Manifest</div>
              <div className="grid grid-cols-3 gap-2">
                {toolOptions.map((t) => (
                  <label key={t} className="text-xs bg-bg border border-border rounded px-2 py-2 flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.tools.includes(t)}
                      onChange={(e) => {
                        setForm((prev) => ({
                          ...prev,
                          tools: e.target.checked ? [...prev.tools, t] : prev.tools.filter((x) => x !== t),
                        }));
                      }}
                    />
                    <span className="font-mono">{t}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-4">
              <div className="text-xs text-muted mb-2">System Prompt</div>
              <textarea className="w-full h-[140px] bg-bg border border-border rounded px-3 py-2 text-sm" value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} />
            </div>

            <div className="mt-4 flex justify-end gap-2">
              <button className="px-3 py-2 text-sm rounded border border-border hover:border-blue/60" onClick={() => setOpen(false)}>
                Cancel
              </button>
              <button
                className="px-4 py-2 text-sm rounded bg-blue/20 border border-blue/40 hover:border-blue"
                onClick={async () => {
                  setErr(null);
                  try {
                    const created = await api.createAgent({
                      display_name: form.display_name,
                      model: form.model,
                      owner: form.owner,
                      tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean),
                      tool_manifest: form.tools,
                      system_prompt: form.system_prompt,
                    });
                    const prompt_hash = await sha256Hex(form.system_prompt);
                    await api.attest(created.agent_id, { system_prompt_hash: prompt_hash, tool_manifest: created.tool_manifest });
                    setOpen(false);
                    setForm({ display_name: "", model: "gpt-5.2", owner: "", tags: "trusted", tools: [], system_prompt: "" });
                    await load();
                  } catch (e: any) {
                    setErr(e?.message || String(e));
                  }
                }}
              >
                Register & Attest
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {blast ? (
        <div className="fixed inset-0 bg-black/70 p-6 overflow-auto">
          <div className="max-w-[1200px] mx-auto bg-surface border border-border rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="font-semibold">Blast Radius — {blast.agent.display_name}</div>
              <button className="text-xs px-2 py-1 rounded border border-border hover:border-blue/60" onClick={() => setBlast(null)}>
                Close
              </button>
            </div>
            <div className="mt-4">
              <BlastRadiusGraph graph={blast.graph} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

