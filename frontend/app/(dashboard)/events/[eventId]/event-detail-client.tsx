"use client";

import Link from "next/link";
import { ArrowLeft, Copy, ExternalLink } from "lucide-react";
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

function aiGenLabel(status: string, aiGenerated: boolean): string {
  // A skipped notification exits before message drafting, so ai_generated=false
  // there means "not generated" — not "fallback". Fallback only applies when
  // a message was actually drafted from the deterministic template.
  if (status === "skipped") return "Not Generated";
  return aiGenerated ? "AI Generated" : "Fallback";
}

function noRecipientLabel(channel: string): string {
  // Backend stores recipient="none" for skipped rows on every channel —
  // label the missing contact for the channel that actually skipped.
  return channel === "sms" ? "No trusted phone on file" : "No trusted email on file";
}

function recipientLabel(channel: string, recipient: string): string {
  return recipient === "none" ? noRecipientLabel(channel) : recipient;
}

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

  // Derive merchant summary helpers from dynamic API data
  const primaryAttempt = event?.attempts && event.attempts.length > 0 ? event.attempts[0] : null;
  const primaryNotification = event?.notifications && event.notifications.length > 0 ? event.notifications[0] : null;

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
          {/* Header */}
          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-slate-950">Payment Failure Detail</h1>
              <StatusBadge status={event.status} />
            </div>
            <p className="text-xs text-slate-500">Detected {formatDateTime(event.created_at)}</p>
          </div>

          {/* Merchant Story Grid - 6 Key Steps */}
          <div className="mb-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {/* 1. What Happened? */}
            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">1. What Happened?</span>
                <CardTitle className="text-base text-slate-900">{EVENT_TYPE_LABELS[event.type] ?? "Payment Failed"}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="text-xs font-medium text-slate-500">Amount: </span>
                  <span className="font-semibold text-slate-900">{formatINR(event.amount_paise)}</span>
                </div>
                <div>
                  <span className="text-xs font-medium text-slate-500">Customer: </span>
                  <span className="text-slate-900 font-mono text-xs">{event.customer_id ?? "—"}</span>
                </div>
              </CardContent>
            </Card>

            {/* 2. Why? */}
            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">2. Why?</span>
                <CardTitle className="text-base text-slate-900">
                  {event.cause ? CAUSE_LABELS[event.cause] : "Not yet classified"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="text-xs font-medium text-slate-500">Classification: </span>
                  <span className="text-slate-700">{event.cause ? titleCase(event.cause) : "Pending analysis"}</span>
                </div>
                {event.error_code ? (
                  <div>
                    <span className="text-xs font-medium text-slate-500">Error Code: </span>
                    <span className="font-mono text-xs text-slate-700">{event.error_code}</span>
                  </div>
                ) : null}
              </CardContent>
            </Card>

            {/* 3. What Reviveo Decided */}
            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">3. What Reviveo Decided</span>
                <CardTitle className="text-base text-slate-900">
                  {event.latest_action ? ACTION_LABELS[event.latest_action] : "Not yet decided"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {event.latest_confidence !== null ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-500">Confidence:</span>
                    <ConfidenceBadge confidence={event.latest_confidence} riskTier={event.latest_risk_tier ?? undefined} />
                  </div>
                ) : (
                  <span className="text-xs text-slate-500">No confidence score available</span>
                )}
              </CardContent>
            </Card>

            {/* 4. What Reviveo Did */}
            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">4. What Reviveo Did</span>
                <CardTitle className="text-base text-slate-900">
                  {primaryAttempt ? ACTION_LABELS[primaryAttempt.action] : event.latest_action ? ACTION_LABELS[event.latest_action] : "Action pending"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {primaryAttempt ? (
                  <>
                    <div className="text-xs text-slate-600">
                      Status: <span className="font-medium text-slate-900">{titleCase(primaryAttempt.status)}</span>
                    </div>
                    {primaryAttempt.short_url ? (
                      <div>
                        <a
                          href={primaryAttempt.short_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:underline"
                        >
                          View Recovery Link <ExternalLink className="size-3" />
                        </a>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <span className="text-xs text-slate-500">No execution recorded yet</span>
                )}
              </CardContent>
            </Card>

            {/* 5. Customer Communication */}
            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">5. Customer Communication</span>
                <CardTitle className="text-base text-slate-900">
                  {primaryNotification ? `${titleCase(primaryNotification.channel)} ${titleCase(primaryNotification.status)}` : "No notification sent"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {primaryNotification ? (
                  <>
                    <div className="text-xs text-slate-600 truncate">
                      To: <span className="font-mono text-slate-800">{primaryNotification.recipient === "none" ? noRecipientLabel(primaryNotification.channel) : primaryNotification.recipient}</span>
                    </div>
                    {primaryNotification.subject ? (
                      <div className="text-xs text-slate-500 truncate" title={primaryNotification.subject}>
                        Subject: <span className="text-slate-700">{primaryNotification.subject}</span>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <span className="text-xs text-slate-500">No customer contact required or triggered</span>
                )}
              </CardContent>
            </Card>

            {/* 6. Result */}
            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">6. Result</span>
                <CardTitle className="text-base text-slate-900">
                  {event.payment_recovered ? "Payment Recovered" : titleCase(event.status)}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="text-xs font-medium text-slate-500">Payment Recovered: </span>
                  <span className={`font-semibold ${event.payment_recovered ? "text-emerald-700" : "text-slate-700"}`}>
                    {event.payment_recovered ? "Yes" : "No"}
                  </span>
                </div>
                <div>
                  <span className="text-xs font-medium text-slate-500">Subscription Restored: </span>
                  <span className="text-slate-700">{event.subscription_restored ? "Yes" : "No"}</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recovery Attempts Details */}
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
                        <TableHead>Execution Mode</TableHead>
                        <TableHead className="text-right">Amount</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Mode</TableHead>
                        <TableHead>Reference</TableHead>
                        <TableHead>Link</TableHead>
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
                          <TableCell className="text-slate-500">{a.execution_mode === "dry_run" ? "Simulation" : "Live"}</TableCell>
                          <TableCell className="font-mono text-xs text-slate-500">
                            {a.reference_id ?? a.razorpay_ref ?? "—"}
                          </TableCell>
                          <TableCell>
                            {a.short_url ? (
                              <a
                                href={a.short_url}
                                target="_blank"
                                rel="noreferrer noopener"
                                className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:underline"
                              >
                                Open <ExternalLink className="size-3" />
                              </a>
                            ) : (
                              <span className="text-xs text-slate-400">—</span>
                            )}
                          </TableCell>
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

          {/* Notifications List if available */}
          {event.notifications && event.notifications.length > 0 ? (
            <Card className="mt-4 rounded-2xl border-slate-200 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span>Customer Communication Log</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-hidden rounded-xl border border-slate-200">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-200 hover:bg-transparent">
                        <TableHead>Channel</TableHead>
                        <TableHead>Recipient</TableHead>
                        <TableHead>Subject</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>AI Gen</TableHead>
                        <TableHead>Sent At</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {event.notifications.map((n) => (
                        <TableRow key={n.notification_id} className="border-slate-100">
                          <TableCell className="font-medium text-slate-700 capitalize">{n.channel}</TableCell>
                          <TableCell className="font-mono text-xs text-slate-700">{recipientLabel(n.channel, n.recipient)}</TableCell>
                          <TableCell className="text-xs text-slate-900 font-medium">{n.subject ?? "—"}</TableCell>
                          <TableCell>
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                              n.status === "sent" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" :
                              n.status === "simulated" ? "bg-blue-50 text-blue-700 border border-blue-200" :
                              n.status === "skipped" ? "bg-slate-100 text-slate-600 border border-slate-200" :
                              "bg-red-50 text-red-700 border border-red-200"
                            }`}>
                              {titleCase(n.status)}
                            </span>
                          </TableCell>
                          <TableCell className="text-xs text-slate-500">{aiGenLabel(n.status, n.ai_generated)}</TableCell>
                          <TableCell className="text-xs text-slate-500">{n.sent_at ? formatDateTime(n.sent_at) : formatDateTime(n.created_at)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {/* Technical Details Section */}
          <Card className="mt-4 rounded-2xl border-slate-200 shadow-sm bg-slate-50/50">
            <CardHeader>
              <CardTitle className="text-base font-semibold text-slate-800">Technical Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div className="col-span-2">
                  <dt className="text-xs font-medium text-slate-500">Event ID</dt>
                  <dd className="mt-0.5 flex items-center gap-1.5 font-mono text-xs text-slate-900">
                    <span>{event.event_id}</span>
                    <Button variant="ghost" size="icon" className="size-6" onClick={copyEventId} aria-label="Copy event ID">
                      <Copy className="size-3 text-slate-400" />
                    </Button>
                  </dd>
                </div>
                <Field label="Error Code">{event.error_code ?? "—"}</Field>
                <Field label="Razorpay Payment ID">
                  {event.razorpay_payment_id ? (
                    <span className="font-mono text-xs">{event.razorpay_payment_id}</span>
                  ) : (
                    "—"
                  )}
                </Field>
                <Field label="Subscription ID">{event.subscription_id ?? "—"}</Field>
                <Field label="Subscription Before">{event.subscription_state_before ? titleCase(event.subscription_state_before) : "—"}</Field>
                <Field label="Subscription After">{event.subscription_state_after ? titleCase(event.subscription_state_after) : "—"}</Field>
                <Field label="Data Origin">{titleCase(event.origin)}</Field>
              </dl>
            </CardContent>
          </Card>

          {/* Audit Trail & Raw Log */}
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
