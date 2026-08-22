"""Core domain vocabulary — shared enums used across the whole pipeline.

These values are also the exact strings stored in the DB and returned by the
API, so the frontend can rely on them. Kept in one place so the state machine,
decision engine, guardrails, and audit trail never drift apart.
"""
from __future__ import annotations

from enum import Enum


class EventStatus(str, Enum):
    """Event lifecycle (doc §3.5). The event is the dashboard source of truth
    and only moves forward; terminal states must not regress."""

    detected = "detected"
    analyzing = "analyzing"
    action_selected = "action_selected"
    approval_pending = "approval_pending"
    scheduled = "scheduled"
    executing = "executing"
    waiting_for_outcome = "waiting_for_outcome"
    recovered = "recovered"
    expired = "expired"
    escalated = "escalated"
    closed = "closed"
    failed = "failed"


# Rank used for out-of-order / stale-webhook precedence (doc §3.5/§3.6).
# A later event may never move the status to a lower rank.
STATUS_RANK: dict[str, int] = {
    EventStatus.detected: 0,
    EventStatus.analyzing: 1,
    EventStatus.action_selected: 2,
    EventStatus.approval_pending: 3,
    EventStatus.scheduled: 3,
    EventStatus.executing: 4,
    EventStatus.waiting_for_outcome: 5,
    # terminal states
    EventStatus.recovered: 10,
    EventStatus.expired: 10,
    EventStatus.escalated: 10,
    EventStatus.failed: 10,
    EventStatus.closed: 11,
}

TERMINAL_STATUSES = {
    EventStatus.recovered,
    EventStatus.expired,
    EventStatus.escalated,
    EventStatus.failed,
    EventStatus.closed,
}


class EventType(str, Enum):
    payment_failed = "payment_failed"
    subscription_failed = "subscription_failed"
    subscription_halted = "subscription_halted"
    abandoned_checkout = "abandoned_checkout"


class Cause(str, Enum):
    card_expired = "card_expired"
    insufficient_funds = "insufficient_funds"
    payment_timeout = "payment_timeout"
    bank_declined = "bank_declined"
    checkout_abandoned = "checkout_abandoned"
    unclassified = "unclassified"


class Action(str, Enum):
    """Bounded set of recovery actions the agent may choose from."""

    send_reminder = "send_reminder"
    smart_retry_24h = "smart_retry_24h"
    immediate_retry = "immediate_retry"
    retry_and_notify = "retry_and_notify"
    send_payment_update_link = "send_payment_update_link"
    monitor_native_retry = "monitor_native_retry"
    escalate_to_human = "escalate_to_human"


class RiskTier(str, Enum):
    low = "low"
    medium = "medium"
    safe = "safe"


class ExecutionMechanism(str, Enum):
    """Actual Razorpay mechanism recorded internally (doc §3.4).

    The user-facing label may say 'Smart Retry', but the audit trail records
    the real mechanism. Never implies an immutable failed payment is reopened.
    """

    native_subscription_retry = "native_subscription_retry"
    new_recovery_payment = "new_recovery_payment"
    scheduled_recovery_payment = "scheduled_recovery_payment"
    payment_link = "payment_link"
    checkout = "checkout"
    manual_charge = "manual_charge"
    reminder_only = "reminder_only"


class SubscriptionState(str, Enum):
    active = "active"
    pending = "pending"
    halted = "halted"
    cancelled = "cancelled"
    completed = "completed"
    none = "none"  # one-time payments have no subscription


class AuditStage(str, Enum):
    """Fixed stage vocabulary for the audit trail (doc C5)."""

    detected = "detected"
    analyzed = "analyzed"
    decided = "decided"
    guardrail = "guardrail"
    executed = "executed"
    outcome = "outcome"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    executing = "executing"
    executed = "executed"
    denied = "denied"
    expired = "expired"
    execution_failed = "execution_failed"


class OutcomeStatus(str, Enum):
    pending = "pending"
    recovered = "recovered"
    expired = "expired"
    failed = "failed"
    escalated = "escalated"


class ExecutionMode(str, Enum):
    dry_run = "dry_run"
    live_call = "live_call"


class DataOrigin(str, Enum):
    synthetic = "synthetic"
    live_test_mode = "live_test_mode"
