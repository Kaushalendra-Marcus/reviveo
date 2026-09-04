"""Regression tests for the void@razorpay.com placeholder-email bug
(evt_420edad734e64f08): Razorpay test mode puts its own dummy address in
the payment.failed entity, and Reviveo must never treat it as the customer.

The trusted address below stands in for the real payer address from the
incident report. It is FIXTURE data for these tests only — production code
never references it (no hardcoding; resolution is purely priority-based).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import RunMode, settings
from app.main import app
from app.services import notification_service
from app.webhooks import webhook as webhook_module

MERCHANT = "codecraft"
TRUSTED_EMAIL = "edujeemarcus@gmail.com"
PLACEHOLDER = "void@razorpay.com"


def _failed_envelope(*, email=None, contact=None, razorpay_customer_id=None,
                     error_reason="payment_cancelled", amount=79300,
                     pay_id=None, event_uuid=None, link_customer=None,
                     order_notes=None, entity_notes=None):
    entity: dict = {
        "id": pay_id or f"pay_{uuid.uuid4().hex[:10]}",
        "amount": amount,
        "currency": "INR",
        "error_reason": error_reason,
        "error_code": error_reason,
    }
    if email is not None:
        entity["email"] = email
    if contact is not None:
        entity["contact"] = contact
    if razorpay_customer_id is not None:
        entity["customer_id"] = razorpay_customer_id
    if entity_notes is not None:
        entity["notes"] = entity_notes
    inner: dict = {"payment": {"entity": entity}}
    if link_customer is not None:
        inner["payment_link"] = {"entity": {"customer": link_customer}}
    if order_notes is not None:
        inner["order"] = {"entity": {"notes": order_notes}}
    return {
        "id": event_uuid or f"evt_rzp_{uuid.uuid4().hex[:10]}",
        "event": "payment.failed",
        "payload": inner,
    }


def _ingest(payload) -> dict:
    webhook_module._handle_payment_failed(MERCHANT, payload)
    rows = db.query_all(
        "SELECT * FROM events WHERE merchant_id=? ORDER BY created_at DESC LIMIT 1",
        (MERCHANT,),
    )
    assert rows
    return rows[0]


def _seed_trusted_customer(phone="+919876543210", customer_id="cust_trusted",
                           rzp_id=None):
    db.insert_customer({"id": customer_id, "merchant_id": MERCHANT,
                        "name": "Trusted Buyer", "email": TRUSTED_EMAIL,
                        "phone": phone, "razorpay_customer_id": rzp_id})


# ── Exact incident: void entity email + trusted record matched by phone ────
def test_void_entity_email_loses_to_trusted_phone_match(seeded_db):
    _seed_trusted_customer()
    event = _ingest(_failed_envelope(email=PLACEHOLDER, contact="+919876543210"))

    assert event["customer_id"] == "cust_trusted"
    customer = db.get_customer(MERCHANT, "cust_trusted")
    assert customer["email"] == TRUSTED_EMAIL  # never overwritten by placeholder

    notifs = db.list_notifications_for_event(event["event_id"])
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == TRUSTED_EMAIL
    assert notifs[0]["recipient"] != PLACEHOLDER


# ── Placeholder with NO trusted source anywhere → skipped, never sent ──────
def test_placeholder_without_trusted_source_skips(seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "run_mode", RunMode.live)
    monkeypatch.setattr(settings, "notification_email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_do_not_use")
    with patch.object(notification_service.ResendEmailProvider, "send_email",
                      side_effect=AssertionError("must never send to placeholder")):
        event = _ingest(_failed_envelope(email=PLACEHOLDER, contact="+917830328929"))
        # A phone-only record may exist, but with no trusted email the
        # notification must stay skipped.
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] == "skipped"
        assert notifs[0]["recipient"] == "none"
        assert "No trusted customer email" in (notifs[0]["error"] or "")
        # And no customer row may store the placeholder as its email.
        rows = db.query_all("SELECT * FROM customers WHERE email=?", (PLACEHOLDER,))
        assert rows == []


# ── Placeholder-only (no phone at all) creates nothing ─────────────────────
def test_placeholder_only_creates_no_customer(seeded_db):
    before = db.count_customers(MERCHANT)
    event = _ingest(_failed_envelope(email=PLACEHOLDER))
    assert event["customer_id"] is None
    assert db.count_customers(MERCHANT) == before


# ── Normal real email still works ───────────────────────────────────────────
def test_real_entity_email_still_used(seeded_db):
    event = _ingest(_failed_envelope(email="customer@example.com"))
    assert event["customer_id"]
    customer = db.get_customer(MERCHANT, event["customer_id"])
    assert customer["email"] == "customer@example.com"
    notifs = db.list_notifications_for_event(event["event_id"])
    assert notifs[0]["recipient"] == "customer@example.com"


# ── Existing trusted customer is reused; void never overwrites ─────────────
def test_existing_trusted_email_never_overwritten(seeded_db):
    _seed_trusted_customer(phone="+919999999999", customer_id="cust_keep")
    before = db.count_customers(MERCHANT)
    event = _ingest(_failed_envelope(email=PLACEHOLDER, contact="+919999999999"))
    assert event["customer_id"] == "cust_keep"
    assert db.count_customers(MERCHANT) == before
    assert db.get_customer(MERCHANT, "cust_keep")["email"] == TRUSTED_EMAIL


# ── Payment-link checkout contact outranks void entity email (Flow B) ───────
def test_payment_link_customer_beats_void_entity(seeded_db):
    event = _ingest(_failed_envelope(
        email=PLACEHOLDER, contact="+917830328929",
        link_customer={"email": TRUSTED_EMAIL, "contact": "+911234567890"}))
    customer = db.get_customer(MERCHANT, event["customer_id"])
    assert customer is not None
    assert customer["email"] == TRUSTED_EMAIL
    notifs = db.list_notifications_for_event(event["event_id"])
    assert notifs[0]["recipient"] == TRUSTED_EMAIL


# ── Notes contact outranks void entity email ────────────────────────────────
def test_notes_email_beats_void_entity(seeded_db):
    event = _ingest(_failed_envelope(
        email=PLACEHOLDER,
        entity_notes={"email": TRUSTED_EMAIL}))
    customer = db.get_customer(MERCHANT, event["customer_id"])
    assert customer is not None
    assert customer["email"] == TRUSTED_EMAIL


# ── Backfill heals placeholder-poisoned rows, never the reverse ─────────────
def test_trusted_backfill_heals_placeholder_row(seeded_db):
    db.insert_customer({"id": "cust_poisoned", "merchant_id": MERCHANT,
                        "name": PLACEHOLDER, "email": PLACEHOLDER,
                        "phone": "+918888888888"})
    row = db.resolve_webhook_customer(
        MERCHANT, email=TRUSTED_EMAIL, phone="+918888888888")
    assert row["id"] == "cust_poisoned"
    assert db.get_customer(MERCHANT, "cust_poisoned")["email"] == TRUSTED_EMAIL

    # And the reverse is refused: placeholder can never overwrite trusted.
    row2 = db.resolve_webhook_customer(
        MERCHANT, email=PLACEHOLDER, phone="+918888888888")
    assert db.get_customer(MERCHANT, "cust_poisoned")["email"] == TRUSTED_EMAIL
    assert row2["id"] == "cust_poisoned"


# ── Duplicate webhook: same customer, no duplicates ─────────────────────────
@pytest.mark.usefixtures("seeded_db")
def test_duplicate_placeholder_webhook_idempotent():
    _seed_trusted_customer(phone="+917777777777", customer_id="cust_dup")
    payload = _failed_envelope(email=PLACEHOLDER, contact="+917777777777",
                               event_uuid=f"wh_dup_{uuid.uuid4().hex[:8]}")
    with TestClient(app) as client:
        first = client.post("/webhooks/razorpay", json=payload).json()
        assert first["status"] != "duplicate"
        dup = client.post("/webhooks/razorpay", json=payload).json()
        assert dup == {"status": "duplicate"}
    assert db.query_all(
        "SELECT * FROM customers WHERE merchant_id=? AND email=?",
        (MERCHANT, TRUSTED_EMAIL))


# ── Live Resend mock: trusted recipient exactly once, never void ────────────
def test_live_resend_receives_trusted_recipient(seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "run_mode", RunMode.live)
    monkeypatch.setattr(settings, "notification_email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_do_not_use")
    _seed_trusted_customer(phone="+916666666666", customer_id="cust_live")

    calls: list[dict] = []

    def fake_send(self, *, to, subject, text_body, html_body, from_email):
        calls.append({"to": to})
        return True, "re_msg_trusted1", None

    with patch.object(notification_service.ResendEmailProvider, "send_email", fake_send):
        event = _ingest(_failed_envelope(email=PLACEHOLDER, contact="+916666666666"))
        notifs = db.list_notifications_for_event(event["event_id"])
        assert notifs[0]["status"] == "sent"
        assert notifs[0]["provider_message_id"] == "re_msg_trusted1"

    assert len(calls) == 1
    assert calls[0]["to"] == TRUSTED_EMAIL
    assert calls[0]["to"] != PLACEHOLDER


# ── Notification guard: stale placeholder on the passed object ──────────────
def test_notification_guard_rejects_placeholder_object(seeded_db):
    event = {"event_id": "evt_guard", "amount_paise": 1000, "cause": "bank_declined"}
    attempt = {"recovery_attempt_id": "ra_guard_1", "action": "send_reminder"}
    stale = {"id": "cust_stale", "name": "Stale", "email": PLACEHOLDER}
    res = notification_service.send_customer_notification(
        merchant_id=MERCHANT, event=event, recovery_attempt=attempt,
        customer=stale, short_url="http://link")
    assert res.status == "skipped"
    assert res.recipient is None
