/** Shared API contract types, mirrored exactly from the Reviveo backend
 * (backend/app/enums.py, db.py rows and api/routes.py response shapes). */

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

export type AuditStage =
  | "detected"
  | "analyzed"
  | "decided"
  | "guardrail"
  | "executed"
  | "outcome";

export type DataOrigin = "synthetic" | "live_test_mode";

/** SQLite booleans arrive as 0/1 in row payloads. */
export type SqlBool = 0 | 1;

export interface LatestDecisionSummary {
  action: ActionName;
  confidence: number;
  risk_tier: RiskTier;
  reasoning: string;
}

export interface EventListItem {
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
  payment_recovered: SqlBool;
  subscription_restored: SqlBool;
  origin: DataOrigin;
  razorpay_payment_id: string | null;
  decision_expires_at: string | null;
  created_at: string;
  updated_at: string;
  latest_decision: LatestDecisionSummary | null;
  attempt_count: number;
}

export interface DecisionRow {
  id: number;
  event_id: string;
  merchant_id: string;
  action: ActionName;
  execution_mechanism: ExecutionMechanism | null;
  confidence: number;
  risk_tier: RiskTier;
  requires_approval: SqlBool;
  reasoning: string | null;
  ai_used: SqlBool;
  policy_version: string | null;
  decision_expires_at: string | null;
  created_at: string;
}

export interface RecoveryAttemptRow {
  recovery_attempt_id: string;
  event_id: string;
  merchant_id: string;
  attempt_number: number;
  action: ActionName;
  execution_mechanism: ExecutionMechanism | "none";
  amount_paise: number;
  status: "pending" | "awaiting_outcome" | "recovered" | "expired" | "failed";
  execution_mode: "dry_run" | "live_call";
  razorpay_ref: string | null;
  reference_id: string | null;
  notes_json: string;
  scheduled_for: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ApprovalSummaryRow {
  id: number;
  status: string;
  proposed_action: ActionName;
  amount_paise: number;
  reason: string | null;
  ai_summary: string | null;
  created_at: string;
}

export interface EventDetail extends EventListItem {
  decisions: DecisionRow[];
  attempts: RecoveryAttemptRow[];
  approvals: ApprovalSummaryRow[];
}

export interface Paginated<T> {
  page: number;
  total: number;
  items: T[];
}

export interface EventsPage extends Paginated<EventListItem> {
  page_size: number;
}

export interface AuditLogRow {
  id: number;
  event_id: string;
  merchant_id: string;
  stage: AuditStage;
  message: string | null;
  payload: Record<string, unknown>;
  ai_used: SqlBool;
  ai_model: string | null;
  ai_latency_ms: number | null;
  fallback_triggered: SqlBool;
  created_at: string;
}

export interface AuditTrailResponse {
  event_id: string;
  status: EventStatus;
  stages: AuditLogRow[];
}

export interface RawWebhookRow {
  razorpay_event_id: string;
  event_name: string | null;
  raw_payload: string;
  status: string;
  received_at: string;
}

export interface RawLogResponse {
  event_id: string;
  webhooks: RawWebhookRow[];
}

export interface Customer {
  id: string;
  merchant_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  total_recovered_paise: number;
  failed_payment_count: number;
  created_at: string;
}

export interface Subscription {
  id: string;
  merchant_id: string;
  customer_id: string;
  plan_name: string | null;
  amount_paise: number;
  state: string;
  created_at: string;
}

export interface CustomerDetail extends Customer {
  subscriptions: Subscription[];
  events: EventListItem[];
}

export interface DailyCounters {
  merchant_id: string;
  day: string;
  recovery_value_paise: number;
  contact_count: number;
}

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
  daily_counters: DailyCounters;
}

export interface GuardrailConfigUpdate {
  environment: "test" | "production";
  allowed_channels: string[];
  recovery_window_days: number;
  high_confidence: number;
  low_confidence: number;
  max_retries: number;
  cooldown_hours: number;
  max_autonomous_recovery_amount_paise: number;
  daily_recovery_value_cap_paise: number;
  daily_contact_cap: number;
}

export interface PendingApproval {
  id: number;
  merchant_id: string;
  event_id: string;
  recovery_attempt_id: string | null;
  proposed_action: ActionName;
  execution_mechanism: ExecutionMechanism | null;
  amount_paise: number;
  reason: string | null;
  ai_summary: string | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface SummaryDeltas {
  revenue_at_risk_pct: number | null;
  recovered_paise_pct: number | null;
  events_processed_pct: number | null;
}

export interface SummaryResponse {
  range: string;
  revenue_at_risk_paise: number;
  recovered_paise: number;
  recovery_rate_pct: number;
  events_processed: number;
  recovered_count: number;
  actions_executed: number;
  action_success_rate_pct: number;
  deltas_vs_previous: SummaryDeltas;
}

export interface TimeseriesPoint {
  day: string;
  at_risk_paise: number;
  recovered_paise: number;
}

export interface StrategyBreakdownRow {
  mechanism: string;
  attempts: number;
  recovered_paise: number;
  recovered_count: number;
  share_pct: number;
}

export interface StrategyPerformanceRow extends StrategyBreakdownRow {
  success_rate_pct: number;
}

export interface HealthResponse {
  status: string;
  run_mode: "synthetic" | "live";
  razorpay_configured: boolean;
  ai_configured: boolean;
}

export interface BatchRunResult {
  n_events: number;
  seed: number;
  use_ai: boolean;
  dry_run: boolean;
  revenue_at_risk_paise: number;
  recovered_paise: number;
  recovered_count: number;
  approval_pending: number;
  statuses: Record<string, number>;
  actions: Record<string, number>;
  causes: Record<string, number>;
  recovery_rate_pct: number;
  label: string;
}

export interface SimulationResult {
  simulation_run_id: string;
  random_seed: number;
  baseline: BatchRunResult;
  treatment: BatchRunResult;
  modeled_incremental_lift_pct_points: number;
  label: string;
  ai_active_in_treatment: boolean;
}

export interface SavedSimulationRun {
  simulation_run_id: string;
  merchant_id: string;
  random_seed: number;
  dataset_version: string;
  agent_version: string;
  policy_version: string;
  n_events: number;
  use_ai: SqlBool;
  dry_run: SqlBool;
  baseline: BatchRunResult | null;
  treatment: BatchRunResult | null;
  created_at: string;
}

export interface MutationResult {
  ok: boolean;
  status?: string;
  detail?: string;
  error?: string;
}

export interface DemoInjectResult {
  ingested: string;
  result: {
    event_id: string;
    status?: string;
    approval_id?: number;
    scheduled?: boolean;
    skipped?: string;
  };
}

export type RangeKey = "24h" | "7d" | "30d" | "all";

export interface EventsQuery {
  status?: EventStatus | "";
  cause?: Cause | "";
  page?: number;
  pageSize?: number;
}
