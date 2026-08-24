"use client";

import { useState } from "react";
import { Users } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/states";
import { Pagination } from "@/components/shared/pagination";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCustomers } from "@/hooks/api";
import { formatINR, formatDate } from "@/lib/formatters";

const PAGE_SIZE = 20;

export default function CustomersPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useCustomers(page);

  return (
    <div>
      <PageHeader
        title="Customers"
        description="All customers with their recovery history and failure counts."
      />
      {isLoading ? (
        <LoadingState rows={8} />
      ) : isError ? (
        <ErrorState message="Could not load customers." onRetry={() => refetch()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No customers yet"
          message="Seeded demo customers (Rahul, Priya, etc.) appear here."
          icon={<Users className="size-5" />}
        />
      ) : (
        <>
          <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white">
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-200 hover:bg-transparent">
                    <TableHead>Customer</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead className="text-right">Recovered</TableHead>
                    <TableHead className="text-right">Failures</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((c) => (
                    <TableRow key={c.id} className="border-slate-100">
                      <TableCell>
                        <div className="font-medium text-slate-900">{c.name}</div>
                        <div className="font-mono text-xs text-slate-500">{c.id}</div>
                      </TableCell>
                      <TableCell className="text-slate-600">{c.email ?? "—"}</TableCell>
                      <TableCell className="text-slate-600">{c.phone ?? "—"}</TableCell>
                      <TableCell className="text-right font-medium tabular-nums">
                        {formatINR(c.total_recovered_paise)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{c.failed_payment_count}</TableCell>
                      <TableCell className="text-xs text-slate-500">{formatDate(c.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Pagination page={data.page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
