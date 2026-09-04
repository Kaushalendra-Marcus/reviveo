"""Tests for AI customer notification service (scenarios A-J)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app import db
from app.config import settings
from app.enums import Action, AuditStage, EventStatus, ExecutionMechanism
from app.pipeline import pipeline
from app.services import execution_service, notification_service


def test_scenario_a_retry_and_notify_email_generation(seeded_db):
    """Scenario A: Payment failure -> retry_and_notify -> email generated and sent/simulated."""
    customer = {
        "id": "cust_test_a", "merchant_id": "codecraft", "name": "Rahul Sharma",
        "email": "rahul@example.com", "phone": "+919876543210",
        "total_recovered_paise": 0, "failed_payment_count": 0,
        "created_at": "2026-09-01T00:00:00Z"
    }
    db.insert_customer(customer)

    event_id = f"evt_test_a_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id, "merchant_id": "codecraft", "customer_id": "cust_test_a",
        "subscription_id": None, "invoice_id": None, "type": "payment_failed",
        "cause": "bank_declined", "error_code": "card_declined",
        "amount_paise": 109900, "status": "detected", "origin": "synthetic",
        "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"
    }
    db.insert_event(event)

    # Execute action directly (simulate approved retry_and_notify)
    res = execution_service.execute_action(
        merchant_id="codecraft",
        event=event,
        action=Action.retry_and_notify,
        mechanism=ExecutionMechanism.new_recovery_payment,
        customer=customer,
    )
    assert res.status == "awaiting_outcome"
    assert res.short_url is not None

    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n["recovery_attempt_id"] == res.recovery_attempt_id
    assert n["recipient"] == "rahul@example.com"
    assert n["status"] in ("simulated", "sent")
    assert "₹1,099.00" in n["body"] or "1099" in n["body"]
    assert res.short_url in n["body"]


def test_scenario_b_send_reminder_email_generation(seeded_db):
    """Scenario B: Payment failure -> send_reminder -> email generated and sent/simulated."""
    customer = {
        "id": "cust_test_b", "merchant_id": "codecraft", "name": "Priya Patel",
        "email": "priya@example.com", "phone": None,
        "total_recovered_paise": 0, "failed_payment_count": 0,
        "created_at": "2026-09-01T00:00:00Z"
    }
    db.insert_customer(customer)

    event_id = f"evt_test_b_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id, "merchant_id": "codecraft", "customer_id": "cust_test_b",
        "subscription_id": None, "invoice_id": None, "type": "abandoned_checkout",
        "cause": "checkout_abandoned", "error_code": "payment_cancelled",
        "amount_paise": 49900, "status": "detected", "origin": "synthetic",
        "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"
    }
    db.insert_event(event)

    # Process via pipeline
    pipeline.process_event(db.get_event(event_id))

    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "priya@example.com"
    assert notifs[0]["status"] in ("simulated", "sent")


def test_scenario_c_missing_customer_email_skipped(seeded_db):
    """Scenario C: Missing customer email -> notification skipped safely."""
    customer = {
        "id": "cust_no_email", "merchant_id": "codecraft", "name": "Anonymous User",
        "email": None, "phone": None,
        "total_recovered_paise": 0, "failed_payment_count": 0,
        "created_at": "2026-09-01T00:00:00Z"
    }
    db.insert_customer(customer)

    event_id = f"evt_test_c_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id, "merchant_id": "codecraft", "customer_id": "cust_no_email",
        "subscription_id": None, "invoice_id": None, "type": "abandoned_checkout",
        "cause": "checkout_abandoned", "error_code": "payment_cancelled",
        "amount_paise": 49900, "status": "detected", "origin": "synthetic",
        "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"
    }
    db.insert_event(event)

    # Pipeline should complete without raising
    result = pipeline.process_event(db.get_event(event_id))
    assert result["status"] == EventStatus.waiting_for_outcome.value

    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 1
    assert notifs[0]["status"] == "skipped"
    assert notifs[0]["error"] == "No trusted customer email available"


def test_scenario_d_guardrail_blocks_contact_no_email(seeded_db):
    """Scenario D: Guardrail blocks contact -> no email sent."""
    customer = {
        "id": "cust_test_d", "merchant_id": "codecraft", "name": "Amit Kumar",
        "email": "amit@example.com", "phone": None,
        "total_recovered_paise": 0, "failed_payment_count": 0,
        "created_at": "2026-09-01T00:00:00Z"
    }
    db.insert_customer(customer)

    # Set contact count to max daily contact cap (500)
    db.incr_daily_counter("codecraft", value_paise=0, contacts=500)

    event_id = f"evt_test_d_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id, "merchant_id": "codecraft", "customer_id": "cust_test_d",
        "subscription_id": None, "invoice_id": None, "type": "abandoned_checkout",
        "cause": "checkout_abandoned", "error_code": "payment_cancelled",
        "amount_paise": 49900, "status": "detected", "origin": "synthetic",
        "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"
    }
    db.insert_event(event)

    pipeline.process_event(db.get_event(event_id))

    # Guardrails should route to approval queue due to cap limit
    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 0


def test_scenario_e_approval_required_no_email_before_approval(seeded_db):
    """Scenario E: Approval required -> no email before approval."""
    customer = {
        "id": "cust_test_e", "merchant_id": "codecraft", "name": "Sneha Roy",
        "email": "sneha@example.com", "phone": None,
        "total_recovered_paise": 0, "failed_payment_count": 0,
        "created_at": "2026-09-01T00:00:00Z"
    }
    db.insert_customer(customer)

    event_id = f"evt_test_e_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id, "merchant_id": "codecraft", "customer_id": "cust_test_e",
        "subscription_id": None, "invoice_id": None, "type": "payment_failed",
        "cause": "bank_declined", "error_code": "card_declined",
        "amount_paise": 99900, "status": "detected", "origin": "synthetic",
        "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"
    }
    db.insert_event(event)

    res = pipeline.process_event(db.get_event(event_id))
    assert res["status"] == EventStatus.approval_pending.value

    # NO email sent yet before approval
    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 0

    # Now approve the pending approval
    pending = db.list_pending_approvals("codecraft")
    assert len(pending) >= 1
    appr = [a for a in pending if a["event_id"] == event_id][0]
    appr_id = appr["id"]

    from app.services import approvals
    appr_res = approvals.approve(appr_id, resolved_by="merchant-test")
    assert appr_res["ok"] is True

    # Email IS sent after approval
    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "sneha@example.com"


def test_scenario_f_duplicate_execution_idempotency(seeded_db):
    """Scenario F: Duplicate execution -> only one email."""
    customer = {"id": "cust_f", "name": "F", "email": "f@example.com"}
    event = {"event_id": "evt_f", "amount_paise": 1000, "cause": "payment_timeout"}
    attempt = {"recovery_attempt_id": "ra_f_123", "action": "send_reminder"}

    # First call
    res1 = notification_service.send_customer_notification(
        merchant_id="codecraft", event=event, recovery_attempt=attempt, customer=customer, short_url="http://link"
    )
    assert res1.status in ("simulated", "sent")

    # Second call for SAME recovery_attempt_id
    res2 = notification_service.send_customer_notification(
        merchant_id="codecraft", event=event, recovery_attempt=attempt, customer=customer, short_url="http://link"
    )
    assert res2.notification_id == res1.notification_id

    # Verify only 1 row in DB
    all_n = db.list_notifications_for_event("evt_f")
    assert len(all_n) == 1


def test_scenario_g_ai_generation_failure_safe_fallback(seeded_db):
    """Scenario G: AI generation failure -> safe fallback message used."""
    customer = {"id": "cust_g", "name": "Vikram", "email": "vikram@example.com"}
    event = {"event_id": "evt_g", "amount_paise": 150000, "cause": "insufficient_funds"}
    attempt = {"recovery_attempt_id": "ra_g_123", "action": "retry_and_notify"}

    with patch("app.services.ai_service._get_client") as mock_client:
        mock_client.side_effect = Exception("Groq connection error")
        res = notification_service.send_customer_notification(
            merchant_id="codecraft", event=event, recovery_attempt=attempt, customer=customer, short_url="https://rzp.io/test"
        )
        assert res.status in ("simulated", "sent")
        assert "Vikram" in res.body
        assert "1,500.00" in res.body
        assert "https://rzp.io/test" in res.body


def test_scenario_h_synthetic_mode_no_real_email_sent(seeded_db):
    """Scenario H: Synthetic mode -> no real email sent."""
    customer = {"id": "cust_h", "name": "Synthetic User", "email": "synth@example.com"}
    event = {"event_id": "evt_h", "amount_paise": 5000, "cause": "checkout_abandoned"}
    attempt = {"recovery_attempt_id": "ra_h_123", "action": "send_reminder"}

    res = notification_service.send_customer_notification(
        merchant_id="codecraft", event=event, recovery_attempt=attempt, customer=customer
    )
    assert res.status == "simulated"
    assert res.provider_message_id.startswith("sim_msg_")


def test_scenario_i_live_mode_email_disabled_no_real_email(seeded_db, monkeypatch):
    """Scenario I: Live mode with email disabled -> no real email sent."""
    monkeypatch.setattr(settings, "run_mode", "live")
    monkeypatch.setattr(settings, "notification_email_enabled", False)

    customer = {"id": "cust_i", "name": "Live User", "email": "live@example.com"}
    event = {"event_id": "evt_i", "amount_paise": 5000, "cause": "checkout_abandoned"}
    attempt = {"recovery_attempt_id": "ra_i_123", "action": "send_reminder"}

    res = notification_service.send_customer_notification(
        merchant_id="codecraft", event=event, recovery_attempt=attempt, customer=customer
    )
    assert res.status == "simulated"


def test_scenario_j_attribution_works_after_notification(seeded_db):
    """Scenario J: Successful Razorpay payment after notification -> existing attribution still works."""
    customer = {
        "id": "cust_j", "merchant_id": "codecraft", "name": "Arjun",
        "email": "arjun@example.com", "phone": None,
        "total_recovered_paise": 0, "failed_payment_count": 0,
        "created_at": "2026-09-01T00:00:00Z"
    }
    db.insert_customer(customer)

    event_id = f"evt_test_j_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id, "merchant_id": "codecraft", "customer_id": "cust_j",
        "subscription_id": None, "invoice_id": None, "type": "abandoned_checkout",
        "cause": "checkout_abandoned", "error_code": "payment_cancelled",
        "amount_paise": 88800, "status": "detected", "origin": "synthetic",
        "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"
    }
    db.insert_event(event)

    # Process event
    pipeline.process_event(db.get_event(event_id))

    # Notification sent
    notifs = db.list_notifications_for_event(event_id)
    assert len(notifs) == 1

    # Simulate payment link paid webhook outcome
    attempts = db.list_attempts_for_event(event_id)
    assert len(attempts) == 1
    attempt_id = attempts[0]["recovery_attempt_id"]

    from app.pipeline import attribution
    attr_res = attribution.attribute_payment(
        recovery_attempt_id=attempt_id,
        razorpay_payment_id="pay_succ_j_999",
        amount_paise=88800,
        recovery_window_days=7,
    )
    assert attr_res.accepted is True
    ev = db.get_event(event_id)
    assert ev["status"] == EventStatus.recovered.value
    assert ev["payment_recovered"] == 1
