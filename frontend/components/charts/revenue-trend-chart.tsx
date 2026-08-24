"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate, formatINR } from "@/lib/formatters";
import type { CombinedTimeseriesPoint } from "@/lib/types";

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-slate-900">{formatDate(label)}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="flex items-center gap-1.5 text-slate-600">
          <span className="inline-block size-2 rounded-full" style={{ backgroundColor: p.color }} />
          {p.name}: <span className="font-medium text-slate-900">{formatINR(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

export function RevenueTrendChart({ data }: { data: CombinedTimeseriesPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="recoveredFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#2563eb" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="atRiskFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#94a3b8" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#94a3b8" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="#e2e8f0" />
        <XAxis
          dataKey="day"
          tickFormatter={(d) => formatDate(d)}
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={{ stroke: "#e2e8f0" }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis
          tickFormatter={(v) => formatINR(v, { compact: true })}
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip content={<ChartTooltip />} />
        <Area
          type="monotone"
          dataKey="at_risk_paise"
          name="Revenue at risk"
          stroke="#94a3b8"
          strokeWidth={1.5}
          fill="url(#atRiskFill)"
        />
        <Area
          type="monotone"
          dataKey="recovered_paise"
          name="Recovered"
          stroke="#2563eb"
          strokeWidth={2}
          fill="url(#recoveredFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
