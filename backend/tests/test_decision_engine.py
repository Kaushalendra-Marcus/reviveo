"""One test per decision-engine rule-table row (doc A6)."""
from __future__ import annotations

import pytest

from app.domain.decision_engine import (
    ACTION_RISK,
    ALLOWED_ACTIONS_BY_CAUSE,
    confidence_band,
    decide,
    select_action,
)
from app.enums import Action, Cause, RiskTier


class TestWhitelist:
    def test_unclassified_only_permits_escalation(self):
        assert ALLOWED_ACTIONS_BY_CAUSE[Cause.unclassified] == ()
        assert select_action(Cause.unclassified, 0) is Action.escalate_to_human

    def test_every_cause_whitelist_actions_are_known_risk_tiers(self):
        for cause, actions in ALLOWED_ACTIONS_BY_CAUSE.items():
            for a in actions:
                assert a in ACTION_RISK

    def test_card_expired_primary_is_payment_update_link(self):
        assert select_action(Cause.card_expired, 0) is Action.send_payment_update_link

    def test_insufficient_funds_primary_is_smart_retry(self):
        assert select_action(Cause.insufficient_funds, 0) is Action.smart_retry_24h

    def test_payment_timeout_primary_is_immediate_retry(self):
        assert select_action(Cause.payment_timeout, 0) is Action.immediate_retry

    def test_bank_declined_primary_is_smart_retry(self):
        assert select_action(Cause.bank_declined, 0) is Action.smart_retry_24h

    def test_checkout_abandoned_only_reminder(self):
        assert ALLOWED_ACTIONS_BY_CAUSE[Cause.checkout_abandoned] == (Action.send_reminder,)
        d = decide(event_type="payment_failed", subscription_state=None,
                   cause=Cause.checkout_abandoned, attempts_count=3,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.action is Action.send_reminder


class TestProgression:
    def test_second_attempt_picks_secondary_action(self):
        secondary = ALLOWED_ACTIONS_BY_CAUSE[Cause.card_expired][1]
        assert select_action(Cause.card_expired, 1) is secondary

    def test_later_attempts_fall_back_to_reminder_when_allowed(self):
        assert select_action(Cause.payment_timeout, 5) is Action.send_reminder

    def test_exhausted_non_reminder_whitelist_escalates(self):
        # bank_declined has no send_reminder... it does. checkout_abandoned does too.
        # Use a cause whose whitelist lacks reminder by construction:
        assert select_action(Cause.unclassified, 9) is Action.escalate_to_human


class TestRiskTiers:
    @pytest.mark.parametrize("action,tier", [
        (Action.send_reminder, RiskTier.low),
        (Action.smart_retry_24h, RiskTier.low),
        (Action.retry_and_notify, RiskTier.medium),
        (Action.immediate_retry, RiskTier.medium),
        (Action.send_payment_update_link, RiskTier.medium),
        (Action.escalate_to_human, RiskTier.safe),
    ])
    def test_explicit_risk_table(self, action, tier):
        assert ACTION_RISK[action] is tier


class TestConfidenceBands:
    def test_high_medium_low_boundaries(self):
        assert confidence_band(0.85, low=0.5, high=0.85) == "high"
        assert confidence_band(0.849, low=0.5, high=0.85) == "medium"
        assert confidence_band(0.50, low=0.5, high=0.85) == "medium"
        assert confidence_band(0.499, low=0.5, high=0.85) == "low"

    def test_medium_band_medium_risk_requires_approval(self):
        # bank_declined confidence 0.78 → medium band; smart_retry is low risk
        d = decide(event_type="payment_failed", subscription_state=None,
                   cause=Cause.bank_declined, attempts_count=0,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.requires_approval is False
        # force medium-risk action into medium band via insufficient_funds retry_and_notify
        d2 = decide(event_type="payment_failed", subscription_state=None,
                    cause=Cause.insufficient_funds, attempts_count=1,
                    low_confidence=0.5, high_confidence=0.85)
        assert d2.action is Action.retry_and_notify
        assert d2.risk_tier is RiskTier.medium
        assert d2.requires_approval is True

    def test_low_confidence_always_escalates(self):
        d = decide(event_type="payment_failed", subscription_state=None,
                   cause=Cause.unclassified, attempts_count=0,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.action is Action.escalate_to_human
        assert d.mechanism is None
        assert d.confidence < 0.5


class TestSubscriptionLifecycleMatrix:
    def test_pending_subscription_monitors_native_retry(self):
        d = decide(event_type="subscription_failed", subscription_state="pending",
                   cause=Cause.insufficient_funds, attempts_count=0,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.action is Action.monitor_native_retry
        assert d.mechanism.value == "native_subscription_retry"
        assert d.reasoning  # explains why we don't fight Razorpay's retries

    def test_halted_subscription_with_expired_card_gets_update_link(self):
        d = decide(event_type="subscription_halted", subscription_state="halted",
                   cause=Cause.card_expired, attempts_count=0,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.action is Action.send_payment_update_link
        assert d.mechanism.value == "checkout"

    def test_halted_subscription_generic_retry_becomes_manual_charge(self):
        d = decide(event_type="subscription_halted", subscription_state=None,
                   cause=Cause.payment_timeout, attempts_count=0,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.action is Action.immediate_retry
        assert d.mechanism.value == "manual_charge"

    def test_mechanism_never_implies_reopening_failed_payment(self):
        d = decide(event_type="payment_failed", subscription_state=None,
                   cause=Cause.payment_timeout, attempts_count=0,
                   low_confidence=0.5, high_confidence=0.85)
        assert d.mechanism.value == "new_recovery_payment"  # §3.4 honest vocabulary
