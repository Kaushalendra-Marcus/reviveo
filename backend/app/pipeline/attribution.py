"""Attribution engine — the proof-of-recovery chain (doc §3.1).

A payment counts as recovered ONLY when it resolves a recovery_attempt, lands
inside the merchant's recovery window, and covers the outstanding obligation.
The window verdict is stored (`within_window`), never silently dropped. The
UNIQUE(recovered_razorpay_payment_id) constraint in the schema makes the
headline metric double-count-proof.
"""
from __future__ import annotations

import random
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..enums import AuditStage, EventType, EventStatus, SubscriptionState
from ..logging_config import get_logger
from .state_machine import transition

logger = get_logger("reviveo.attribution")

# Deterministic synthetic outcome probabilities per mechanism — used only when
# execution_mode == dry_run and event origin is synthetic.
_SYNTH_SUCCESS_RATE = {
    "checkout": 0.80,
    "payment_link": 0.70,
    "scheduled_recovery_payment": 0.60,
    "new_recovery_payment": 0.55,
    "manual_charge": 0.50,
    "native_subscription_retry": 0.65,
    "reminder_only": 0.45,
}


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def iso_plus_days(ts: str, days: int) -> str:
    return (_parse(ts) + timedelta(days=days)).isoformat()


def simulate_outcome(attempt: dict) -> dict:
    """Deterministic pseudo-outcome seeded by attempt id (reproducible)."""
    rate = _SYNTH_SUCCESS_RATE.get(attempt["execution_mechanism"], 0.5)
    seed = hashlib.sha256(f"{attempt['recovery_attempt_id']}|outcome".encode()).hexdigest()
    paid = random.Random(seed).random() < rate
    payment_id = f"pay_syn_{seed[:12]}" if paid else None
    return {
        "paid": paid,
        "razorpay_payment_id": payment_id,
        "amount_paise": attempt["amount_paise"] if paid else 0,
        "occurred_at": db.now_iso(),
    }


def apply_outcome(
    event: dict,
    attempt: dict,
    *,
    paid: bool,
    razorpay_payment_id: Optional[str] = None,
    amount_paise: int = 0,
    occurred_at: Optional[str] = None,
) -> dict:
    """Resolve an attempt with a real or simulated payment outcome.

    Returns a summary dict describing what attribution decided."""
    cfg = db.get_guardrail_config(event["merchant_id"])
    occurred_at = occurred_at or db.now_iso()
    result: dict = {"paid": paid, "counted_as_recovered": False}

    if not paid:
        remaining = cfg["max_retries"] - db.count_attempts(event["event_id"])
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="failed",
                                   resolved_at=occurred_at)
        if remaining <= 0:
            transition(event["event_id"], EventStatus.failed)
        db.insert_audit({
            "event_id": event["event_id"],
            "merchant_id": event["merchant_id"],
            "stage": AuditStage.outcome.value,
            "message": f"Recovery attempt #{attempt['attempt_number']} did not convert; "
                       f"{max(remaining, 0)} attempt(s) remain.",
            "payload": {"paid": False, "attempt_number": attempt["attempt_number"]},
        })
        result["attempts_remaining"] = max(remaining, 0)
        return result

    # Window + obligation checks (§3.1).
    within_window = False
    try:
        within_window = (
            _parse(occurred_at)
            <= _parse(iso_plus_days(attempt["created_at"], cfg["recovery_window_days"]))
            and amount_paise >= attempt["amount_paise"]
            and event["status"] not in ("failed", "closed")
        )
    except (ValueError, TypeError):
        logger.warning("could not parse timestamps for window check (event %s)",
                       event["event_id"])

    inserted = db.insert_recovered_payment({
        "event_id": event["event_id"],
        "merchant_id": event["merchant_id"],
        "recovery_attempt_id": attempt["recovery_attempt_id"],
        "recovered_razorpay_payment_id": razorpay_payment_id or f"pay_{attempt['recovery_attempt_id']}",
        "amount_paise": amount_paise,
        "within_window": within_window,
    })
    result["within_window"] = within_window
    result["newly_recorded"] = inserted

    if not inserted:
        # Idempotent replay of the same outcome webhook — no double counting.
        db.insert_audit({
            "event_id": event["event_id"], "merchant_id": event["merchant_id"],
            "stage": AuditStage.outcome.value,
            "message": "Duplicate recovery payment id ignored (already attributed).",
            "payload": {"razorpay_payment_id": razorpay_payment_id},
        })
        return result

    if within_window:
        fields = {"payment_recovered": 1}
        if event["type"] in (EventType.subscription_halted.value, EventType.subscription_failed.value):
            sub_id = event.get("subscription_id")
            if sub_id:
                db.update_subscription_state(sub_id, SubscriptionState.active.value)
            fields.update({"subscription_restored": 1, "subscription_state_after": "active"})
        db.update_event(event["event_id"], **fields)
        transition(event["event_id"], EventStatus.recovered)
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="recovered",
                                   resolved_at=occurred_at)
        db.add_customer_recovered(event["merchant_id"], event.get("customer_id") or "", amount_paise)
        db.incr_daily_counter(event["merchant_id"], value_paise=amount_paise)
        result["counted_as_recovered"] = True
        message = (f"Recovered ₹{amount_paise / 100:.2f} via payment "
                   f"{razorpay_payment_id} within the {cfg['recovery_window_days']}-day window.")
    else:
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="expired",
                                   resolved_at=occurred_at)
        message = ("Payment succeeded but fell OUTSIDE the recovery window or did not "
                   "cover the obligation — recorded, not counted as recovered.")

    db.insert_audit({
        "event_id": event["event_id"], "merchant_id": event["merchant_id"],
        "stage": AuditStage.outcome.value, "message": message,
        "payload": {"paid": True, "within_window": within_window,
                    "amount_paise": amount_paise,
                    "razorpay_payment_id": razorpay_payment_id},
    })
    return result


def expire_stale_attempts(merchant_id: str) -> int:
    """Attempts awaiting an outcome past the recovery window expire honestly."""
    cfg = db.get_guardrail_config(merchant_id)
    now = datetime.now(timezone.utc)
    expired = 0
    for attempt in db.query_all(
        "SELECT * FROM recovery_attempts WHERE merchant_id=? AND status='awaiting_outcome'",
        (merchant_id,),
    ):
        deadline = _parse(iso_plus_days(attempt["created_at"], cfg["recovery_window_days"]))
        if now > deadline:
            db.update_recovery_attempt(attempt["recovery_attempt_id"], status="expired",
                                       resolved_at=db.now_iso())
            ev = db.get_event(attempt["event_id"])
            if ev and ev["status"] == "waiting_for_outcome":
                transition(ev["event_id"], EventStatus.expired)
                db.insert_audit({
                    "event_id": ev["event_id"], "merchant_id": merchant_id,
                    "stage": AuditStage.outcome.value,
                    "message": "Recovery window elapsed with no successful payment — expired.",
                    "payload": {},
                })
            expired += 1
    return expired
