import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";

const colors: Record<string, string> = {
  drift: "#bc8cff",
  temporal: "#d29922",
  stac: "#f85149",
  coherence: "#58a6ff",
};

export default function AnomalyChart(props: { points: { timestamp: string; module: string; score: number }[] }) {
  // pivot points into time buckets
  const map = new Map<string, any>();
  for (const p of props.points) {
    const k = p.timestamp.slice(0, 16);
    const row = map.get(k) || { t: k };
    row[p.module] = p.score;
    map.set(k, row);
  }
  const data = Array.from(map.values()).sort((a, b) => (a.t < b.t ? -1 : 1));

  return (
    <div className="bg-surface border border-border rounded-lg p-3">
      <div className="text-sm font-semibold mb-2">Anomaly scores (last alerts)</div>
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <XAxis dataKey="t" tick={{ fill: "#7d8590", fontSize: 10 }} />
            <YAxis tick={{ fill: "#7d8590", fontSize: 10 }} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d", color: "#e6edf3" }} />
            <Legend />
            {Object.keys(colors).map((k) => (
              <Line key={k} type="monotone" dataKey={k} stroke={colors[k]} dot={false} strokeWidth={2} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

