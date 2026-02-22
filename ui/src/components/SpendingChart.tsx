import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import type { SpendingRecord } from "@/types";
import "./SpendingChart.css";

interface Props {
  records: SpendingRecord[];
}

export function SpendingChart({ records }: Props) {
  if (records.length === 0) {
    return <p className="empty-text">No spending data yet. Sync providers to start tracking.</p>;
  }

  // Group by period, sum per provider
  const providers = [...new Set(records.map((r) => r.provider_id))];
  const periods = [...new Set(records.map((r) => r.period))].sort();

  const chartData = periods.map((period) => {
    const point: Record<string, string | number> = { period };
    let total = 0;
    for (const pid of providers) {
      const amount = records
        .filter((r) => r.period === period && r.provider_id === pid)
        .reduce((sum, r) => sum + r.amount, 0);
      point[pid] = Number(amount.toFixed(2));
      total += amount;
    }
    point.total = Number(total.toFixed(2));
    return point;
  });

  const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

  return (
    <div className="spending-chart">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="period" stroke="#94a3b8" fontSize={12} />
          <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(v: number) => `$${v}`} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
            labelStyle={{ color: "#e2e8f0" }}
            formatter={(value: number | undefined) => [`$${(value ?? 0).toFixed(2)}`, undefined]}
          />
          <Legend />
          {providers.map((pid, i) => (
            <Line
              key={pid}
              type="monotone"
              dataKey={pid}
              stroke={colors[i % colors.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              name={pid}
            />
          ))}
          {providers.length > 1 && (
            <Line
              type="monotone"
              dataKey="total"
              stroke="#e2e8f0"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              name="Total"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
