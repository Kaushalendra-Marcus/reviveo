/** Frontend runtime configuration. Defaults keep local dev frictionless;
 * override via environment (NEXT_PUBLIC_*). */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

/** Hackathon-scope auth: single shared key sent as X-API-Key (stated openly
 * in the README; the backend enforces it server-side). */
export const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "reviveo-dev-key";

export const POLL_INTERVAL_MS = 15_000;
export const ACTIVE_EVENT_POLL_MS = 5_000;

export const ACTIVE_EVENT_STATUSES = [
  "approval_pending",
  "scheduled",
  "executing",
  "waiting_for_outcome",
] as const;

export const KNOWN_CHANNELS = ["email", "payment_link"] as const;
export const DISABLED_CHANNELS = ["sms", "whatsapp"] as const;
