import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import LiveFeed from "./pages/LiveFeed";
import AgentRegistry from "./pages/AgentRegistry";
import SessionExplorer from "./pages/SessionExplorer";
import AnomalyDashboard from "./pages/AnomalyDashboard";
import PolicyManager from "./pages/PolicyManager";
import AuditLog from "./pages/AuditLog";
import EscalationQueue from "./pages/EscalationQueue";
import { api } from "./lib/api";

function Dot(props: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span className={`w-2 h-2 rounded-full ${props.ok ? "bg-green" : "bg-red"}`} />
      {props.label}
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState<{ [k: string]: boolean }>({});
  const [err, setErr] = useState<string | null>(null);
  const loc = useLocation();

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const h = await api.health();
        if (!alive) return;
        setHealth({
          registry: h.registry.status === "fulfilled" && h.registry.value.ok,
          proxy: h.proxy.status === "fulfilled" && h.proxy.value.ok,
          policy: h.policy.status === "fulfilled" && h.policy.value.ok,
          anomaly: h.anomaly.status === "fulfilled" && h.anomaly.value.ok,
          audit: h.audit.status === "fulfilled" && h.audit.value.ok,
        });
      } catch (e: any) {
        if (!alive) return;
        setErr(e?.message || String(e));
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [loc.pathname]);

  const allOk = useMemo(() => Object.values(health).every(Boolean), [health]);

  return (
    <div className="h-full flex">
      <Sidebar />
      <div className="flex-1 h-full flex flex-col">
        <header className="h-[56px] bg-surface border-b border-border px-4 flex items-center justify-between">
          <div className="text-sm text-muted">
            {allOk ? <span className="text-green">All services healthy</span> : <span className="text-yellow">Degraded</span>}
            {err ? <span className="ml-2 text-red">{err}</span> : null}
          </div>
          <div className="flex gap-4">
            <Dot ok={!!health.proxy} label="proxy" />
            <Dot ok={!!health.registry} label="registry" />
            <Dot ok={!!health.policy} label="policy" />
            <Dot ok={!!health.anomaly} label="anomaly" />
            <Dot ok={!!health.audit} label="audit" />
          </div>
        </header>
        <main className="flex-1 overflow-auto p-4 bg-bg">
          <Routes>
            <Route path="/" element={<Navigate to="/live" replace />} />
            <Route path="/live" element={<LiveFeed />} />
            <Route path="/agents" element={<AgentRegistry />} />
            <Route path="/sessions" element={<SessionExplorer />} />
            <Route path="/anomaly" element={<AnomalyDashboard />} />
            <Route path="/policies" element={<PolicyManager />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/escalations" element={<EscalationQueue />} />
            <Route path="*" element={<Navigate to="/live" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

