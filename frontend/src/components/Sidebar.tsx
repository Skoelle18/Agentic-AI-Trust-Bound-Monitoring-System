import { NavLink } from "react-router-dom";
import { Activity, Shield, Users, Waypoints, Radar, ScrollText, CheckSquare } from "lucide-react";

const links = [
  { to: "/live", label: "Live Feed", icon: Activity },
  { to: "/agents", label: "Agent Registry", icon: Users },
  { to: "/sessions", label: "Sessions", icon: Waypoints },
  { to: "/anomaly", label: "Anomaly", icon: Radar },
  { to: "/policies", label: "Policies", icon: Shield },
  { to: "/audit", label: "Audit Log", icon: ScrollText },
  { to: "/escalations", label: "Escalations", icon: CheckSquare },
];

export default function Sidebar() {
  return (
    <aside className="w-[240px] h-full bg-surface border-r border-border p-4 flex flex-col">
      <div className="text-lg font-semibold tracking-wide mb-4">ATBMS</div>
      <nav className="flex flex-col gap-1">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-2 rounded-md border border-transparent hover:bg-bg ${
                isActive ? "bg-bg border-border text-blue" : "text-text"
              }`
            }
          >
            <l.icon size={16} className="text-muted" />
            <span className="text-sm">{l.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto text-xs text-muted pt-4">
        Trust-Boundary Monitoring
        <div className="mt-1">React + FastAPI + OPA</div>
      </div>
    </aside>
  );
}

