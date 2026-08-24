"use client";

import Link from "next/link";
import { ChevronRight, Inbox } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfidenceBadge } from "@/components/shared/confidence-badge";
import { EmptyState } from "@/components/shared/states";
import { ACTION_LABELS, CAUSE_LABELS, EVENT_TYPE_LABELS, formatINR, formatRelative } from "@/lib/formatters";
import type { EventOut } from "@/lib/types";

export function EventTable({
  events,
  emptyTitle = "No events yet",
  emptyMessage = "Events will appear here as soon as a payment failure is detected.",
}: {
  events: EventOut[];
  emptyTitle?: string;
  emptyMessage?: string;
}) {
  if (events.length === 0) {
    return <EmptyState title={emptyTitle} message={emptyMessage} icon={<Inbox className="size-5" />} />;
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <Table>
        <TableHeader>
          <TableRow className="border-slate-200 hover:bg-transparent">
            <TableHead>Event</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Root Cause</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Detected</TableHead>
            <TableHead className="w-8" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => (
            <TableRow key={event.event_id} className="border-slate-100">
              <TableCell>
                <Link
                  href={`/events/${encodeURIComponent(event.event_id)}`}
                  className="font-mono text-xs font-medium text-blue-700 hover:underline"
                >
                  {event.event_id}
                </Link>
              </TableCell>
              <TableCell className="text-slate-700">{event.customer_id ?? "—"}</TableCell>
              <TableCell className="text-slate-600">{EVENT_TYPE_LABELS[event.type]}</TableCell>
              <TableCell className="text-slate-600">
                {event.cause ? CAUSE_LABELS[event.cause] : "—"}
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums text-slate-900">
                {formatINR(event.amount_paise)}
              </TableCell>
              <TableCell>
                {event.latest_confidence !== null ? (
                  <ConfidenceBadge
                    confidence={event.latest_confidence}
                    riskTier={event.latest_risk_tier ?? undefined}
                  />
                ) : (
                  <span className="text-xs text-slate-400">—</span>
                )}
              </TableCell>
              <TableCell className="text-slate-600">
                {event.latest_action ? ACTION_LABELS[event.latest_action] : "—"}
              </TableCell>
              <TableCell>
                <StatusBadge status={event.status} />
              </TableCell>
              <TableCell className="text-xs text-slate-500">{formatRelative(event.created_at)}</TableCell>
              <TableCell>
                <Link href={`/events/${encodeURIComponent(event.event_id)}`}>
                  <ChevronRight className="size-4 text-slate-300" />
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
