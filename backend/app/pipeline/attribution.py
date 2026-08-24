"""Recovery attribution (doc §3.1). A payment counts as recovered revenue
only when it (1) explicitly resolves a specific `recovery_attempt` — never by
matching customer email, customer id, or amount alone — (2) falls within the
merchant's configured recovery window, and (3) its amount satisfies the
outstanding obligation. The result of the window/amount check is always
stored, never hidden: a late or short payment is recorded honestly rather
than silently excluded or silently counted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..enums import EventStatus


@dataclass(frozen=True)
class AttributionResult:
    accepted: bool          # True iff counted as recovered revenue
    within_window: bool
    satisfies_amount: bool
    reason: str


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def attribute_payment(
    *, recovery_attempt_id: str, razorpay_payment_id: str, amount_paise: int,
    recovery_window_days: int,
) -> AttributionResult:
    """Called once a specific recovery_attempt's linked payment is confirmed
    (from the `payment_link.paid` outcome webhook, or the synthetic batch
    runner's simulated outcome). Idempotent: `UNIQUE(recovered_razorpay_payment_id)`
    means the same confirmed payment can never be counted twice, even under
    webhook retries.
    """
    attempt = db.get_recovery_attempt(recovery_attempt_id)
    if attempt is None:
        return AttributionResult(accepted=False, within_window=False, satisfies_amount=False,
                                  reason=f"No recovery_attempt found for '{recovery_attempt_id}'.")

    event = db.get_event(attempt["event_id"])
    if event is None:
        return AttributionResult(accepted=False, within_window=False, satisfies_amount=False,
                                  reason=f"No event found for attempt's event_id '{attempt['event_id']}'.")

    now = datetime.now(timezone.utc)
    created = _parse_iso(event["created_at"])
    within_window = (now - created) <= timedelta(days=recovery_window_days)
    satisfies_amount = amount_paise >= attempt["amount_paise"]
    accepted = within_window and satisfies_amount

    inserted = db.insert_recovered_payment({
        "event_id": attempt["event_id"], "merchant_id": attempt["merchant_id"],
        "recovery_attempt_id": recovery_attempt_id,
        "recovered_razorpay_payment_id": razorpay_payment_id,
        "amount_paise": amount_paise, "within_window": accepted,
    })
    if not inserted:
        return AttributionResult(accepted=False, within_window=within_window,
                                  satisfies_amount=satisfies_amount,
                                  reason="Payment id already attributed (idempotent no-op).")

    db.update_recovery_attempt(recovery_attempt_id, status="recovered", resolved_at=now.isoformat())

    if accepted:
        db.update_event(attempt["event_id"], status=EventStatus.recovered.value,
                         payment_recovered=1, razorpay_payment_id=razorpay_payment_id)
        customer_id = event.get("customer_id")
        if customer_id:
            db.add_customer_recovered(attempt["merchant_id"], customer_id, amount_paise)
        reason = "Recovered within window and amount satisfied."
    else:
        problems = []
        if not within_window:
            problems.append("outside the recovery window")
        if not satisfies_amount:
            problems.append("amount below the outstanding obligation")
        reason = f"Payment received but {' and '.join(problems)} — not counted as recovered revenue."
        # Never regress an already-recovered event to `closed` because a
        # different attempt's link later paid short/late (doc §3.5: terminal
        # states don't move backwards).
        if event.get("status") != EventStatus.recovered.value:
            db.update_event(attempt["event_id"], status=EventStatus.closed.value,
                             razorpay_payment_id=razorpay_payment_id)

    return AttributionResult(accepted=accepted, within_window=within_window,
                              satisfies_amount=satisfies_amount, reason=reason)


def mark_expired(event_id: str, reason: str) -> None:
    """The event aged out of its recovery window without a confirmed
    payment — a distinct terminal outcome from `recovered`, never silently
    reclassified as either."""
    db.update_event(event_id, status=EventStatus.expired.value)


def mark_attempt_failed(recovery_attempt_id: str, reason: str) -> None:
    db.update_recovery_attempt(recovery_attempt_id, status="failed",
                                resolved_at=datetime.now(timezone.utc).isoformat())
