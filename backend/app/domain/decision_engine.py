"""Deterministic decision policy — the single source of truth for which
action a cause is allowed to produce, and at what confidence/risk it may
auto-execute (doc §3.8, §3.9).

This module is the enforcement point for the "agent proposes, policy
decides" boundary (doc C4/§3.8): whether the caller is the synchronous
deterministic pipeline or the agentic tool-use loop, every proposed action
passes through `decide()`. The LLM never invents an action, changes a
threshold, or bypasses this whitelist — it can only choose among actions this
module already allows for the classified cause, and the confidence/approval
outcome is always recomputed here, never trusted from the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..enums import Action, Cause, EventType, ExecutionMechanism, RiskTier
from . import subscription_lifecycle

POLICY_VERSION = "policy-v1"

# Hard whitelist (doc §3.9). Unclassified causes may only escalate.
ALLOWED_ACTIONS_BY_CAUSE: dict[Cause, tuple[Action, ...]] = {
    Cause.card_expired: (Action.send_payment_update_link, Action.escalate_to_human),
    Cause.insufficient_funds: (Action.smart_retry_24h, Action.send_reminder, Action.escalate_to_human),
    Cause.payment_timeout: (Action.immediate_retry, Action.escalate_to_human),
    Cause.bank_declined: (Action.retry_and_notify, Action.send_payment_update_link, Action.escalate_to_human),
    Cause.checkout_abandoned: (Action.send_reminder, Action.escalate_to_human),
    Cause.unclassified: (Action.escalate_to_human,),
}

# Explicit risk tiers (doc §3.9).
ACTION_RISK: dict[Action, RiskTier] = {
    Action.send_reminder: RiskTier.low,
    Action.smart_retry_24h: RiskTier.low,
    Action.retry_and_notify: RiskTier.medium,
    Action.immediate_retry: RiskTier.medium,
    Action.send_payment_update_link: RiskTier.medium,
    Action.monitor_native_retry: RiskTier.low,
    Action.escalate_to_human: RiskTier.safe,
}

# Default internal execution mechanism per action (doc §3.4) when no
# subscription-lifecycle override and no one-time/subscription context
# distinction applies. `select_execution_mechanism` refines this.
_DEFAULT_MECHANISM_BY_ACTION: dict[Action, Optional[ExecutionMechanism]] = {
    Action.send_reminder: ExecutionMechanism.reminder_only,
    Action.smart_retry_24h: ExecutionMechanism.scheduled_recovery_payment,
    Action.immediate_retry: ExecutionMechanism.new_recovery_payment,
    Action.retry_and_notify: ExecutionMechanism.new_recovery_payment,
    Action.send_payment_update_link: ExecutionMechanism.payment_link,
    Action.monitor_native_retry: ExecutionMechanism.native_subscription_retry,
    Action.escalate_to_human: None,
}

# Deterministic baseline confidence per cause, used when no AI reasoning is
# requested (doc: batch runs default use_ai=False) and as the starting point
# the agent's own confidence is sanity-checked against. Reflects how
# reliably each cause bucket is fixed by its default action in practice —
# an explicit, explainable heuristic, not a black box.
_BASE_CONFIDENCE_BY_CAUSE: dict[Cause, float] = {
    Cause.payment_timeout: 0.90,     # transient — retrying now is very likely to work
    Cause.insufficient_funds: 0.80,  # waiting/reminding is a well-understood fix
    Cause.checkout_abandoned: 0.75,  # a reminder recovers a meaningful share
    Cause.card_expired: 0.65,        # needs the customer to act; less certain
    Cause.bank_declined: 0.55,       # broad bucket, many possible sub-causes
    Cause.unclassified: 0.20,        # always escalate
}

# Public aliases. The underscore-prefixed names above are the canonical
# source of truth used by every live code path (decide()/choose_action()).
# These aliases exist only so backend/app/agent/tools.py — a legacy,
# currently-unwired agent implementation kept for reference (see that
# module's docstring) — doesn't raise ImportError if it's ever imported.
# Audit note (2026-08-24): fixing this import was the cheapest safe fix
# available; it does not mean agent/tools.py is wired into the running app.
ACTION_MECHANISM = _DEFAULT_MECHANISM_BY_ACTION
CAUSE_CONFIDENCE = _BASE_CONFIDENCE_BY_CAUSE


@dataclass(frozen=True)
class Decision:
    action: Action
    execution_mechanism: Optional[ExecutionMechanism]
    confidence: float
    risk_tier: RiskTier
    requires_approval: bool
    reasoning: str
    blocked_invalid_proposal: bool = False


def select_execution_mechanism(
    action: Action, subscription_state: Optional[str]
) -> Optional[ExecutionMechanism]:
    """`send_payment_update_link` uses the subscription card-change flow
    (Checkout) in a subscription context, and a Payment Link for a one-time
    obligation (doc §3.3 final action matrix)."""
    if action == Action.send_payment_update_link and subscription_state not in (None, "none"):
        return ExecutionMechanism.checkout
    return _DEFAULT_MECHANISM_BY_ACTION.get(action)


def compute_confidence(cause: Cause, customer: Optional[dict], attempt_count: int) -> float:
    """Deterministic confidence heuristic (doc: "Confidence level, Customer
    history, ... Previous recovery attempts" are inputs to the decision).

    Starts from the cause's base rate, then adjusts for customer history and
    how many attempts have already been made on this event — repeated
    failures on the same event should reduce confidence, not stay flat.
    """
    confidence = _BASE_CONFIDENCE_BY_CAUSE.get(cause, 0.20)

    if customer:
        if (customer.get("total_recovered_paise") or 0) > 0:
            confidence += 0.05  # has paid successfully before — likely a real customer hitting friction
        if (customer.get("failed_payment_count") or 0) >= 3:
            confidence -= 0.15  # chronic failures — lower trust in an automated fix

    if attempt_count >= 2:
        confidence -= 0.10 * (attempt_count - 1)  # each repeat failure erodes confidence further

    return max(0.0, min(1.0, round(confidence, 4)))


def choose_action(
    *, cause: Cause, event_type: EventType | str, subscription_state: Optional[str]
) -> tuple[Action, Optional[ExecutionMechanism], str, Optional[float]]:
    """Deterministic default action for a cause+context — the policy's own
    pick, used directly by the non-AI pipeline and as the ground truth an
    agent-proposed action is validated against. The fourth element is a
    confidence override (set only when a lifecycle rule is a well-understood
    platform fact rather than a probabilistic guess) — None otherwise."""
    allowed = ALLOWED_ACTIONS_BY_CAUSE.get(cause, (Action.escalate_to_human,))
    base_action = allowed[0]

    override = subscription_lifecycle.resolve_subscription_action(
        event_type=event_type, subscription_state=subscription_state,
        cause=cause, base_action=base_action,
    )
    if override:
        return override.action, override.mechanism, override.note, override.confidence

    mechanism = select_execution_mechanism(base_action, subscription_state)
    reasoning = f"Cause classified as {cause.value}; default policy action is {base_action.value}."
    return base_action, mechanism, reasoning, None


def _requires_approval(confidence: float, risk: RiskTier, high_conf: float, low_conf: float) -> bool:
    if confidence >= high_conf:
        return False  # high confidence — auto-execute if guardrails pass
    if confidence < low_conf:
        return False  # always escalated instead (handled by caller), not a normal "approval"
    # medium confidence: only low-risk actions may auto-execute
    return risk != RiskTier.low


def decide(
    *,
    cause: Cause,
    event_type: EventType | str,
    subscription_state: Optional[str],
    customer: Optional[dict],
    attempt_count: int,
    high_confidence: float,
    low_confidence: float,
    requested_action: Optional[Action] = None,
) -> Decision:
    """The single deterministic authority for action selection (doc §3.8).

    `requested_action` is what an AI agent is proposing (via the
    `check_guardrails`/decision tool). If it isn't in the whitelist for this
    cause, the proposal is rejected outright and replaced with
    `escalate_to_human` — the model cannot invent an action.
    """
    default_action, default_mechanism, default_reasoning, confidence_override = choose_action(
        cause=cause, event_type=event_type, subscription_state=subscription_state,
    )

    allowed = ALLOWED_ACTIONS_BY_CAUSE.get(cause, (Action.escalate_to_human,))
    blocked_invalid = False
    if requested_action is not None:
        if requested_action in allowed:
            action = requested_action
            mechanism = select_execution_mechanism(action, subscription_state)
            reasoning = f"Agent-selected action {action.value} for cause {cause.value} (within policy whitelist)."
            confidence_override = None  # an agent-proposed action isn't the well-understood lifecycle rule
        else:
            action, mechanism, reasoning = Action.escalate_to_human, None, (
                f"Agent proposed '{requested_action.value}' which is not permitted for cause "
                f"'{cause.value}'; escalating to a human instead."
            )
            blocked_invalid = True
            confidence_override = None
    else:
        action, mechanism, reasoning = default_action, default_mechanism, default_reasoning

    confidence = (
        confidence_override if confidence_override is not None
        else compute_confidence(cause, customer, attempt_count)
    )

    # Low confidence always escalates, regardless of which action was chosen
    # (doc §3.9: "<0.50 low → escalation only").
    if confidence < low_confidence and action != Action.escalate_to_human:
        action = Action.escalate_to_human
        mechanism = None
        reasoning = f"Confidence {confidence:.2f} is below the low-confidence threshold — escalating rather than acting automatically."

    risk = ACTION_RISK[action]
    needs_approval = (
        False if action == Action.escalate_to_human
        else _requires_approval(confidence, risk, high_confidence, low_confidence)
    )

    return Decision(
        action=action,
        execution_mechanism=mechanism,
        confidence=confidence,
        risk_tier=risk,
        requires_approval=needs_approval,
        reasoning=reasoning,
        blocked_invalid_proposal=blocked_invalid,
    )
