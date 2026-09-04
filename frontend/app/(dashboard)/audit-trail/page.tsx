"use client";

import { useState } from "react";
import Link from "next/link";
import { ScrollText } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/states";
import { Pagination } from "@/components/shared/pagination";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGlobalAudit } from "@/hooks/api";
import { formatDateTime, titleCase } from "@/lib/formatters";

const PAGE_SIZE = 50;

export default function AuditTrailPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useGlobalAudit(page, PAGE_SIZE);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <PageHeader
        title="Audit Trail"
        description="Every decision, guardrail check, execution and outcome across all events."
      />
      {isLoading ? (
        <LoadingState rows={10} />
      ) : isError ? (
        <ErrorState message="Could not load audit trail." onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No audit entries yet"
          message="Audit entries appear as soon as the pipeline processes an event."
          icon={<ScrollText className="size-5" />}
        />
      ) : (
        <>
          <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white">
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-200 hover:bg-transparent">
                    <TableHead>Time</TableHead>
                    <TableHead>Event</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead>Details</TableHead>
                    <TableHead>AI</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map(
                    (entry) => (
                      <TableRow key={entry.id} className="border-slate-100">
                        <TableCell className="text-xs text-slate-500">{formatDateTime(entry.created_at)}</TableCell>
                        <TableCell>
                          <Link
                            href={`/events/${encodeURIComponent(entry.event_id)}`}
                            className="font-mono text-xs font-medium text-blue-700 hover:underline"
                          >
                            {entry.event_id}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="rounded-full border-slate-200 bg-white text-[11px]">
                            {titleCase(entry.stage)}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-md truncate text-sm text-slate-600">{entry.message ?? "—"}</TableCell>
                        <TableCell>
                          {entry.ai_used ? (
                            <Badge variant="outline" className="rounded-full border-blue-200 bg-blue-50 text-[11px] text-blue-700">
                              AI
                            </Badge>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
