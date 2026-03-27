import type { Agent } from "../lib/api";

export default function AgentCard(props: {
  agent: Agent;
  onToggle: () => void;
  onBlast: () => void;
  onSessions: () => void;
}) {
  const a = props.agent;
  const statusColor =
    a.status === "ACTIVE" ? "bg-green/15 text-green border-green/40" : a.status === "SUSPENDED" ? "bg-red/20 text-red border-red/40" : "bg-yellow/15 text-yellow border-yellow/40";

  return (
    <div className="bg-surface border border-border rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{a.display_name}</div>
          <div className="text-xs text-muted">{a.model}</div>
        </div>
        <span className={`text-xs px-2 py-1 rounded border ${statusColor}`}>{a.status}</span>
      </div>
      <div className="text-xs text-muted">
        <div>
          <span className="text-text">Owner</span>: {a.owner}
        </div>
        <div className="mt-1">
          <span className="text-text">Last attested</span>: {a.last_attested ? new Date(a.last_attested).toLocaleString() : "—"}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {a.tool_manifest.map((t) => (
          <span key={t} className="text-xs px-2 py-1 rounded bg-bg border border-border font-mono">
            {t}
          </span>
        ))}
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={props.onBlast} className="px-3 py-2 text-xs rounded bg-bg border border-border hover:border-blue/60">
          Blast Radius
        </button>
        <button onClick={props.onSessions} className="px-3 py-2 text-xs rounded bg-bg border border-border hover:border-blue/60">
          View Sessions
        </button>
        <button
          onClick={props.onToggle}
          className={`ml-auto px-3 py-2 text-xs rounded border ${
            a.status === "ACTIVE" ? "bg-red/10 border-red/40 hover:border-red" : "bg-green/10 border-green/40 hover:border-green"
          }`}
        >
          {a.status === "ACTIVE" ? "Suspend" : "Activate"}
        </button>
      </div>
    </div>
  );
}

