"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Zap } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { MetricCard } from "@/components/shared/metric-card";
import { RangeToggle } from "@/components/shared/range-toggle";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EventTable } from "@/components/events/event-table";
import { RevenueTrendChart } from "@/components/charts/revenue-trend-chart";
import { StrategyBreakdownChart } from "@/components/charts/strategy-breakdown-chart";
import { useEvents, useStrategyBreakdown, useSummary, useTimeseries } from "@/hooks/api";
import { formatINR } from "@/lib/formatters";
import type { RangeDays } from "@/lib/types";

export default function DashboardOverviewPage() {
  const [range, setRange] = useState<RangeDays>(30);

  const summary = useSummary(range);
  const timeseries = useTimeseries(range);
  const strategyBreakdown = useStrategyBreakdown(range);
  const recentEvents = useEvents({ page: 1, pageSize: 8 });

  return (
    <div>
      <PageHeader
        title="Overview"
        description="How Reviveo is doing right now."
        actions={<RangeToggle value={range} onChange={setRange} />}
      />

      {summary.isError ? (
        <ErrorState message="Could not load summary metrics." onRetry={() => summary.refetch()} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label="Revenue at Risk"
            value={summary.data ? formatINR(summary.data.revenue_at_risk_paise) : "—"}
            icon={<AlertTriangle className="size-4" />}
            loading={summary.isLoading}
            hint={`${summary.data?.events_processed ?? 0} events`}
            deltaPct={summary.data?.delta_revenue_at_risk_pct}
            deltaGoodDirection="down"
          />
          <MetricCard
            label="Recovered"
            value={summary.data ? formatINR(summary.data.recovered_paise) : "—"}
            icon={<CheckCircle2 className="size-4" />}
            loading={summary.isLoading}
            hint={`${summary.data?.recovered_count ?? 0} payments`}
            deltaPct={summary.data?.delta_recovered_pct}
          />
          <MetricCard
            label="Recovery Rate"
            value={summary.data ? `${Math.round(summary.data.recovery_rate * 100)}%` : "—"}
            icon={<ArrowUpRight className="size-4" />}
            loading={summary.isLoading}
            hint="of processed events"
            deltaPct={summary.data?.delta_recovery_rate_pct}
          />
          <MetricCard
            label="Actions Executed"
            value={summary.data ? String(summary.data.actions_executed) : "—"}
            icon={<Zap className="size-4" />}
            loading={summary.isLoading}
            hint={`${summary.data?.actions_succeeded ?? 0} succeeded`}
          />
        </div>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="rounded-2xl border-slate-200 shadow-sm lg:col-span-2">
          <CardHeader>
            <CardTitle>Recovered vs. Revenue at Risk</CardTitle>
          </CardHeader>
          <CardContent>
            {timeseries.isLoading ? (
              <LoadingState rows={1} className="h-[280px]" />
            ) : timeseries.isError ? (
              <ErrorState message="Could not load the trend chart." onRetry={() => timeseries.refetch()} />
            ) : (
              <RevenueTrendChart data={timeseries.data ?? []} />
            )}
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle>Recovery by Strategy</CardTitle>
          </CardHeader>
          <CardContent>
            {strategyBreakdown.isLoading ? (
              <LoadingState rows={1} className="h-[280px]" />
            ) : strategyBreakdown.isError ? (
              <ErrorState message="Could not load strategy breakdown." onRetry={() => strategyBreakdown.refetch()} />
            ) : (
              <StrategyBreakdownChart data={strategyBreakdown.data ?? []} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4 rounded-2xl border-slate-200 shadow-sm">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Recent Events</CardTitle>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/events">View all</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {recentEvents.isLoading ? (
            <LoadingState rows={5} />
          ) : recentEvents.isError ? (
            <ErrorState message="Could not load recent events." onRetry={() => recentEvents.refetch()} />
          ) : (
            <EventTable events={recentEvents.data?.items ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
