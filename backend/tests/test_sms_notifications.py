"""Tests for the Twilio SMS channel (same architecture as email: idempotency,
trusted-contact checks, AI message + fallback, provider/simulated persistence).

The SMS channel is flag-gated (TWILIO_SMS_ENABLED): with the flag off,
execution creates email rows only — existing behavior byte-for-byte.
No test performs a real network call or sends a real SMS.
"""
from __future__ import annotations

import base64
import io
import json
import urllib.error
import uuid
from unittest.mock import patch

import pytest

from app import db
from app.config import RunMode, settings
from app.enums import Action, EventStatus, ExecutionMechanism
from app.services import execution_service, notification_service

MERCHANT = "codecraft"
VALID_PHONE = "+919812345670"
VALID_EMAIL = "smsbuyer@example.com"


def _enable_sms(monkeypatch, *, live=False, configured=True):
    monkeypatch.setattr(settings, "twilio_sms_enabled", True)
    if live:
        monkeypatch.setattr(settings, "run_mode", RunMode.live)
    if configured:
        monkeypatch.setattr(settings, "twilio_account_sid", "AC_test_sid")
        monkeypatch.setattr(settings, "twilio_auth_token", "test_token")
        monkeypatch.setattr(settings, "twilio_phone_number", "+15005550006")
    # Keep Razorpay execution synthetic even when the notification gate is
    # live: these tests cover SMS, never the payment provider.
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")


def _customer(cid="cust_sms", phone=VALID_PHONE, email=VALID_EMAIL):
    return {"id": cid, "merchant_id": MERCHANT, "name": "Sms Buyer",
            "email": email, "phone": phone,
            "total_recovered_paise": 0, "failed_payment_count": 0,
            "created_at": "2026-09-01T00:00:00Z"}


def _event(eid, cid):
    return {"event_id": eid, "merchant_id": MERCHANT, "customer_id": cid,
            "subscription_id": None, "invoice_id": None, "type": "payment_failed",
            "cause": "bank_declined", "error_code": "card_declined",
            "amount_paise": 99900, "status": "detected", "origin": "synthetic",
            "created_at": "2026-09-04T12:00:00Z", "updated_at": "2026-09-04T12:00:00Z"}


# ── Flag off (default): no SMS rows — existing behavior preserved ───────────
def test_sms_disabled_by_default(seeded_db):
    db.insert_customer(_customer())
    eid = f"evt_sms_off_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms"))
    execution_service.execute_action(
        merchant_id=MERCHANT, event=db.get_event(eid),
        action=Action.retry_and_notify,
        mechanism=ExecutionMechanism.new_recovery_payment,
        customer=db.get_customer(MERCHANT, "cust_sms"))
    rows = db.list_notifications_for_event(eid)
    assert {r["channel"] for r in rows} == {"email"}


# ── Enabled + synthetic: simulated SMS with link, no HTTP ───────────────────
def test_sms_simulated_in_synthetic_mode(seeded_db, monkeypatch):
    _enable_sms(monkeypatch)
    db.insert_customer(_customer())
    eid = f"evt_sms_sim_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms"))
    with patch("urllib.request.urlopen",
               side_effect=AssertionError("no real HTTP in synthetic mode")):
        execution_service.execute_action(
            merchant_id=MERCHANT, event=db.get_event(eid),
            action=Action.retry_and_notify,
            mechanism=ExecutionMechanism.new_recovery_payment,
            customer=db.get_customer(MERCHANT, "cust_sms"))
    sms = db.get_notification_by_attempt(
        db.list_attempts_for_event(eid)[0]["recovery_attempt_id"], channel="sms")
    assert sms is not None
    assert sms["status"] == "simulated"
    assert sms["provider"] == "simulated"
    assert sms["recipient"] == VALID_PHONE
    assert sms["provider_message_id"].startswith("sim_msg_")
    assert "rzp.io" in (sms["body"] or "")  # recovery link present


# ── Enabled but no phone → skipped with clear reason ────────────────────────
def test_sms_skipped_without_phone(seeded_db, monkeypatch):
    _enable_sms(monkeypatch, live=True)
    db.insert_customer(_customer(cid="cust_sms_nophone", phone=None))
    eid = f"evt_sms_noph_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms_nophone"))
    with patch.object(notification_service.TwilioSmsProvider, "send_sms",
                      side_effect=AssertionError("must not send without phone")):
        execution_service.execute_action(
            merchant_id=MERCHANT, event=db.get_event(eid),
            action=Action.retry_and_notify,
            mechanism=ExecutionMechanism.new_recovery_payment,
            customer=db.get_customer(MERCHANT, "cust_sms_nophone"))
    sms = db.get_notification_by_attempt(
        db.list_attempts_for_event(eid)[0]["recovery_attempt_id"], channel="sms")
    assert sms["status"] == "skipped"
    assert sms["recipient"] == "none"
    assert sms["error"] == "No trusted customer phone available"


# ── Placeholder phones never sent ───────────────────────────────────────────
@pytest.mark.parametrize("bad_phone", ["+917830328929", "+916349562698",
                                       "+911111111111", "+910000000000"])
def test_sms_placeholder_phones_rejected(seeded_db, monkeypatch, bad_phone):
    _enable_sms(monkeypatch, live=True)
    assert db.trusted_phone(bad_phone) is None
    db.insert_customer(_customer(cid=f"cust_sms_ph_{uuid.uuid4().hex[:6]}",
                                 phone=bad_phone))
    cid = db.query_one(
        "SELECT id FROM customers WHERE phone=?", (bad_phone,))["id"]
    eid = f"evt_sms_ph_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, cid))
    with patch.object(notification_service.TwilioSmsProvider, "send_sms",
                      side_effect=AssertionError("must never send to placeholder")):
        execution_service.execute_action(
            merchant_id=MERCHANT, event=db.get_event(eid),
            action=Action.retry_and_notify,
            mechanism=ExecutionMechanism.new_recovery_payment,
            customer=db.get_customer(MERCHANT, cid))
    sms = db.get_notification_by_attempt(
        db.list_attempts_for_event(eid)[0]["recovery_attempt_id"], channel="sms")
    assert sms["status"] == "skipped"


def test_trusted_phone_accepts_real_numbers():
    assert db.trusted_phone("+919812345670") == "+919812345670"
    assert db.trusted_phone("  +1 650-253-0000 ") == "+16502530000"
    assert db.trusted_phone(None) is None
    assert db.trusted_phone("abc") is None
    assert db.trusted_phone("+91") is None


# ── Live + configured: real send, SID recorded, called once ─────────────────
def test_sms_live_send(seeded_db, monkeypatch):
    _enable_sms(monkeypatch, live=True)
    calls: list[dict] = []

    def fake_send(self, *, to, body, from_number):
        calls.append({"to": to, "from_number": from_number, "body": body})
        return True, "SM_test_sid_123", None

    db.insert_customer(_customer())
    eid = f"evt_sms_live_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms"))
    with patch.object(notification_service.TwilioSmsProvider, "send_sms", fake_send):
        execution_service.execute_action(
            merchant_id=MERCHANT, event=db.get_event(eid),
            action=Action.retry_and_notify,
            mechanism=ExecutionMechanism.new_recovery_payment,
            customer=db.get_customer(MERCHANT, "cust_sms"))
    assert len(calls) == 1
    assert calls[0]["to"] == VALID_PHONE
    assert calls[0]["from_number"] == "+15005550006"
    assert "rzp.io" in calls[0]["body"]
    sms = db.get_notification_by_attempt(
        db.list_attempts_for_event(eid)[0]["recovery_attempt_id"], channel="sms")
    assert sms["status"] == "sent"
    assert sms["provider"] == "twilio"
    assert sms["provider_message_id"] == "SM_test_sid_123"


# ── Twilio rejection (e.g. trial 21608): failed, never sent ─────────────────
def test_sms_twilio_rejection_failed(seeded_db, monkeypatch):
    _enable_sms(monkeypatch, live=True)

    def fake_fail(self, *, to, body, from_number):
        return False, None, "Twilio API error (400): Error 21608 unverified"

    db.insert_customer(_customer())
    eid = f"evt_sms_fail_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms"))
    with patch.object(notification_service.TwilioSmsProvider, "send_sms", fake_fail):
        execution_service.execute_action(
            merchant_id=MERCHANT, event=db.get_event(eid),
            action=Action.retry_and_notify,
            mechanism=ExecutionMechanism.new_recovery_payment,
            customer=db.get_customer(MERCHANT, "cust_sms"))
    sms = db.get_notification_by_attempt(
        db.list_attempts_for_event(eid)[0]["recovery_attempt_id"], channel="sms")
    assert sms["status"] == "failed"
    assert "21608" in (sms["error"] or "")
    assert sms["provider_message_id"] is None


# ── AI failure → fallback body, still sends ─────────────────────────────────
def test_sms_ai_fallback_still_sends(seeded_db, monkeypatch):
    from app.services.ai_service import AIResult
    _enable_sms(monkeypatch)
    db.insert_customer(_customer())
    eid = f"evt_sms_ai_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms"))
    with patch("app.services.notification_service.ai_service.call_claude",
               return_value=AIResult(text=None, used=False, model="m",
                                     latency_ms=1, fallback_triggered=True)):
        execution_service.execute_action(
            merchant_id=MERCHANT, event=db.get_event(eid),
            action=Action.retry_and_notify,
            mechanism=ExecutionMechanism.new_recovery_payment,
            customer=db.get_customer(MERCHANT, "cust_sms"))
    sms = db.get_notification_by_attempt(
        db.list_attempts_for_event(eid)[0]["recovery_attempt_id"], channel="sms")
    assert sms["status"] == "simulated"
    assert bool(sms["ai_generated"]) is False
    assert "999.00" in (sms["body"] or "")


# ── Idempotency: same attempt twice → one SMS row ────────────────────────────
def test_sms_idempotency(seeded_db, monkeypatch):
    _enable_sms(monkeypatch)
    customer = _customer()
    event = {"event_id": "evt_sms_idem", "amount_paise": 1000, "cause": "bank_declined"}
    attempt = {"recovery_attempt_id": "ra_sms_idem_1", "action": "send_reminder"}
    first = notification_service.send_sms_notification(
        merchant_id=MERCHANT, event=event, recovery_attempt=attempt,
        customer=customer, short_url="https://rzp.io/x")
    second = notification_service.send_sms_notification(
        merchant_id=MERCHANT, event=event, recovery_attempt=attempt,
        customer=customer, short_url="https://rzp.io/x")
    assert second.notification_id == first.notification_id
    assert len(db.list_notifications_for_event("evt_sms_idem")) == 1


# ── Approval flow: SMS only after approval ───────────────────────────────────
def test_sms_after_approval(seeded_db, monkeypatch):
    from app.pipeline import pipeline
    from app.services import approvals
    _enable_sms(monkeypatch)
    db.insert_customer(_customer(cid="cust_sms_appr"))
    eid = f"evt_sms_appr_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_sms_appr"))
    res = pipeline.process_event(db.get_event(eid))
    assert res["status"] == EventStatus.approval_pending.value
    assert db.list_notifications_for_event(eid) == []
    pending = [a for a in db.list_pending_approvals(MERCHANT) if a["event_id"] == eid]
    assert approvals.approve(pending[0]["id"], resolved_by="merchant-test")["ok"] is True
    channels = {n["channel"]: n for n in db.list_notifications_for_event(eid)}
    assert channels["email"]["recipient"] == VALID_EMAIL
    assert channels["sms"]["recipient"] == VALID_PHONE
    assert channels["sms"]["status"] == "simulated"


# ── Provider unit: request shape, auth, error paths ─────────────────────────
def test_twilio_provider_request_shape(monkeypatch):
    captured: dict = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"sid": "SM_abc"}).encode()

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["ctype"] = req.headers.get("Content-type")
        captured["fields"] = dict(urllib.parse.parse_qsl(req.data.decode()))
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = notification_service.TwilioSmsProvider("AC_sid", "tok")
    ok, sid, err = provider.send_sms(to="+919812345670", body="hi link",
                                     from_number="+15005550006")
    assert (ok, sid, err) == (True, "SM_abc", None)
    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC_sid/Messages.json"
    assert captured["auth"] == "Basic " + base64.b64encode(b"AC_sid:tok").decode()
    assert captured["ctype"] == "application/x-www-form-urlencoded"
    assert captured["fields"] == {"To": "+919812345670", "From": "+15005550006",
                                  "Body": "hi link"}


def test_twilio_provider_http_error(monkeypatch):
    import urllib.parse  # noqa: F401  (kept explicit for clarity)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"code": 21608}'))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = notification_service.TwilioSmsProvider("AC_sid", "tok")
    ok, sid, err = provider.send_sms(to="+919812345670", body="hi",
                                     from_number="+15005550006")
    assert ok is False and sid is None
    assert "400" in err and "21608" in err


# ── Retry endpoint covers SMS symmetrically ─────────────────────────────────
def test_retry_redispatches_sms(seeded_db, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    _enable_sms(monkeypatch)
    H = {"X-API-Key": "reviveo-dev-key"}
    db.insert_customer(_customer(cid="cust_sms_retry"))
    eid = f"evt_sms_retry_{uuid.uuid4().hex[:8]}"
    # retry_and_notify on bank_declined routes to approval first.
    db.insert_event(_event(eid, "cust_sms_retry"))
    with TestClient(app) as c:
        from app.pipeline import pipeline as pipeline_mod
        from app.services import approvals as approvals_mod
        assert pipeline_mod.process_event(db.get_event(eid))["status"] == \
            EventStatus.approval_pending.value
        pending = [a for a in db.list_pending_approvals(MERCHANT)
                   if a["event_id"] == eid]
        assert approvals_mod.approve(pending[0]["id"])["ok"] is True
        # Both channels delivered (simulated); retry must refuse duplicates.
        r = c.post(f"/api/events/{eid}/notifications/retry", headers=H)
        assert r.status_code == 409


# ── Audit trail carries the message + AI proof (both channels) ──────────────
def test_notification_audit_rows(seeded_db, monkeypatch):
    _enable_sms(monkeypatch)
    db.insert_customer(_customer(cid="cust_audit"))
    eid = f"evt_audit_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_audit"))
    execution_service.execute_action(
        merchant_id=MERCHANT, event=db.get_event(eid),
        action=Action.retry_and_notify,
        mechanism=ExecutionMechanism.new_recovery_payment,
        customer=db.get_customer(MERCHANT, "cust_audit"))
    rows = db.list_audit_for_event(eid)
    by_channel = {}
    for r in rows:
        ch = (r["payload"] or {}).get("channel")
        if ch in ("email", "sms"):
            by_channel[ch] = r
    assert set(by_channel) == {"email", "sms"}
    for ch, r in by_channel.items():
        assert r["stage"] == "executed"
        assert (r["payload"] or {}).get("body")  # exact message text
        assert (r["payload"] or {}).get("notification_id")
        assert (r["payload"] or {}).get("status") == "simulated"
    # AI-vs-fallback proof is on the row itself.
    assert all("ai_used" in r and "fallback_triggered" in r for r in by_channel.values())


def test_skipped_notification_audited(seeded_db, monkeypatch):
    _enable_sms(monkeypatch)
    db.insert_customer(_customer(cid="cust_audskip", phone=None, email=None))
    eid = f"evt_audskip_{uuid.uuid4().hex[:8]}"
    db.insert_event(_event(eid, "cust_audskip"))
    execution_service.execute_action(
        merchant_id=MERCHANT, event=db.get_event(eid),
        action=Action.retry_and_notify,
        mechanism=ExecutionMechanism.new_recovery_payment,
        customer=db.get_customer(MERCHANT, "cust_audskip"))
    skipped = [r for r in db.list_audit_for_event(eid)
               if (r["payload"] or {}).get("status") == "skipped"]
    assert { (r["payload"] or {}).get("channel") for r in skipped } == {"email", "sms"}
