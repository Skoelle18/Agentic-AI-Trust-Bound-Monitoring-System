import { useEffect, useMemo, useState } from "react";
import { api, type Agent, type AuditEvent } from "../lib/api";

function trunc(s: string, n = 10) {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

export default function AuditLog() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [offset, setOffset] = useState(0);
  const [verify, setVerify] = useState<{ valid: boolean; total_events: number; first_broken_at: number | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [filters, setFilters] = useState({
    agent_id: "",
    event_type: "",
    tool_name: "",
    from_ts: "",
    to_ts: "",
  });

  const agentName = useMemo(() => {
    const m = new Map(agents.map((a) => [a.agent_id, a.display_name]));
    return (id?: string | null) => (id && m.get(id)) || id || "—";
  }, [agents]);

  const load = async () => {
    setErr(null);
    try {
      const [aa, ev] = await Promise.all([
        api.listAgents(),
        api.listEvents({ limit: 50, offset, ...filters, agent_id: filters.agent_id || undefined, event_type: filters.event_type || undefined, tool_name: filters.tool_name || undefined, from_ts: filters.from_ts || undefined, to_ts: filters.to_ts || undefined }),
      ]);
      setAgents(aa);
      setEvents(ev);
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  };

  useEffect(() => {
    load();
  }, [offset]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xl font-semibold">Audit Log</div>
          {err ? <div className="text-xs text-red mt-1">{err}</div> : <div className="text-xs text-muted mt-1">Canonical append-only events</div>}
        </div>
        <div className="flex gap-2">
          <button
            className="px-3 py-2 text-sm rounded border border-border hover:border-blue/60"
            onClick={async () => {
              const v = await api.verifyChain();
              setVerify(v);
            }}
          >
            Verify Chain Integrity
          </button>
          <button
            className="px-3 py-2 text-sm rounded border border-border hover:border-blue/60"
            onClick={() => {
              const lines = events.map((e) => JSON.stringify(e)).join("\n");
              const blob = new Blob([lines], { type: "application/jsonl" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "audit-export.jsonl";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Export JSONL
          </button>
        </div>
      </div>

      {verify ? (
        <div className={`mb-3 p-3 rounded border ${verify.valid ? "border-green/40 bg-green/10 text-green" : "border-red/40 bg-red/10 text-red"}`}>
          {verify.valid ? `✓ All ${verify.total_events} events verified — chain intact` : `✗ Chain broken at event #${verify.first_broken_at}`}
        </div>
      ) : null}

      <div className="bg-surface border border-border rounded-lg p-3 mb-3">
        <div className="grid grid-cols-5 gap-3">
          <label className="text-xs">
            <div className="text-muted mb-1">Agent</div>
            <select className="w-full bg-bg border border-border rounded px-2 py-2" value={filters.agent_id} onChange={(e) => setFilters({ ...filters, agent_id: e.target.value })}>
              <option value="">All</option>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            <div className="text-muted mb-1">Event type</div>
            <input className="w-full bg-bg border border-border rounded px-2 py-2 font-mono" value={filters.event_type} onChange={(e) => setFilters({ ...filters, event_type: e.target.value })} placeholder="TOOL_CALL" />
          </label>
          <label className="text-xs">
            <div className="text-muted mb-1">Tool</div>
            <input className="w-full bg-bg border border-border rounded px-2 py-2 font-mono" value={filters.tool_name} onChange={(e) => setFilters({ ...filters, tool_name: e.target.value })} placeholder="read_file" />
          </label>
          <label className="text-xs">
            <div className="text-muted mb-1">From (ISO)</div>
            <input className="w-full bg-bg border border-border rounded px-2 py-2 font-mono" value={filters.from_ts} onChange={(e) => setFilters({ ...filters, from_ts: e.target.value })} placeholder="2026-03-17T..." />
          </label>
          <label className="text-xs">
            <div className="text-muted mb-1">To (ISO)</div>
            <input className="w-full bg-bg border border-border rounded px-2 py-2 font-mono" value={filters.to_ts} onChange={(e) => setFilters({ ...filters, to_ts: e.target.value })} placeholder="2026-03-17T..." />
          </label>
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <button className="px-3 py-2 text-xs rounded border border-border hover:border-blue/60" onClick={() => setOffset(0)}>
            Reset page
          </button>
          <button
            className="px-3 py-2 text-xs rounded bg-blue/20 border border-blue/40 hover:border-blue"
            onClick={() => {
              setOffset(0);
              load();
            }}
          >
            Apply Filters
          </button>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-lg overflow-hidden">
        <table className="w-full text-left">
          <thead className="text-xs text-muted">
            <tr className="border-b border-border">
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Timestamp</th>
              <th className="px-3 py-2">Agent</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Tool</th>
              <th className="px-3 py-2">Policy</th>
              <th className="px-3 py-2">Hash</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <AuditRow key={e.event_id} e={e} agentName={agentName} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3">
        <button className="px-3 py-2 text-xs rounded border border-border hover:border-blue/60" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - 50))}>
          Prev
        </button>
        <div className="text-xs text-muted">offset {offset}</div>
        <button className="px-3 py-2 text-xs rounded border border-border hover:border-blue/60" onClick={() => setOffset((o) => o + 50)}>
          Next
        </button>
      </div>
    </div>
  );
}

function AuditRow(props: { e: AuditEvent; agentName: (id?: string | null) => string }) {
  const [open, setOpen] = useState(false);
  const e = props.e;
  return (
    <>
      <tr className="border-b border-border hover:bg-bg cursor-pointer" onClick={() => setOpen((v) => !v)}>
        <td className="px-3 py-2 text-xs font-mono">{trunc(e.event_id, 10)}</td>
        <td className="px-3 py-2 text-xs text-muted">{new Date(e.timestamp).toLocaleString()}</td>
        <td className="px-3 py-2 text-xs">{props.agentName(e.agent_id)}</td>
        <td className="px-3 py-2 text-xs">{e.event_type}</td>
        <td className="px-3 py-2 text-xs font-mono">{e.tool_name || "—"}</td>
        <td className="px-3 py-2 text-xs">{e.policy_result || "—"}</td>
        <td className="px-3 py-2 text-xs font-mono text-purple">{trunc(e.event_hash, 16)}</td>
      </tr>
      {open ? (
        <tr className="border-b border-border">
          <td colSpan={7} className="px-3 py-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-bg border border-border rounded p-3">
                <div className="text-xs text-muted mb-1">prev_hash</div>
                <div className="text-xs font-mono text-purple break-all">{e.prev_hash}</div>
              </div>
              <div className="bg-bg border border-border rounded p-3">
                <div className="text-xs text-muted mb-1">event_hash</div>
                <div className="text-xs font-mono text-purple break-all">{e.event_hash}</div>
              </div>
              <div className="bg-bg border border-border rounded p-3 col-span-2">
                <div className="text-xs text-muted mb-1">signature</div>
                <div className="text-xs font-mono text-purple break-all">{e.signature}</div>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

