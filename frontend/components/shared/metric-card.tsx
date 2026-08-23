import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDelta } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  icon,
  deltaPct,
  deltaGoodDirection = "up",
  loading,
  hint,
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  /** Percent change vs. the previous period, already computed by the API. */
  deltaPct?: number | null;
  /** Whether an increase is the desired direction for this metric (revenue
   * at risk going UP is bad, so pass "down" for that card). */
  deltaGoodDirection?: "up" | "down";
  loading?: boolean;
  hint?: string;
}) {
  const hasDelta = deltaPct !== undefined && deltaPct !== null;
  const isGood = hasDelta && (deltaGoodDirection === "up" ? deltaPct! >= 0 : deltaPct! <= 0);

  return (
    <Card className="rounded-2xl border-slate-200 shadow-sm">
      <CardContent className="flex items-start justify-between gap-3 px-5 py-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-500">{label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-28" />
          ) : (
            <p className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-950 tabular-nums">
              {value}
            </p>
          )}
          {!loading && hasDelta ? (
            <p
              className={cn(
                "mt-1.5 inline-flex items-center gap-1 text-xs font-medium",
                isGood ? "text-emerald-600" : "text-red-600"
              )}
            >
              {deltaPct! >= 0 ? (
                <ArrowUpRight className="size-3.5" />
              ) : (
                <ArrowDownRight className="size-3.5" />
              )}
              {formatDelta(deltaPct)} vs previous period
            </p>
          ) : !loading && hint ? (
            <p className="mt-1.5 text-xs text-slate-400">{hint}</p>
          ) : null}
        </div>
        {icon ? (
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
            {icon}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
