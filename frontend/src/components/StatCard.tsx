import type { ReactNode } from "react";

export default function StatCard(props: { title: string; value: string | number; subtitle?: string; icon?: ReactNode; accent?: "green" | "red" | "yellow" | "blue" | "purple" }) {
  const accent = props.accent || "blue";
  const ring =
    accent === "green"
      ? "border-green/40"
      : accent === "red"
        ? "border-red/40"
        : accent === "yellow"
          ? "border-yellow/40"
          : accent === "purple"
            ? "border-purple/40"
          : "border-blue/40";
  return (
    <div className={`bg-surface border border-border rounded-lg p-4 flex items-start justify-between ${ring}`}>
      <div>
        <div className="text-xs text-muted">{props.title}</div>
        <div className="text-2xl font-semibold mt-1">{props.value}</div>
        {props.subtitle ? <div className="text-xs text-muted mt-1">{props.subtitle}</div> : null}
      </div>
      {props.icon ? <div className="text-muted">{props.icon}</div> : null}
    </div>
  );
}

