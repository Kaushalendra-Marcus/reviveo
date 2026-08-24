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
    razorpay_ref: Optional[str] = None
    scheduled_for: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


class EventDetailOut(EventOut):
    attempts: list[RecoveryAttemptOut] = Field(default_factory=list)


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
    # Period-over-period deltas vs the immediately preceding window of equal
    # length (doc A1 "deltas_vs_previous"). Relative % change for money/count
    # metrics; percentage-POINT change (not relative %) for the rate metric,
    # so a 5%->50% swing reads as "+45", not a confusing "+900%". None when
    # the prior period had no baseline to compare against (e.g. a new merchant).
    delta_revenue_at_risk_pct: Optional[float] = None
    delta_recovered_pct: Optional[float] = None
    delta_recovery_rate_pct: Optional[float] = None


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


class ApprovalActionIn(BaseModel):
    resolved_by: str = "merchant"


class ApprovalActionOut(BaseModel):
    id: int
    status: str
    event_id: str
    recovery_attempt_id: Optional[str] = None


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
    random_seed: Optional[int] = None


class BatchRunOut(BaseModel):
    simulation_run_id: str
    n_events: int
    use_ai: bool
    dry_run: bool
    baseline: Optional[dict] = None
    treatment: Optional[dict] = None
    created_at: str
    label: str = "Modeled incremental lift — not a measured causal effect (no randomized control group)."


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
