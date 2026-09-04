"""Typed request/response models for the REST API. Kept separate from
routes.py so the shape of the API is easy to review at a glance (doc B2:
"one typed response interface per endpoint").
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Events ────────────────────────────────────────────────────────────────────
class EventOut(BaseModel):
    event_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    subscription_id: Optional[str] = None
    invoice_id: Optional[str] = None
    type: str
    cause: Optional[str] = None
    error_code: Optional[str] = None
    amount_paise: int
    status: str
    subscription_state_before: Optional[str] = None
    subscription_state_after: Optional[str] = None
    payment_recovered: bool
    subscription_restored: bool
    origin: str
    razorpay_payment_id: Optional[str] = None
    created_at: str
    updated_at: str
    # Joined latest-decision fields (A1: "paginated list w/ latest decision + outcome joined")
    latest_action: Optional[str] = None
    latest_confidence: Optional[float] = None
    latest_risk_tier: Optional[str] = None


class PaginatedEvents(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int


class AuditEntryOut(BaseModel):
    id: int
    event_id: str
    stage: str
    message: Optional[str] = None
    payload: dict
    ai_used: bool
    ai_model: Optional[str] = None
    ai_latency_ms: Optional[int] = None
    fallback_triggered: bool
    created_at: str


class RecoveryAttemptOut(BaseModel):
    recovery_attempt_id: str
    attempt_number: int
    action: str
    execution_mechanism: str
    amount_paise: int
    status: str
    execution_mode: str
    customer_id: Optional[str] = None
    razorpay_ref: Optional[str] = None
    short_url: Optional[str] = None
    reference_id: Optional[str] = None
    scheduled_for: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


class DecisionOut(BaseModel):
    """One row of an event's full decision history (doc A1 "full record")
    — EventOut/EventDetailOut's latest_* fields are only the most recent of
    these, joined for the list view; this is the complete history."""
    id: int
    action: str
    execution_mechanism: Optional[str] = None
    confidence: float
    risk_tier: str
    requires_approval: bool
    reasoning: Optional[str] = None
    ai_used: bool
    policy_version: Optional[str] = None
    decision_expires_at: Optional[str] = None
    created_at: str


class NotificationOut(BaseModel):
    id: int
    notification_id: str
    merchant_id: str
    event_id: str
    recovery_attempt_id: str
    customer_id: Optional[str] = None
    channel: str
    recipient: str
    subject: Optional[str] = None
    body: str
    status: str
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    created_at: str
    sent_at: Optional[str] = None
    error: Optional[str] = None
    ai_generated: bool = False
    ai_model: Optional[str] = None
    ai_latency_ms: Optional[int] = None


class EventDetailOut(EventOut):
    attempts: list[RecoveryAttemptOut] = Field(default_factory=list)
    decisions: list[DecisionOut] = Field(default_factory=list)
    notifications: list[NotificationOut] = Field(default_factory=list)


class AuditTrailOut(BaseModel):
    """GET /api/events/{id}/audit-trail — doc A1 "5-stage timeline shape"."""
    event_id: str
    stages: list[AuditEntryOut]


class PaginatedAudit(BaseModel):
    """GET /api/audit-trail (global) — wrapped for a real page total,
    consistent with every other paginated list endpoint."""
    items: list[AuditEntryOut]
    total: int
    page: int
    page_size: int


# ── Summary / dashboard ───────────────────────────────────────────────────────
class SummaryOut(BaseModel):
    range_days: int
    revenue_at_risk_paise: int
    recovered_paise: int
    recovered_count: int
    events_processed: int
    actions_executed: int
    actions_succeeded: int
    recovery_rate: float  # recovered_count / events_processed, 0..1
    recovery_rate_pct: Optional[float] = None  # alias in % for legacy tests/docs
    # Period-over-period deltas vs the immediately preceding window of equal
    # length (doc A1 "deltas_vs_previous"). Relative % change for money/count
    # metrics; percentage-POINT change (not relative %) for the rate metric,
    # so a 5%->50% swing reads as "+45", not a confusing "+900%". None when
    # the prior period had no baseline to compare against (e.g. a new merchant).
    delta_revenue_at_risk_pct: Optional[float] = None
    delta_recovered_pct: Optional[float] = None
    delta_recovery_rate_pct: Optional[float] = None

    def model_post_init(self, __context):
        if self.recovery_rate_pct is None:
            object.__setattr__(self, "recovery_rate_pct", round(self.recovery_rate * 100, 2))


class TimeseriesPoint(BaseModel):
    day: str
    amount_paise: int
    count: int


class StrategyBreakdownRow(BaseModel):
    mechanism: str
    attempts: int
    recovered_paise: int
    recovered_count: int
    success_rate: float


# ── Customers ─────────────────────────────────────────────────────────────────
class CustomerOut(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_recovered_paise: int
    failed_payment_count: int
    created_at: str


class CustomerUpdateIn(BaseModel):
    """Merchant-authoritative contact attach. Omitted fields stay unchanged.
    Provided email must be trusted (valid + not a placeholder); provided
    phone must be a plausible dialable number."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class PaginatedCustomers(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int


# ── Guardrails ────────────────────────────────────────────────────────────────
class GuardrailConfigOut(BaseModel):
    merchant_id: str
    environment: str
    recovery_window_days: int
    high_confidence: float
    low_confidence: float
    max_retries: int
    cooldown_hours: int
    max_autonomous_recovery_amount_paise: int
    daily_recovery_value_cap_paise: int
    daily_contact_cap: int
    allowed_channels: list[str]
    updated_at: str
    # The system-wide hard ceiling (settings.max_recovery_attempts) that
    # `max_retries` is actually clamped to at guardrail-check time —
    # surfaced so the UI can warn when a merchant's configured value is
    # silently not the one in effect (AUDIT_REPORT.md "Guardrail hard caps
    # vs UI ranges").
    effective_max_retries: int


class GuardrailConfigIn(BaseModel):
    environment: str = Field(pattern="^(test|production)$")
    recovery_window_days: int = Field(ge=1, le=90)
    high_confidence: float = Field(ge=0.0, le=1.0)
    low_confidence: float = Field(ge=0.0, le=1.0)
    max_retries: int = Field(ge=1, le=10)
    cooldown_hours: int = Field(ge=1, le=168)
    max_autonomous_recovery_amount_paise: int = Field(ge=0)
    daily_recovery_value_cap_paise: int = Field(ge=0)
    daily_contact_cap: int = Field(ge=1, le=100000)
    allowed_channels: list[str]


# ── Approvals ─────────────────────────────────────────────────────────────────
class PendingApprovalOut(BaseModel):
    id: int
    event_id: str
    recovery_attempt_id: Optional[str] = None
    proposed_action: str
    execution_mechanism: Optional[str] = None
    amount_paise: int
    reason: Optional[str] = None
    ai_summary: Optional[str] = None
    status: str
    created_at: str


class PaginatedPendingApprovals(BaseModel):
    items: list[PendingApprovalOut]
    total: int


class ApprovalActionIn(BaseModel):
    resolved_by: str = "merchant"


class ApprovalActionOut(BaseModel):
    id: int
    status: str
    event_id: str
    recovery_attempt_id: Optional[str] = None
    short_url: Optional[str] = None
    ok: bool = True


# ── Strategies ────────────────────────────────────────────────────────────────
class StrategyOut(BaseModel):
    mechanism: str
    attempts: int
    recovered_paise: int
    recovered_count: int
    success_rate: float


# ── Batch ─────────────────────────────────────────────────────────────────────
class BatchRunIn(BaseModel):
    n_events: int = Field(default=50, ge=1, le=2000)
    dry_run: bool = True
    use_ai: bool = False
    random_seed: Optional[int] = Field(default=None, alias="seed")
    # pydantic v2: allow both `seed` and `random_seed`
    model_config = {"populate_by_name": True}
    # Back-compat: tests send `seed`, frontend sends `random_seed`
    # statuses alias for legacy test expectations (baseline/treatment statuses)
    @property
    def effective_seed(self) -> Optional[int]:
        return self.random_seed


class BatchRunOut(BaseModel):
    simulation_run_id: str
    n_events: int
    use_ai: bool
    dry_run: bool
    baseline: Optional[dict] = None
    treatment: Optional[dict] = None
    created_at: str
    label: str = "Modeled incremental lift — not a measured causal effect (no randomized control group)."
    # Back-compat for tests expecting `statuses`
    statuses: Optional[dict] = None

    def model_post_init(self, __context):
        if self.statuses is None and self.treatment is not None:
            # derive a simple statuses summary from treatment
            object.__setattr__(self, "statuses", {
                "baseline": self.baseline,
                "treatment": self.treatment,
            })


# ── Demo (single-event injection, synthetic mode only) ─────────────────────────
class DemoInjectIn(BaseModel):
    type: str = Field(pattern="^(payment_failed|subscription_failed|subscription_halted|abandoned_checkout)$")
    error_code: Optional[str] = None
    customer_id: Optional[str] = None
    subscription_id: Optional[str] = None
    amount_paise: Optional[int] = Field(default=None, ge=0)


class DemoInjectOut(BaseModel):
    ingested: str
    result: dict


# ── Reports (alias of /batch/run using the field names documented in
#    status.md's quick-start; always deterministic/free) ───────────────────────
class ReportSimulateIn(BaseModel):
    n_events: int = Field(default=50, ge=1, le=2000)
    seed: Optional[int] = None
