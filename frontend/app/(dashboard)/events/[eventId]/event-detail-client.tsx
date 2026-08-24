"use client";

import Link from "next/link";
import { ArrowLeft, Copy } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfidenceBadge } from "@/components/shared/confidence-badge";
import { LoadingState, ErrorState, EmptyState } from "@/components/shared/states";
import { AuditTimeline } from "@/components/audit/audit-timeline";
import { RawLogPanel } from "@/components/audit/raw-log-panel";
import { useAuditTrail, useEventDetail, useRawLog } from "@/hooks/api";
import {
  ACTION_LABELS,
  CAUSE_LABELS,
  EVENT_TYPE_LABELS,
  MECHANISM_LABELS,
  formatDateTime,
  formatINR,
  titleCase,
} from "@/lib/formatters";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-900">{children}</dd>
    </div>
  );
}

export function EventDetailClient({ eventId }: { eventId: string }) {
  const { data: event, isLoading, isError, refetch } = useEventDetail(eventId);
  const { data: auditEntries, isLoading: auditLoading } = useAuditTrail(eventId);
  const { data: rawLog, isLoading: rawLoading } = useRawLog(eventId);

  function copyEventId() {
    navigator.clipboard.writeText(eventId);
    toast.success("Event ID copied");
  }

  return (
    <div>
      <Link href="/events" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900">
        <ArrowLeft className="size-4" />
        Back to Events
      </Link>

      {isLoading ? (
        <LoadingState rows={6} />
      ) : isError || !event ? (
        <ErrorState message="Could not load this event." onRetry={() => refetch()} />
      ) : (
        <>
          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <h1 className="font-mono text-lg font-semibold text-slate-950">{event.event_id}</h1>
              <Button variant="ghost" size="icon" className="size-7" onClick={copyEventId} aria-label="Copy event ID">
                <Copy className="size-3.5 text-slate-400" />
              </Button>
              <StatusBadge status={event.status} />
            </div>
            <p className="text-xs text-slate-400">Detected {formatDateTime(event.created_at)}</p>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="rounded-2xl border-slate-200 shadow-sm lg:col-span-2">
              <CardHeader>
                <CardTitle>Overview</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  <Field label="Customer">{event.customer_id ?? "—"}</Field>
                  <Field label="Subscription">{event.subscription_id ?? "—"}</Field>
                  <Field label="Amount">{formatINR(event.amount_paise)}</Field>
                  <Field label="Event Type">{EVENT_TYPE_LABELS[event.type]}</Field>
                  <Field label="Root Cause">{event.cause ? CAUSE_LABELS[event.cause] : "Not yet classified"}</Field>
                  <Field label="Error Code">{event.error_code ?? "—"}</Field>
                  <Field label="Subscription Before">{event.subscription_state_before ? titleCase(event.subscription_state_before) : "—"}</Field>
                  <Field label="Subscription After">{event.subscription_state_after ? titleCase(event.subscription_state_after) : "—"}</Field>
                  <Field label="Data Origin">{titleCase(event.origin)}</Field>
                  <Field label="Payment Recovered">{event.payment_recovered ? "Yes" : "No"}</Field>
                  <Field label="Subscription Restored">{event.subscription_restored ? "Yes" : "No"}</Field>
                  <Field label="Razorpay Payment ID">
                    {event.razorpay_payment_id ? (
                      <span className="font-mono text-xs">{event.razorpay_payment_id}</span>
                    ) : (
                      "—"
                    )}
                  </Field>
                </dl>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader>
                <CardTitle>Latest Decision</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Field label="Action">{event.latest_action ? ACTION_LABELS[event.latest_action] : "Not yet decided"}</Field>
                {event.latest_confidence !== null ? (
                  <ConfidenceBadge confidence={event.latest_confidence} riskTier={event.latest_risk_tier ?? undefined} />
                ) : null}
              </CardContent>
            </Card>
          </div>

          <Card className="mt-4 rounded-2xl border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle>Recovery Attempts</CardTitle>
            </CardHeader>
            <CardContent>
              {event.attempts.length === 0 ? (
                <EmptyState title="No recovery attempts yet" message="An attempt appears here once an action executes." />
              ) : (
                <div className="overflow-hidden rounded-xl border border-slate-200">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-200 hover:bg-transparent">
                        <TableHead>#</TableHead>
                        <TableHead>Action</TableHead>
                        <TableHead>Mechanism</TableHead>
                        <TableHead className="text-right">Amount</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Mode</TableHead>
                        <TableHead>Reference</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead>Resolved</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {event.attempts.map((a) => (
                        <TableRow key={a.recovery_attempt_id} className="border-slate-100">
                          <TableCell className="text-slate-500">{a.attempt_number}</TableCell>
                          <TableCell>{ACTION_LABELS[a.action]}</TableCell>
                          <TableCell className="text-slate-600">{MECHANISM_LABELS[a.execution_mechanism] ?? a.execution_mechanism}</TableCell>
                          <TableCell className="text-right font-medium tabular-nums">{formatINR(a.amount_paise)}</TableCell>
                          <TableCell className="text-slate-600">{titleCase(a.status)}</TableCell>
                          <TableCell className="text-slate-500">{a.execution_mode === "dry_run" ? "Dry Run" : "Live"}</TableCell>
                          <TableCell className="font-mono text-xs text-slate-500">{a.razorpay_ref ?? "—"}</TableCell>
                          <TableCell className="text-xs text-slate-500">{formatDateTime(a.created_at)}</TableCell>
                          <TableCell className="text-xs text-slate-500">{a.resolved_at ? formatDateTime(a.resolved_at) : "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="mt-4">
            <Tabs defaultValue="audit">
              <TabsList>
                <TabsTrigger value="audit">Audit Trail</TabsTrigger>
                <TabsTrigger value="raw">Raw Log</TabsTrigger>
              </TabsList>
              <TabsContent value="audit" className="mt-4">
                <Card className="rounded-2xl border-slate-200 p-5 shadow-sm">
                  {auditLoading ? <LoadingState rows={4} /> : <AuditTimeline entries={auditEntries ?? []} />}
                </Card>
              </TabsContent>
              <TabsContent value="raw" className="mt-4">
                {rawLoading || !rawLog ? <LoadingState rows={4} /> : <RawLogPanel data={rawLog} />}
              </TabsContent>
            </Tabs>
          </div>
        </>
      )}
    </div>
  );
}
