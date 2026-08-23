import type { ActionName, Cause, EventType, ExecutionMechanism } from "@/lib/types";

/** All money crosses the API in paise (INTEGER) — display in ₹. */
export function formatINR(paise: number, opts?: { compact?: boolean }): string {
  const rupees = paise / 100;
  if (opts?.compact) {
    if (Math.abs(rupees) >= 1_00_00_000) return `₹${(rupees / 1_00_00_000).toFixed(1)}Cr`;
    if (Math.abs(rupees) >= 1_00_000) return `₹${(rupees / 1_00_000).toFixed(1)}L`;
    if (Math.abs(rupees) >= 1_000) return `₹${(rupees / 1_000).toFixed(1)}K`;
    return `₹${rupees.toFixed(0)}`;
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: rupees % 1 === 0 ? 0 : 2,
  }).format(rupees);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-IN", { dateStyle: "medium" });
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 90) return "1 min ago";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

export function formatDelta(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "—";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

export function titleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  payment_failed: "Payment Failed",
  subscription_failed: "Subscription Failed",
  subscription_halted: "Subscription Halted",
  abandoned_checkout: "Abandoned Checkout",
};

export const CAUSE_LABELS: Record<Cause, string> = {
  card_expired: "Card Expired",
  insufficient_funds: "Insufficient Funds",
  payment_timeout: "Payment Timeout",
  bank_declined: "Bank Declined",
  checkout_abandoned: "Checkout Abandoned",
  unclassified: "Unclassified",
};

export const ACTION_LABELS: Record<ActionName, string> = {
  send_reminder: "Send Reminder",
  smart_retry_24h: "Smart Retry (24h)",
  immediate_retry: "Immediate Retry",
  retry_and_notify: "Retry & Notify",
  send_payment_update_link: "Payment Update Link",
  monitor_native_retry: "Monitor Native Retry",
  escalate_to_human: "Escalate to Human",
};

export const MECHANISM_LABELS: Record<string, string> = {
  native_subscription_retry: "Native Subscription Retry",
  new_recovery_payment: "New Recovery Payment",
  scheduled_recovery_payment: "Scheduled Recovery Payment",
  payment_link: "Payment Link",
  checkout: "Checkout",
  manual_charge: "Manual Charge",
  reminder_only: "Reminder Only",
  none: "No Mechanism",
};
