import uuid
from datetime import datetime, timezone

import pytest

from app import db
from app.enums import EventStatus
from app.pipeline import pipeline

pytestmark = pytest.mark.usefixtures("seeded_db")

MERCHANT = "codecraft"

_EVENTS = [
    # (type, error_code, amount_paise, customer_id, subscription_id)
    ("payment_failed", "card_expired", 249_900, "cust_rahul", None),
    ("payment_failed", "insufficient_funds", 99_900, "cust_priya", None),
    ("payment_failed", "payment_timed_out", 249_900, "cust_amit", None),
    ("payment_failed", "card_declined", 99_900, "cust_sara", None),
    ("payment_failed", "payment_cancelled", 499_900, "cust_dev", None),
    ("payment_failed", "SOME_UNKNOWN_CODE", 99_900, "cust_neha", None),
    ("payment_failed", "card_expired", 5_000_000, "cust_rahul", None),  # over autonomous ceiling -> approval
    ("subscription_failed", "insufficient_funds", 99_900, "cust_priya", "sub_cust_priya"),
    ("subscription_halted", "card_expired", 249_900, "cust_amit", "sub_cust_amit"),
    ("payment_failed", "bank_downtime", 99_900, "cust_sara", None),
]


def _make_event(i: int, spec: tuple) -> dict:
    etype, error_code, amount, customer_id, subscription_id = spec
    event_id = f"evt_test_{i}_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "event_id": event_id, "merchant_id": MERCHANT, "customer_id": customer_id,
        "subscription_id": subscription_id, "type": etype, "error_code": error_code,
        "amount_paise": amount, "status": EventStatus.detected.value,
        "origin": "synthetic", "created_at": now,
    }
    db.insert_event(event)
    return db.get_event(event_id)


def test_ten_event_batch_produces_uniform_audit_trail():
    results = []
    for i, spec in enumerate(_EVENTS):
        event = _make_event(i, spec)
        result = pipeline.process_event(event, use_ai=False)
        results.append(result)

    assert len(results) == 10

    for result in results:
        event_id = result["event_id"]
        audit_rows = db.list_audit_for_event(event_id)
        assert len(audit_rows) == 6, f"{event_id} has {len(audit_rows)} audit rows, expected 6"

        stages = [r["stage"] for r in audit_rows]
        assert stages == ["detected", "analyzed", "decided", "guardrail", "executed", "outcome"]

        outcome_rows = [r for r in audit_rows if r["stage"] == "outcome"]
        assert len(outcome_rows) == 1

        # Every event must have moved off its initial 'detected' status.
        final_event = db.get_event(event_id)
        assert final_event["status"] != EventStatus.detected.value


def test_high_confidence_low_risk_auto_executes_and_creates_attempt():
    event = _make_event(100, ("payment_failed", "payment_timed_out", 99_900, "cust_amit", None))
    result = pipeline.process_event(event, use_ai=False)
    assert result["status"] == EventStatus.waiting_for_outcome.value
    attempts = db.list_attempts_for_event(event["event_id"])
    assert len(attempts) == 1
    assert attempts[0]["status"] == "awaiting_outcome"


def test_unclassified_cause_always_escalates_to_approval():
    event = _make_event(101, ("payment_failed", "TOTALLY_UNKNOWN", 99_900, "cust_amit", None))
    result = pipeline.process_event(event, use_ai=False)
    assert result["action"] == "escalate_to_human"
    assert result["status"] == EventStatus.approval_pending.value
    approvals = db.list_pending_approvals(MERCHANT)
    assert any(a["event_id"] == event["event_id"] for a in approvals)


def test_amount_over_autonomous_ceiling_requires_approval():
    event = _make_event(102, ("payment_failed", "payment_timed_out", 5_000_000, "cust_dev", None))
    result = pipeline.process_event(event, use_ai=False)
    assert result["status"] == EventStatus.approval_pending.value


def test_pending_subscription_monitors_without_razorpay_call():
    db.update_subscription_state("sub_cust_sara", "pending")
    event = _make_event(103, ("subscription_failed", "insufficient_funds", 99_900,
                               "cust_sara", "sub_cust_sara"))
    result = pipeline.process_event(event, use_ai=False)
    assert result["action"] == "monitor_native_retry"
    attempts = db.list_attempts_for_event(event["event_id"])
    assert attempts[0]["execution_mechanism"] == "native_subscription_retry"
    assert attempts[0]["razorpay_ref"] is None


def test_recovery_attribution_end_to_end():
    event = _make_event(104, ("payment_failed", "payment_timed_out", 99_900, "cust_amit", None))
    result = pipeline.process_event(event, use_ai=False)
    attempt_id = result["recovery_attempt_id"]

    from app.pipeline import attribution
    outcome = attribution.attribute_payment(
        recovery_attempt_id=attempt_id, razorpay_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
        amount_paise=99_900, recovery_window_days=7,
    )
    assert outcome.accepted is True

    final_event = db.get_event(event["event_id"])
    assert final_event["status"] == EventStatus.recovered.value
    assert final_event["payment_recovered"] == 1

    # Idempotency: attributing the same payment id again must be a no-op.
    outcome2 = attribution.attribute_payment(
        recovery_attempt_id=attempt_id, razorpay_payment_id=outcome and _last_payment_id(attempt_id),
        amount_paise=99_900, recovery_window_days=7,
    )
    assert outcome2.accepted is False


def _last_payment_id(attempt_id: str) -> str:
    row = db.query_one(
        "SELECT recovered_razorpay_payment_id FROM recovered_payments WHERE recovery_attempt_id=?",
        (attempt_id,),
    )
    return row["recovered_razorpay_payment_id"]
