"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/shared/states";
import { MECHANISM_LABELS } from "@/lib/formatters";
import { formatINR } from "@/lib/formatters";
import type { StrategyRow } from "@/lib/types";

const BAR_COLORS = ["#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#1d4ed8", "#1e40af", "#0ea5e9"];

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: StrategyRow = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-slate-900">{MECHANISM_LABELS[row.mechanism] ?? row.mechanism}</p>
      <p className="text-slate-600">
        Recovered: <span className="font-medium text-slate-900">{formatINR(row.recovered_paise)}</span>
      </p>
      <p className="text-slate-600">
        Success rate: <span className="font-medium text-slate-900">{Math.round(row.success_rate * 100)}%</span>
      </p>
      <p className="text-slate-600">
        Attempts: <span className="font-medium text-slate-900">{row.attempts}</span>
      </p>
    </div>
  );
}

export function StrategyBreakdownChart({ data }: { data: StrategyRow[] }) {
  if (data.length === 0) {
    return <EmptyState title="No recovery attempts yet" message="Strategy performance appears once actions have executed." />;
  }

  const sorted = [...data].sort((a, b) => b.recovered_paise - a.recovered_paise);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid horizontal={false} stroke="#e2e8f0" />
        <XAxis
          type="number"
          tickFormatter={(v) => formatINR(v, { compact: true })}
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="mechanism"
          tickFormatter={(m) => MECHANISM_LABELS[m] ?? m}
          tick={{ fontSize: 11, fill: "#475569" }}
          axisLine={false}
          tickLine={false}
          width={150}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "#f1f5f9" }} />
        <Bar dataKey="recovered_paise" radius={[0, 6, 6, 0]} maxBarSize={22}>
          {sorted.map((entry, i) => (
            <Cell key={entry.mechanism} fill={BAR_COLORS[i % BAR_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
