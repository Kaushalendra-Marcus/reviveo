"use client";

import { useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Customer, Notification, RecoveryAttemptOut } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface ContactRetryCardProps {
  eventId: string;
  customerId: string | null;
  attempts: RecoveryAttemptOut[];
  notifications: Notification[];
  onDone: () => void;
}

/** One-click unblocker for skipped/failed notifications: attach the real
 * contact the webhooks never carried (merchant-authoritative), then
 * re-dispatch. Renders nothing unless a retry can actually do something:
 * latest attempt awaiting outcome + at least one non-delivered row. */
export function ContactRetryCard({
  eventId,
  customerId,
  attempts,
  notifications,
  onDone,
}: ContactRetryCardProps) {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const latest = attempts.length > 0 ? attempts[attempts.length - 1] : null;
  const retryable =
    latest?.status === "awaiting_outcome" &&
    notifications.some((n) => n.status === "skipped" || n.status === "failed");
  if (!retryable) return null;

  async function submit() {
    if (!customerId) {
      setMessage({ kind: "err", text: "No customer is linked to this event yet." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const contact: Record<string, string> = {};
      if (email.trim()) contact.email = email.trim();
      if (phone.trim()) contact.phone = phone.trim();
      if (Object.keys(contact).length > 0) {
        // 422 here means invalid/placeholder contact — surfaced below.
        await api.put<Customer>(`/api/customers/${customerId}`, contact);
      }
      await api.post(`/api/events/${eventId}/notifications/retry`);
      setMessage({ kind: "ok", text: "Re-dispatched — refreshing status below." });
      onDone();
    } catch (error) {
      setMessage({
        kind: "err",
        text: error instanceof ApiError ? error.message : "Retry failed unexpectedly.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4 rounded-2xl border-amber-200 bg-amber-50/60 shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-base text-slate-900">Attach contact &amp; retry</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            type="email"
            placeholder="customer@example.com"
            aria-label="Customer email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={busy}
            className="bg-white"
          />
          <Input
            type="tel"
            placeholder="+919812345678"
            aria-label="Customer phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            disabled={busy}
            className="bg-white"
          />
          <Button onClick={submit} disabled={busy} className="shrink-0">
            {busy ? "Working…" : "Save & retry"}
          </Button>
        </div>
        {message ? (
          <p
            className={`mt-2 text-xs font-medium ${
              message.kind === "ok" ? "text-emerald-700" : "text-red-700"
            }`}
          >
            {message.text}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
