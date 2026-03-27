import type { AuditEvent } from "../lib/api";

function badgeColor(e: AuditEvent) {
  const t = e.event_type;
  if (t === "POLICY_BLOCK" || e.policy_result === "BLOCK") return "bg-red/20 text-red border-red/40";
  if (t === "RESPONSE_FLAGGED") return "bg-yellow/20 text-yellow border-yellow/40";
  return "bg-green/15 text-green border-green/40";
}

export default function EventRow(props: { e: AuditEvent; onClick: () => void }) {
  const { e } = props;
  const left =
    e.event_type === "POLICY_BLOCK" || e.policy_result === "BLOCK"
      ? "border-l-red"
      : e.event_type === "RESPONSE_FLAGGED"
        ? "border-l-yellow"
        : "border-l-green";

  return (
    <tr onClick={props.onClick} className={`cursor-pointer hover:bg-bg border-l-2 ${left}`}>
      <td className="px-3 py-2 text-xs text-muted whitespace-nowrap">{new Date(e.timestamp).toLocaleString()}</td>
      <td className="px-3 py-2">
        <span className={`text-xs px-2 py-1 rounded border ${badgeColor(e)}`}>{e.policy_result || e.event_type}</span>
      </td>
      <td className="px-3 py-2 text-sm">{e.agent_id || "—"}</td>
      <td className="px-3 py-2 text-sm font-mono">{e.tool_name || "—"}</td>
      <td className="px-3 py-2 text-sm text-muted truncate max-w-[520px]">{e.reason || "—"}</td>
    </tr>
  );
}

