import pytest

from app.domain import decision_engine as de
from app.enums import Action, Cause, EventType, RiskTier, SubscriptionState


# ── whitelist (doc §3.9) ──────────────────────────────────────────────────────
@pytest.mark.parametrize("cause,expected", [
    (Cause.card_expired, (Action.send_payment_update_link, Action.escalate_to_human)),
    (Cause.insufficient_funds, (Action.smart_retry_24h, Action.send_reminder, Action.escalate_to_human)),
    (Cause.payment_timeout, (Action.immediate_retry, Action.escalate_to_human)),
    (Cause.bank_declined, (Action.retry_and_notify, Action.send_payment_update_link, Action.escalate_to_human)),
    (Cause.checkout_abandoned, (Action.send_reminder, Action.escalate_to_human)),
    (Cause.unclassified, (Action.escalate_to_human,)),
])
def test_allowed_actions_by_cause(cause, expected):
    assert de.ALLOWED_ACTIONS_BY_CAUSE[cause] == expected


def test_unclassified_only_escalates():
    d = de.decide(cause=Cause.unclassified, event_type=EventType.payment_failed,
                   subscription_state=None, customer=None, attempt_count=0,
                   high_confidence=0.85, low_confidence=0.50)
    assert d.action == Action.escalate_to_human


# ── risk tiers (doc §3.9) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("action,tier", [
    (Action.send_reminder, RiskTier.low),
    (Action.smart_retry_24h, RiskTier.low),
    (Action.retry_and_notify, RiskTier.medium),
    (Action.immediate_retry, RiskTier.medium),
    (Action.send_payment_update_link, RiskTier.medium),
    (Action.escalate_to_human, RiskTier.safe),
])
def test_action_risk_tiers(action, tier):
    assert de.ACTION_RISK[action] == tier


# ── confidence policy (doc §3.9) ──────────────────────────────────────────────
def test_high_confidence_auto_executes_without_approval():
    d = de.decide(cause=Cause.payment_timeout, event_type=EventType.payment_failed,
                   subscription_state=None, customer=None, attempt_count=0,
                   high_confidence=0.85, low_confidence=0.50)
    assert d.confidence >= 0.85
    assert d.requires_approval is False
    assert d.action == Action.immediate_retry


def test_medium_confidence_low_risk_auto_executes():
    # insufficient_funds base confidence 0.80 sits in the medium band; its
    # default action (smart_retry_24h) is low risk, so it may auto-execute
    # without approval even though confidence isn't "high".
    d = de.decide(cause=Cause.insufficient_funds, event_type=EventType.payment_failed,
                   subscription_state=None, customer=None, attempt_count=0,
                   high_confidence=0.85, low_confidence=0.50)
    assert 0.50 <= d.confidence < 0.85
    assert d.action == Action.smart_retry_24h
    assert d.risk_tier == RiskTier.low
    assert d.requires_approval is False


def test_medium_confidence_medium_risk_requires_approval():
    d = de.decide(cause=Cause.bank_declined, event_type=EventType.payment_failed,
                   subscription_state=None, customer=None, attempt_count=0,
                   high_confidence=0.85, low_confidence=0.50)
    assert 0.50 <= d.confidence < 0.85
    assert d.requires_approval is True


def test_low_confidence_always_escalates():
    # Force low confidence via repeated attempts eroding the base rate.
    d = de.decide(cause=Cause.bank_declined, event_type=EventType.payment_failed,
                   subscription_state=None, customer={"failed_payment_count": 5},
                   attempt_count=4, high_confidence=0.85, low_confidence=0.50)
    assert d.confidence < 0.50
    assert d.action == Action.escalate_to_human
    assert d.requires_approval is False


def test_agent_cannot_propose_disallowed_action():
    d = de.decide(cause=Cause.card_expired, event_type=EventType.payment_failed,
                   subscription_state=None, customer=None, attempt_count=0,
                   high_confidence=0.85, low_confidence=0.50,
                   requested_action=Action.immediate_retry)  # not whitelisted for card_expired
    assert d.action == Action.escalate_to_human
    assert d.blocked_invalid_proposal is True


# ── subscription lifecycle overrides (doc §3.2/§3.3) ──────────────────────────
def test_pending_subscription_monitors_native_retry():
    d = de.decide(cause=Cause.bank_declined, event_type=EventType.subscription_failed,
                   subscription_state=SubscriptionState.pending.value, customer=None,
                   attempt_count=0, high_confidence=0.85, low_confidence=0.50)
    assert d.action == Action.monitor_native_retry
    assert d.confidence == 0.92


def test_halted_subscription_with_expired_card_uses_checkout():
    d = de.decide(cause=Cause.card_expired, event_type=EventType.subscription_halted,
                   subscription_state=SubscriptionState.halted.value, customer=None,
                   attempt_count=0, high_confidence=0.85, low_confidence=0.50)
    assert d.action == Action.send_payment_update_link
    from app.enums import ExecutionMechanism
    assert d.execution_mechanism == ExecutionMechanism.checkout


def test_halted_subscription_retry_becomes_manual_charge():
    d = de.decide(cause=Cause.bank_declined, event_type=EventType.subscription_halted,
                   subscription_state=SubscriptionState.halted.value, customer=None,
                   attempt_count=0, high_confidence=0.85, low_confidence=0.50)
    from app.enums import ExecutionMechanism
    assert d.action == Action.immediate_retry
    assert d.execution_mechanism == ExecutionMechanism.manual_charge
