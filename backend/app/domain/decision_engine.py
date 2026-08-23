"""Deterministic decision engine (doc §3.8 / §3.9).

The LLM may only choose among the actions whitelisted here; known causes,
confidence thresholds, risk tiers and escalation rules are fully
deterministic. `decide()` is pure apart from reading no I/O at all — every
input is passed in — so it is trivially unit-testable per rule-table row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..enums import Action, Cause, EventType, ExecutionMechanism, RiskTier
from .subscription_lifecycle import resolve_subscription_action

POLICY_VERSION = "reviveo-policy-1.0"

# Hard whitelist (doc §3.9). Unknown/unclassified causes permit ONLY escalation.
ALLOWED_ACTIONS_BY_CAUSE: dict[Cause, tuple[Action, ...]] = {
    Cause.card_expired: (
        Action.send_payment_update_link,
        Action.smart_retry_24h,
        Action.send_reminder,
    ),
    Cause.insufficient_funds: (
        Action.smart_retry_24h,
        Action.retry_and_notify,
        Action.send_reminder,
    ),
    Cause.payment_timeout: (
        Action.immediate_retry,
        Action.retry_and_notify,
        Action.send_reminder,
    ),
    Cause.bank_declined: (
        Action.smart_retry_24h,
        Action.send_reminder,
    ),
    Cause.checkout_abandoned: (Action.send_reminder,),
    Cause.unclassified: (),
}

ESCALATION_FALLBACK = Action.escalate_to_human

# Explicit risk tiers (doc §3.9): low → send_reminder/smart_retry_24h,
# medium → retry_and_notify/immediate_retry/send_payment_update_link,
# safe → escalate_to_human.
ACTION_RISK: dict[Action, RiskTier] = {
    Action.send_reminder: RiskTier.low,
    Action.smart_retry_24h: RiskTier.low,
    Action.monitor_native_retry: RiskTier.low,
    Action.retry_and_notify: RiskTier.medium,
    Action.immediate_retry: RiskTier.medium,
    Action.send_payment_update_link: RiskTier.medium,
    Action.escalate_to_human: RiskTier.safe,
}

# How confident classification itself is, per cause (feeds §3.9 bands).
CAUSE_CONFIDENCE: dict[Cause, float] = {
    Cause.card_expired: 0.92,
    Cause.payment_timeout: 0.88,
    Cause.checkout_abandoned: 0.90,
    Cause.insufficient_funds: 0.82,
    Cause.bank_declined: 0.78,
    Cause.unclassified: 0.30,
}

# Internal mechanism vocabulary (doc §3.4) — what Razorpay actually does.
ACTION_MECHANISM: dict[Action, Optional[ExecutionMechanism]] = {
    Action.send_reminder: ExecutionMechanism.reminder_only,
    Action.smart_retry_24h: ExecutionMechanism.scheduled_recovery_payment,
    Action.immediate_retry: ExecutionMechanism.new_recovery_payment,
    Action.retry_and_notify: ExecutionMechanism.new_recovery_payment,
    Action.send_payment_update_link: ExecutionMechanism.checkout,
    Action.monitor_native_retry: ExecutionMechanism.native_subscription_retry,
    Action.escalate_to_human: None,
}


@dataclass(frozen=True)
class Decision:
    action: Action
    mechanism: Optional[ExecutionMechanism]
    confidence: float
    risk_tier: RiskTier
    requires_approval: bool
    reasoning: str
    cause: Cause
    policy_version: str = POLICY_VERSION


def confidence_band(confidence: float, *, low: float, high: float) -> str:
    """§3.9: ≥high → auto-execute if guardrails pass; [low, high) → only
    low-risk actions auto-execute; <low → escalation only."""
    if confidence >= high:
        return "high"
    if confidence >= low:
        return "medium"
    return "low"


def select_action(cause: Cause, attempts_count: int) -> Action:
    """Deterministic pick from the whitelist; progresses across attempts."""
    if cause is Cause.unclassified:
        return ESCALATION_FALLBACK
    allowed = ALLOWED_ACTIONS_BY_CAUSE.get(cause, ())
    if not allowed:
        return ESCALATION_FALLBACK
    if attempts_count == 0:
        return allowed[0]
    if len(allowed) > 1 and attempts_count == 1:
        return allowed[1]
    if Action.send_reminder in allowed:
        return Action.send_reminder
    return ESCALATION_FALLBACK


def decide(
    *,
    event_type: EventType | str,
    subscription_state: Optional[str],
    cause: Cause,
    attempts_count: int,
    low_confidence: float,
    high_confidence: float,
) -> Decision:
    event_type = EventType(event_type)
    base_action = select_action(cause, attempts_count)
    confidence = CAUSE_CONFIDENCE[cause]

    override = resolve_subscription_action(
        event_type=event_type,
        subscription_state=subscription_state,
        cause=cause,
        base_action=base_action,
    )
    note = ""
    if override is not None:
        action, mechanism = override.action, override.mechanism
        confidence = override.confidence if override.confidence is not None else confidence
        note = override.note
    else:
        action, mechanism = base_action, ACTION_MECHANISM[base_action]

    band = confidence_band(confidence, low=low_confidence, high=high_confidence)
    risk = ACTION_RISK[action]

    # §3.9 medium-confidence rule: only low-risk actions may auto-execute.
    requires_approval = band == "medium" and risk is not RiskTier.low

    if band == "low" and action is not ESCALATION_FALLBACK:
        action, mechanism = ESCALATION_FALLBACK, None
        risk = RiskTier.safe
        requires_approval = False
        note = (note + " " if note else "") + (
            f"Cause confidence {confidence:.2f} below threshold {low_confidence:.2f} "
            "— escalating to a human instead of acting."
        )

    reasoning = (
        f"Cause '{cause.value}' classified with confidence {confidence:.2f} ({band} band); "
        f"selected '{action.value}' (risk={risk.value})."
    )
    if note:
        reasoning += f" {note}"

    return Decision(
        action=action,
        mechanism=mechanism,
        confidence=round(confidence, 4),
        risk_tier=risk,
        requires_approval=requires_approval,
        reasoning=reasoning,
        cause=cause,
    )


def as_decision_dict(d: Decision, *, ai_used: bool = False) -> dict:
    return {
        "action": d.action.value,
        "mechanism": d.mechanism.value if d.mechanism else None,
        "confidence": d.confidence,
        "risk_tier": d.risk_tier.value,
        "requires_approval": d.requires_approval,
        "reasoning": d.reasoning,
        "cause": d.cause.value,
        "policy_version": d.policy_version,
        "ai_used": ai_used,
    }
