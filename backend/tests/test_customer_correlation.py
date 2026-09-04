"""Tests for webhook customer correlation + live email recovery (fix tests A-O).

Covers: payment.failed -> resolve/create customer -> event.customer_id ->
decision -> approval/auto-execution -> recovery attempt -> notification ->
Resend (mocked) -> persistence, plus idempotency, fallback, and attribution.
External Resend calls are always mocked — no test sends a real email.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import RunMode, settings
from app.enums import EventStatus
from app.main import app
from app.services import notification_service
from app.webhooks import webhook as webhook_module

MERCHANT = "codecraft"


def _failed_envelope(*, email=None, contact=None, razorpay_customer_id=None,
                     error_reason="payment_cancelled", amount=49900,
                     pay_id=None, name=None, event_uuid=None):
    """Representative Razorpay payment.failed envelope using only fields the
    webhook parser supports (payload.payload.payment.entity)."""
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
    if name is not None:
        entity["name"] = name
    return {
        "id": event_uuid or f"evt_rzp_{uuid.uuid4().hex[:10]}",
        "event": "payment.failed",
        "payload": {"payment": {"entity": entity}},
    }


def _ingest(payload) -> dict:
    """Push a failure envelope through the real webhook handler (no HTTP)."""
    webhook_module._handle_payment_failed(MERCHANT, payload)
    rows = db.query_all(
        "SELECT * FROM events WHERE merchant_id=? ORDER BY created_at DESC LIMIT 1",
        (MERCHANT,),
    )
    assert rows, "expected _handle_payment_failed to persist an event"
    return rows[0]


def _enable_live_email(monkeypatch):
    monkeypatch.setattr(settings, "run_mode", RunMode.live)
    monkeypatch.setattr(settings, "notification_email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_do_not_use")


# ── TEST A: new email/contact creates customer, links event + notification ──
def test_a_new_contact_creates_customer_and_notifies(seeded_db):
    payload = _failed_envelope(email="newbuyer@example.com", contact="+919812345678")
    event = _ingest(payload)

    assert event["customer_id"], "event.customer_id must be set from webhook contact"
    customer = db.get_customer(MERCHANT, event["customer_id"])
    assert customer is not None
    assert customer["email"] == "newbuyer@example.com"
    assert customer["phone"] == "+919812345678"

    notifs = db.list_notifications_for_event(event["event_id"])
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "newbuyer@example.com"
    assert notifs[0]["status"] in ("simulated", "sent")


# ── TEST B: duplicate delivery → no duplicate customer/notification ─────────
def test_b_duplicate_webhook_is_idempotent(seeded_db):
    payload = _failed_envelope(email="repeat@example.com", contact="+919812345679")
    first = _ingest(payload)
    second = _ingest(payload)

    assert second["customer_id"] == first["customer_id"], "same identity must reuse one customer"
    dupes = db.query_all(
        "SELECT * FROM customers WHERE merchant_id=? AND email=?",
        (MERCHANT, "repeat@example.com"),
    )
    assert len(dupes) == 1

    attempts = db.list_attempts_for_event(first["event_id"])
    assert attempts
    again = notification_service.send_customer_notification(
        merchant_id=MERCHANT, event=db.get_event(first["event_id"]),
        recovery_attempt=attempts[0],
        customer=db.get_customer(MERCHANT, first["customer_id"]),
        short_url="https://rzp.io/x",
    )
    existing = db.get_notification_by_attempt(attempts[0]["recovery_attempt_id"])
    assert again.notification_id == existing["notification_id"]
    assert len(db.list_notifications_for_event(first["event_id"])) == 1


# ── TEST C: existing customer matched by email ──────────────────────────────
def test_c_existing_customer_matched_by_email(seeded_db):
    before = db.count_customers(MERCHANT)
    payload = _failed_envelope(email="rahul@example.com", contact="+910000000000")
    event = _ingest(payload)
    assert event["customer_id"] == "cust_rahul"
    assert db.count_customers(MERCHANT) == before


# ── TEST D: existing customer matched by phone ──────────────────────────────
def test_d_existing_customer_matched_by_phone(seeded_db):
    before = db.count_customers(MERCHANT)
    payload = _failed_envelope(email="someone-else@example.com", contact="+919000000002")
    event = _ingest(payload)
    assert event["customer_id"] == "cust_priya"
    assert db.count_customers(MERCHANT) == before


# ── TEST E: stored Razorpay customer-id mapping resolves ────────────────────
def test_e_razorpay_customer_id_mapping(seeded_db):
    db.insert_customer({"id": "cust_mapped", "merchant_id": MERCHANT,
                        "name": "Mapped User", "email": "mapped@example.com",
                        "phone": None, "razorpay_customer_id": "cust_rzp_abc123"})
    payload = _failed_envelope(razorpay_customer_id="cust_rzp_abc123")
    event = _ingest(payload)
    assert event["customer_id"] == "cust_mapped"


# ── TEST F: no email/phone → skipped, Resend never called ───────────────────
def test_f_no_contact_skips_and_never_calls_resend(seeded_db, monkeypatch):
    _enable_live_email(monkeypatch)
    with patch.object(notification_service.ResendEmailProvider, "send_email",
                      side_effect=AssertionError("Resend must not be called")):
        payload = _failed_envelope()
        event = _ingest(payload)
        assert event["customer_id"] is None
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] == "skipped"
        assert notifs[0]["recipient"] == "none"
        assert "No customer email" in (notifs[0]["error"] or "")


# ── TEST G: live + enabled + key → Resend called once, status sent ──────────
def test_g_live_email_sends_via_resend(seeded_db, monkeypatch):
    _enable_live_email(monkeypatch)
    calls: list[dict] = []

    def fake_send(self, *, to, subject, text_body, html_body, from_email):
        calls.append({"to": to, "subject": subject, "from_email": from_email})
        return True, "re_msg_test123", None

    with patch.object(notification_service.ResendEmailProvider, "send_email", fake_send):
        payload = _failed_envelope(email="vipbuyer@example.com", contact="+919812345680")
        event = _ingest(payload)
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] == "sent"
        assert notifs[0]["provider_message_id"] == "re_msg_test123"

    assert len(calls) == 1
    assert calls[0]["to"] == "vipbuyer@example.com"


# ── TEST H: Resend 4xx/5xx → failed, error persisted, never "sent" ──────────
def test_h_resend_failure_persists_failed(seeded_db, monkeypatch):
    _enable_live_email(monkeypatch)

    def fake_fail(self, *, to, subject, text_body, html_body, from_email):
        return False, None, "Resend API error (403): Invalid `from` address"

    with patch.object(notification_service.ResendEmailProvider, "send_email", fake_fail):
        payload = _failed_envelope(email="unlucky@example.com")
        event = _ingest(payload)
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] == "failed"
        assert "403" in (notifs[0]["error"] or "")
        assert notifs[0]["provider_message_id"] is None


# ── TEST I: AI succeeds → ai_generated true ─────────────────────────────────
def test_i_ai_success_marks_generated(seeded_db, monkeypatch):
    from app.services.ai_service import AIResult
    with patch("app.services.notification_service.ai_service.draft_customer_message",
               return_value=AIResult(text="Hi, please pay via this link.",
                                     used=True, model="test-model",
                                     latency_ms=42, fallback_triggered=False)):
        payload = _failed_envelope(email="aifriend@example.com")
        event = _ingest(payload)
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert bool(notifs[0]["ai_generated"]) is True
        assert notifs[0]["ai_model"] == "test-model"


# ── TEST J: AI fails → fallback body still attempted ────────────────────────
def test_j_ai_failure_falls_back_and_still_sends(seeded_db):
    from app.services.ai_service import AIResult
    with patch("app.services.notification_service.ai_service.call_claude",
               return_value=AIResult(text=None, used=False, model="m",
                                     latency_ms=1, fallback_triggered=True)):
        payload = _failed_envelope(email="aifallback@example.com")
        event = _ingest(payload)
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] in ("simulated", "sent", "failed")
        assert bool(notifs[0]["ai_generated"]) is False
        # deterministic fallback template carries amount + link + name
        assert "499.00" in (notifs[0]["body"] or "") or "aifallback@example.com" in (notifs[0]["body"] or "")


# ── TEST K: synthetic mode → simulated, no HTTP ─────────────────────────────
def test_k_synthetic_mode_simulates_without_http(seeded_db):
    with patch("urllib.request.urlopen",
               side_effect=AssertionError("no real HTTP in synthetic mode")):
        payload = _failed_envelope(email="synthmode@example.com")
        event = _ingest(payload)
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] == "simulated"
        assert (notifs[0]["provider_message_id"] or "").startswith("sim_msg_")


# ── TEST L: live but email disabled → simulated ─────────────────────────────
def test_l_live_email_disabled_simulates(seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "run_mode", RunMode.live)
    monkeypatch.setattr(settings, "notification_email_enabled", False)
    with patch("urllib.request.urlopen",
               side_effect=AssertionError("no real HTTP when disabled")):
        payload = _failed_envelope(email="disabledmode@example.com")
        event = _ingest(payload)
        notifs = db.list_notifications_for_event(event["event_id"])
        assert len(notifs) == 1
        assert notifs[0]["status"] == "simulated"


# ── TEST M: approval gates notification; post-approval sends ────────────────
def test_m_approval_gates_notification_then_sends(seeded_db):
    from app.services import approvals
    # bank_declined → retry_and_notify (medium risk) → approval_pending
    payload = _failed_envelope(email="approveme@example.com",
                               contact="+919812345681",
                               error_reason="card_declined", amount=99900)
    event = _ingest(payload)
    assert event["status"] == EventStatus.approval_pending.value
    assert db.list_notifications_for_event(event["event_id"]) == []

    pending = [a for a in db.list_pending_approvals(MERCHANT)
               if a["event_id"] == event["event_id"]]
    assert pending
    res = approvals.approve(pending[0]["id"], resolved_by="merchant-test")
    assert res["ok"] is True

    notifs = db.list_notifications_for_event(event["event_id"])
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "approveme@example.com"
    assert notifs[0]["status"] in ("simulated", "sent")


# ── TEST N: duplicate execution → single notification ───────────────────────
def test_n_notification_idempotency(seeded_db):
    event = {"event_id": "evt_n_corr", "amount_paise": 1000, "cause": "payment_timeout"}
    attempt = {"recovery_attempt_id": "ra_n_corr_123", "action": "send_reminder"}
    customer = {"id": "cust_n", "name": "N", "email": "n_corr@example.com"}
    first = notification_service.send_customer_notification(
        merchant_id=MERCHANT, event=event, recovery_attempt=attempt,
        customer=customer, short_url="http://link")
    second = notification_service.send_customer_notification(
        merchant_id=MERCHANT, event=event, recovery_attempt=attempt,
        customer=customer, short_url="http://link")
    assert second.notification_id == first.notification_id
    assert len(db.list_notifications_for_event("evt_n_corr")) == 1


# ── TEST O + real-world payload: full path through HTTP + attribution ───────
@pytest.mark.usefixtures("seeded_db")
def test_o_real_world_payload_end_to_end():
    """payment.failed (real envelope) → customer → event → decision →
    attempt → notification, then payment_link.paid → recovered revenue."""
    with TestClient(app) as client:
        fail_id = f"wh_real_{uuid.uuid4().hex[:8]}"
        pay_id = f"pay_real_{uuid.uuid4().hex[:8]}"
        r = client.post("/webhooks/razorpay", json={
            "id": fail_id, "event": "payment.failed",
            "payload": {"payment": {"entity": {
                "id": pay_id, "amount": 249900, "currency": "INR",
                "email": "realbuyer@example.com", "contact": "+919876543299",
                "customer_id": "cust_rzp_real999",
                "error_reason": "payment_cancelled",
                "error_code": "payment_cancelled"}}}})
        assert r.status_code == 200

        H = {"X-API-Key": "reviveo-dev-key"}
        detail = None
        for item in client.get("/api/events", headers=H).json()["items"]:
            if item.get("razorpay_payment_id") == pay_id:
                detail = client.get(f"/api/events/{item['event_id']}", headers=H).json()
                break
        assert detail is not None, "webhook must create a live_test_mode event"
        assert detail["customer_id"], "customer must be resolved from the envelope"
        customer = db.get_customer(MERCHANT, detail["customer_id"])
        assert customer["email"] == "realbuyer@example.com"
        assert customer["razorpay_customer_id"] == "cust_rzp_real999"
        assert detail["notifications"], "expected a notification record"
        assert detail["notifications"][0]["recipient"] == "realbuyer@example.com"

        if detail["attempts"]:
            attempt = detail["attempts"][0]
            out = client.post("/webhooks/razorpay", json={
                "id": f"wh_paid_{uuid.uuid4().hex[:8]}", "event": "payment_link.paid",
                "payload": {"payment_link": {"entity": {
                    "reference_id": attempt["reference_id"],
                    "amount": attempt["amount_paise"],
                    "id": f"pay_confirm_{uuid.uuid4().hex[:8]}"}}}}).json()
            assert out["status"] == "outcome_applied" and out["paid"] is True
            assert client.get(f"/api/events/{detail['event_id']}",
                              headers=H).json()["status"] == EventStatus.recovered.value


def test_never_invents_contact_data(seeded_db):
    """Garbage/placeholder contact values must not create fake customers."""
    for bad in ["none", "unknown@example", "not-an-email", "", "   ", "123", "+"]:
        event = _ingest(_failed_envelope(email=bad))
        assert event["customer_id"] is None, f"must not resolve customer from {bad!r}"
    assert db.query_one(
        "SELECT COUNT(*) n FROM customers WHERE email IN ('none')")["n"] == 0
