import { useEffect, useMemo, useState } from "react";
import AnomalyChart from "../components/AnomalyChart";
import StatCard from "../components/StatCard";
import { api, type Agent, type Alert } from "../lib/api";

export default function AnomalyDashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [baselines, setBaselines] = useState<any[]>([]);
  const [history, setHistory] = useState<{ timestamp: string; module: string; score: number }[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const agentName = useMemo(() => {
    const m = new Map(agents.map((a) => [a.agent_id, a.display_name]));
    return (id?: string | null) => (id && m.get(id)) || id || "—";
  }, [agents]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      setErr(null);
      try {
        const [aa, al, bl] = await Promise.all([api.listAgents(), api.listAlerts(false), api.baselines()]);
        if (!alive) return;
        setAgents(aa);
        setAlerts(al);
        setBaselines(bl);
        if (aa[0]) {
          const h = await api.scoreHistory(aa[0].agent_id);
          setHistory(h.points || []);
        }
      } catch (e: any) {
        if (!alive) return;
        setErr(e?.message || String(e));
      }
    };
    load();
    const id = setInterval(load, 10000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = { drift: 0, temporal: 0, stac: 0, coherence: 0 };
    for (const a of alerts) c[a.module] = (c[a.module] || 0) + 1;
    return c;
  }, [alerts]);

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <div className="text-xl font-semibold">Anomaly Dashboard</div>
        {err ? <div className="text-xs text-red mt-1">{err}</div> : <div className="text-xs text-muted mt-1">{alerts.length} active alerts</div>}
      </div>

      <div className="col-span-12 grid grid-cols-4 gap-4">
        <StatCard title="Baseline Drift" value={counts.drift} accent="purple" />
        <StatCard title="Temporal" value={counts.temporal} accent="yellow" />
        <StatCard title="STAC" value={counts.stac} accent="red" />
        <StatCard title="Coherence" value={counts.coherence} accent="blue" />
      </div>

      <div className="col-span-7">
        <div className="bg-surface border border-border rounded-lg p-3">
          <div className="text-sm font-semibold mb-2">Active Alerts</div>
          <div className="flex flex-col gap-2">
            {alerts.slice(0, 30).map((a) => (
              <div key={a.id} className="bg-bg border border-border rounded p-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs">
                    <span className="text-yellow">{a.alert_type}</span> <span className="text-muted">({a.module})</span>
                  </div>
                  <div className="text-xs text-muted">{new Date(a.timestamp).toLocaleString()}</div>
                </div>
                <div className="text-xs text-muted mt-1">{agentName(a.agent_id)}</div>
                <div className="text-xs mt-2">{a.detail}</div>
                <div className="mt-2 flex items-center justify-between">
                  <div className="text-xs text-muted">
                    score <span className="text-text">{Math.round(a.score)}</span>/100
                  </div>
                  <button
                    className="text-xs px-2 py-1 rounded border border-border hover:border-blue/60"
                    onClick={async () => {
                      await api.dismissAlert(a.id);
                      setAlerts((prev) => prev.filter((x) => x.id !== a.id));
                    }}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
            {alerts.length === 0 ? <div className="text-xs text-muted">No alerts.</div> : null}
          </div>
        </div>

        <div className="mt-4">
          <AnomalyChart points={history} />
        </div>
      </div>

      <div className="col-span-5">
        <div className="bg-surface border border-border rounded-lg p-3">
          <div className="text-sm font-semibold mb-2">Baselines</div>
          <div className="overflow-auto max-h-[640px]">
            <table className="w-full text-left">
              <thead className="text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="py-2 pr-2">Agent</th>
                  <th className="py-2 pr-2">Tool</th>
                  <th className="py-2 pr-2">Mean/hr</th>
                  <th className="py-2 pr-2">Std</th>
                  <th className="py-2 pr-2">Samples</th>
                  <th className="py-2 pr-2"></th>
                </tr>
              </thead>
              <tbody>
                {baselines.map((b) => (
                  <tr key={`${b.agent_id}-${b.tool_name}`} className="border-b border-border">
                    <td className="py-2 pr-2 text-xs">{agentName(b.agent_id)}</td>
                    <td className="py-2 pr-2 text-xs font-mono">{b.tool_name}</td>
                    <td className="py-2 pr-2 text-xs">{b.mean_hourly.toFixed(2)}</td>
                    <td className="py-2 pr-2 text-xs">{b.stddev_hourly.toFixed(2)}</td>
                    <td className="py-2 pr-2 text-xs">{b.sample_count}</td>
                    <td className="py-2 pr-2">
                      <button
                        className="text-xs px-2 py-1 rounded border border-border hover:border-blue/60"
                        onClick={async () => {
                          await api.resetBaselines(b.agent_id);
                          setBaselines((prev) => prev.filter((x) => x.agent_id !== b.agent_id));
                        }}
                      >
                        Reset
                      </button>
                    </td>
                  </tr>
                ))}
                {baselines.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-3 text-xs text-muted">
                      No baselines learned yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-surface border border-border rounded-lg p-3 mt-4">
          <div className="text-sm font-semibold mb-2">STAC Pattern Library</div>
          <div className="text-xs text-muted">list_directory → read_file → http_request</div>
          <div className="text-xs text-muted mt-1">run_query → write_file → http_request</div>
          <div className="text-xs text-muted mt-1">bash_exec → read_file → http_request</div>
          <div className="text-xs text-muted mt-1">read_file → read_file → read_file → http_request</div>
        </div>
      </div>
    </div>
  );
}

