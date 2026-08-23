"""Subscription lifecycle handling — the pending/halted action matrix (doc
§3.2 and §3.3).

Razorpay's documented subscription behavior: a failed auto-charge moves the
subscription to `pending`; Razorpay retries the charge automatically for a
bounded number of cycles; once retries are exhausted the subscription moves
to `halted`. Updating the card while `pending` can auto-charge the last
invoice; once `halted`, future invoices continue to be raised on schedule but
the missed invoice generally needs a manual charge once the customer's
payment method is fixed. See:
  https://razorpay.com/docs/payments/subscriptions/payment-retries/
  https://razorpay.com/docs/payments/subscriptions/states/

`payment_recovered`, `subscription_restored`, and `subscription_state` are
kept as separate concepts everywhere in this codebase (doc §3.2) — collecting
one outstanding invoice does not, by itself, mean the subscription lifecycle
is restored. That distinction is recorded on `events` and finalized by
`pipeline.attribution`, not decided here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..enums import Action, Cause, EventType, ExecutionMechanism, SubscriptionState


@dataclass(frozen=True)
class LifecycleOverride:
    action: Action
    mechanism: ExecutionMechanism
    note: str
    # When set, replaces the cause-based confidence entirely (this is a
    # well-understood platform rule, not a probabilistic guess).
    confidence: Optional[float] = None


def resolve_subscription_action(
    *,
    event_type: EventType | str,
    subscription_state: Optional[str],
    cause: Cause,
    base_action: Action,
) -> Optional[LifecycleOverride]:
    """Return a lifecycle override for the final Razorpay action matrix
    (doc §3.3), or None to fall through to the cause-based decision engine.

    `base_action` is the action the cause-based whitelist would otherwise
    pick — used only to decide whether a halted-subscription redirect is
    needed; the returned action always wins when this is not None.
    """
    event_type = EventType(event_type) if not isinstance(event_type, EventType) else event_type

    # subscription_failed + native retries still active (state == pending):
    # monitor only, never fight Razorpay's own retry engine.
    if event_type == EventType.subscription_failed and subscription_state == SubscriptionState.pending.value:
        return LifecycleOverride(
            action=Action.monitor_native_retry,
            mechanism=ExecutionMechanism.native_subscription_retry,
            note="Subscription is pending — Razorpay's native retry cycle is still active; monitoring rather than competing with it.",
            confidence=0.92,
        )

    if event_type == EventType.subscription_halted or subscription_state == SubscriptionState.halted.value:
        # Retries are exhausted on Razorpay's side. A same-card automatic
        # retry cannot be assumed to work (doc §3.3) — the customer needs to
        # fix their payment method, or we attempt a supported manual charge,
        # or a human decides.
        if cause == Cause.card_expired:
            return LifecycleOverride(
                action=Action.send_payment_update_link,
                mechanism=ExecutionMechanism.checkout,
                note="Subscription halted with an expired card — customer must update their payment method via Checkout.",
            )
        if base_action in (Action.immediate_retry, Action.smart_retry_24h, Action.retry_and_notify):
            return LifecycleOverride(
                action=Action.immediate_retry,
                mechanism=ExecutionMechanism.manual_charge,
                note="Subscription halted — attempting a manual charge against the outstanding invoice instead of assuming native retry semantics apply.",
            )
        # send_reminder / escalate_to_human pass through unchanged.
        return None

    return None
