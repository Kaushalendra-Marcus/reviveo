"use client";

import { useState } from "react";
import { Layers } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { RangeToggle } from "@/components/shared/range-toggle";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/states";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useStrategies } from "@/hooks/api";
import { formatINR } from "@/lib/formatters";
import type { RangeDays } from "@/lib/types";

export default function StrategiesPage() {
  const [range, setRange] = useState<RangeDays>(30);
  const { data, isLoading, isError, refetch } = useStrategies(range);

  return (
    <div>
      <PageHeader
        title="Strategies"
        description="Performance of each recovery mechanism over the selected window."
        actions={<RangeToggle value={range} onChange={setRange} />}
      />
      {isLoading ? (
        <LoadingState rows={5} />
      ) : isError ? (
        <ErrorState message="Could not load strategies." onRetry={() => refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No strategies executed yet"
          message="Recovery strategies will appear here after Reviveo processes payment failures."
          icon={<Layers className="size-5" />}
        />
      ) : (
        <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-200 hover:bg-transparent">
                  <TableHead>Recovery Strategy</TableHead>
                  <TableHead className="text-right">Attempts</TableHead>
                  <TableHead className="text-right">Recovered</TableHead>
                  <TableHead className="text-right">Recovered count</TableHead>
                  <TableHead className="text-right">Success rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((row) => (
                  <TableRow key={row.mechanism} className="border-slate-100">
                    <TableCell className="font-medium text-slate-900">{row.mechanism}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.attempts}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatINR(row.recovered_paise)}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.recovered_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{Math.round(row.success_rate * 100)}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
