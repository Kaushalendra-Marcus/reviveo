/** Shared API contract types, mirrored field-for-field from the Reviveo
 * backend (backend/app/enums.py and backend/app/api/schemas.py). Only fields
 * the API actually serializes are declared here — several endpoints carry
 * more columns internally than they expose; adding a field here that the
 * backend doesn't return would silently lie about what's on the wire. */

export type EventStatus =
  | "detected"
  | "analyzing"
  | "action_selected"
  | "approval_pending"
  | "scheduled"
  | "executing"
  | "waiting_for_outcome"
  | "recovered"
  | "expired"
  | "escalated"
  | "closed"
  | "failed";

export type EventType =
  | "payment_failed"
  | "subscription_failed"
  | "subscription_halted"
  | "abandoned_checkout";

export type Cause =
  | "card_expired"
  | "insufficient_funds"
  | "payment_timeout"
  | "bank_declined"
  | "checkout_abandoned"
  | "unclassified";

export type ActionName =
  | "send_reminder"
  | "smart_retry_24h"
  | "immediate_retry"
  | "retry_and_notify"
  | "send_payment_update_link"
  | "monitor_native_retry"
  | "escalate_to_human";

export type RiskTier = "low" | "medium" | "safe";

export type ExecutionMechanism =
  | "native_subscription_retry"
  | "new_recovery_payment"
  | "scheduled_recovery_payment"
  | "payment_link"
  | "checkout"
  | "manual_charge"
  | "reminder_only";

export type AuditStage = "detected" | "analyzed" | "decided" | "guardrail" | "executed" | "outcome";

export type DataOrigin = "synthetic" | "live_test_mode";

export type RecoveryAttemptStatus = "pending" | "scheduled" | "awaiting_outcome" | "recovered" | "expired" | "failed";

export type ExecutionMode = "dry_run" | "live_call";

/** GET /api/events, GET /api/events/{id} — schemas.EventOut. The
 * latest_* fields are the joined most-recent `decisions` row for this
 * event; all three are null together iff no decision has been made yet. */
export interface EventOut {
  event_id: string;
  merchant_id: string;
  customer_id: string | null;
  subscription_id: string | null;
  invoice_id: string | null;
  type: EventType;
  cause: Cause | null;
  error_code: string | null;
  amount_paise: number;
  status: EventStatus;
  subscription_state_before: string | null;
  subscription_state_after: string | null;
  payment_recovered: boolean;
  subscription_restored: boolean;
  origin: DataOrigin;
  razorpay_payment_id: string | null;
  created_at: string;
  updated_at: string;
  latest_action: ActionName | null;
  latest_confidence: number | null;
  latest_risk_tier: RiskTier | null;
}

/** schemas.RecoveryAttemptOut — narrower than the `recovery_attempts`
 * table: no event_id/merchant_id/notes_json on the wire. `reference_id`
 * (rvo_…) is the §3.7 outbound correlation key; `razorpay_ref` (plink_…)
 * is Razorpay's own link id. */
export interface RecoveryAttemptOut {
  recovery_attempt_id: string;
  attempt_number: number;
  action: ActionName;
  execution_mechanism: ExecutionMechanism;
  amount_paise: number;
  status: RecoveryAttemptStatus;
  execution_mode: ExecutionMode;
  razorpay_ref: string | null;
  short_url: string | null;
  reference_id: string | null;
  scheduled_for: string | null;
  created_at: string;
  resolved_at: string | null;
}

/** schemas.DecisionOut — one row of an event's full decision history. */
export interface DecisionOut {
  id: number;
  action: ActionName;
  execution_mechanism: ExecutionMechanism | null;
  confidence: number;
  risk_tier: RiskTier;
  requires_approval: boolean;
  reasoning: string | null;
  ai_used: boolean;
  policy_version: string | null;
  decision_expires_at: string | null;
  created_at: string;
}

/** GET /api/events/{id} — schemas.EventDetailOut = EventOut + the full
 * recovery_attempts and decisions histories for this event. */
export interface EventDetail extends EventOut {
  attempts: RecoveryAttemptOut[];
  decisions: DecisionOut[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type EventsPage = Paginated<EventOut>;

/** schemas.AuditEntryOut — the entry shape shared by both audit endpoints.
 * `GET /api/events/{id}/audit-trail` wraps them as `{event_id, stages}`;
 * `GET /api/audit-trail` returns `{items, total, page, page_size}`. */
export interface AuditEntryOut {
  id: number;
  event_id: string;
  stage: AuditStage;
  message: string | null;
  payload: Record<string, unknown>;
  ai_used: boolean;
  ai_model: string | null;
  ai_latency_ms: number | null;
  fallback_triggered: boolean;
  created_at: string;
}

/** GET /api/events/{id}/raw-log returns a raw dict, not a pydantic schema —
 * every field is a straight `db.py` row, so SQLite booleans arrive as 0/1
 * and `notes_json`/`payload` are pre-parsed only where db.py already does
 * so (audit rows), and left as strings where it doesn't (nothing else
 * here). This is intentionally the unfiltered internal state, for the
 * "raw log" debug view — it will show fields the typed endpoints hide. */
export interface RawLogEventRow {
  event_id: string;
  merchant_id: string;
  customer_id: string | null;
  subscription_id: string | null;
  invoice_id: string | null;
  type: string;
  cause: string | null;
  error_code: string | null;
  amount_paise: number;
  status: string;
  subscription_state_before: string | null;
  subscription_state_after: string | null;
  payment_recovered: 0 | 1;
  subscription_restored: 0 | 1;
  origin: string;
  razorpay_payment_id: string | null;
  decision_expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RawLogAuditRow {
  id: number;
  event_id: string;
  merchant_id: string;
  stage: string;
  message: string | null;
  payload: Record<string, unknown>;
  ai_used: 0 | 1;
  ai_model: string | null;
  ai_latency_ms: number | null;
  fallback_triggered: 0 | 1;
  created_at: string;
}

export interface RawLogDecisionRow {
  id: number;
  event_id: string;
  merchant_id: string;
  action: string;
  execution_mechanism: string | null;
  confidence: number;
  risk_tier: string;
  requires_approval: 0 | 1;
  reasoning: string | null;
  ai_used: 0 | 1;
  policy_version: string | null;
  decision_expires_at: string | null;
  created_at: string;
}

export interface RawLogAttemptRow {
  recovery_attempt_id: string;
  event_id: string;
  merchant_id: string;
  attempt_number: number;
  action: string;
  execution_mechanism: string;
  amount_paise: number;
  status: string;
  execution_mode: string;
  razorpay_ref: string | null;
  reference_id: string | null;
  notes_json: string;
  scheduled_for: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface RawLogResponse {
  event: RawLogEventRow;
  audit_log: RawLogAuditRow[];
  decisions: RawLogDecisionRow[];
  recovery_attempts: RawLogAttemptRow[];
}

/** schemas.CustomerOut. No merchant_id on the wire, and there is no
 * customer-detail/customer-events endpoint — the list row is all the API
 * exposes for a customer. */
export interface Customer {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  total_recovered_paise: number;
  failed_payment_count: number;
  created_at: string;
}

export type CustomersPage = Paginated<Customer>;

/** schemas.GuardrailConfigOut (GET/PUT /api/guardrails). */
export interface GuardrailConfig {
  merchant_id: string;
  environment: "test" | "production";
  recovery_window_days: number;
  high_confidence: number;
  low_confidence: number;
  max_retries: number;
  cooldown_hours: number;
  max_autonomous_recovery_amount_paise: number;
  daily_recovery_value_cap_paise: number;
  daily_contact_cap: number;
  allowed_channels: string[];
  updated_at: string;
  /** min(max_retries, system ceiling settings.max_recovery_attempts) — the
   * value actually enforced; when smaller than max_retries the merchant's
   * configured value is silently clamped and the UI should say so. */
  effective_max_retries: number;
}

/** schemas.GuardrailConfigIn (PUT body) — every field is required; the API
 * has no PATCH, so a partial update is not possible and the form must
 * always submit the complete config. */
export interface GuardrailConfigInput {
  environment: "test" | "production";
  recovery_window_days: number;
  high_confidence: number;
  low_confidence: number;
  max_retries: number;
  cooldown_hours: number;
  max_autonomous_recovery_amount_paise: number;
  daily_recovery_value_cap_paise: number;
  daily_contact_cap: number;
  allowed_channels: string[];
}

/** schemas.PendingApprovalOut. GET /api/guardrails/pending-approvals
 * returns `{items, total}`. */
export interface PendingApproval {
  id: number;
  event_id: string;
  recovery_attempt_id: string | null;
  proposed_action: ActionName;
  execution_mechanism: ExecutionMechanism | null;
  amount_paise: number;
  reason: string | null;
  ai_summary: string | null;
  status: "pending" | "approved" | "executing" | "executed" | "denied" | "expired" | "execution_failed";
  created_at: string;
}

/** schemas.ApprovalActionOut — response of both approve/deny endpoints.
 * `ok:false` marks a discarded/failed execution (e.g. the event reached a
 * terminal state while the approval sat in the queue). */
export interface ApprovalActionResult {
  id: number;
  status: string;
  event_id: string;
  recovery_attempt_id: string | null;
  short_url: string | null;
  ok: boolean;
}

/** schemas.SummaryOut. `recovery_rate` is a 0..1 fraction;
 * `recovery_rate_pct` is the same value pre-multiplied for convenience.
 * The delta_* fields are period-over-period comparisons against the
 * immediately preceding window of equal length — relative % change for
 * money metrics, percentage-POINT change for the rate; `null` when the
 * prior period had no data to compare against. */
export interface SummaryResponse {
  range_days: number;
  revenue_at_risk_paise: number;
  recovered_paise: number;
  recovered_count: number;
  events_processed: number;
  actions_executed: number;
  actions_succeeded: number;
  recovery_rate: number;
  recovery_rate_pct: number | null;
  delta_revenue_at_risk_pct: number | null;
  delta_recovered_pct: number | null;
  delta_recovery_rate_pct: number | null;
}

/** schemas.TimeseriesPoint — one metric per point. GET
 * /api/summary/timeseries takes `metric=recovered|at_risk` and must be
 * called once per series; there is no combined-series endpoint. */
export interface TimeseriesPoint {
  day: string;
  amount_paise: number;
  count: number;
}

/** Client-side merge of the two timeseries calls, keyed by day, for charting. */
export interface CombinedTimeseriesPoint {
  day: string;
  recovered_paise: number;
  at_risk_paise: number;
}

/** schemas.StrategyBreakdownRow / schemas.StrategyOut — identical shape,
 * returned by /api/summary/strategy-breakdown and /api/strategies
 * respectively. `success_rate` is a 0..1 fraction. */
export interface StrategyRow {
  mechanism: string;
  attempts: number;
  recovered_paise: number;
  recovered_count: number;
  success_rate: number;
}

export interface HealthResponse {
  status: string;
  run_mode: "synthetic" | "live";
  razorpay_configured: boolean;
  ai_configured: boolean;
}

/** Real shape of `batch_runner._run_baseline` / `_run_treatment` — the
 * schema types `baseline`/`treatment` as a bare `dict`, so this is sourced
 * from backend/app/batch/batch_runner.py directly, not from schemas.py. */
export interface BatchBaselineResult {
  n_events: number;
  total_at_risk_paise: number;
  recovered_paise: number;
  recovered_count: number;
  recovery_rate: number;
}

export interface BatchTreatmentResult extends BatchBaselineResult {
  executed: number;
  scheduled: number;
  pending_approval: number;
  pending_approval_value_paise: number;
  expired: number;
}

/** schemas.BatchRunOut — response of POST /api/batch/run and
 * GET /api/batch/last-summary (which itself returns this-or-null). */
export interface BatchRunResult {
  simulation_run_id: string;
  n_events: number;
  use_ai: boolean;
  dry_run: boolean;
  baseline: BatchBaselineResult | null;
  treatment: BatchTreatmentResult | null;
  created_at: string;
  label: string;
}

export interface BatchRunInput {
  n_events: number;
  dry_run: boolean;
  use_ai: boolean;
  random_seed?: number | null;
}

/** UI-facing day-range selector — mapped straight to the `?range=` integer
 * (days) query param the backend actually expects (`ge=1, le=365`). */
export type RangeDays = 7 | 30 | 90;

export interface EventsQuery {
  status?: EventStatus | "";
  cause?: Cause | "";
  origin?: DataOrigin | "";
  page?: number;
  pageSize?: number;
}
