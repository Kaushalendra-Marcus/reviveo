"""Identity-chain regression tests: every customer gets their own detected
email through payment → customer → event → attempt → link → notification.

All addresses below are per-test FIXTURE data (alice/bob/customer.real) —
production code contains no hardcoded recipient (see test_no_hardcoded_email).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from app import db
from app.config import RunMode, settings
from app.enums import Action, ExecutionMechanism
from app.services import execution_service, notification_service
from app.webhooks import webhook as webhook_module

MERCHANT = "codecraft"
VOID = "void@razorpay.com"


def _failed_envelope(*, email=None, contact=None, error_reason="payment_cancelled",
                     amount=49900, pay_id=None, event_uuid=None, entity_notes=None):
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
    if entity_notes is not None:
        entity["notes"] = entity_notes
    return {
        "id": event_uuid or f"evt_rzp_{uuid.uuid4().hex[:10]}",
        "event": "payment.failed",
        "payload": {"payment": {"entity": entity}},
    }


def _ingest(payload) -> dict:
    webhook_module._handle_payment_failed(MERCHANT, payload)
    rows = db.query_all(
        "SELECT * FROM events WHERE merchant_id=? ORDER BY created_at DESC LIMIT 1",
        (MERCHANT,),
    )
    assert rows
    return rows[0]


def _enable_live_email(monkeypatch):
    monkeypatch.setattr(settings, "run_mode", RunMode.live)
    monkeypatch.setattr(settings, "notification_email_enabled", True)
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key_do_not_use")


# ── §18: exact incident regression ──────────────────────────────────────────
def test_exact_incident_placeholder_vs_trusted(seeded_db):
    db.insert_customer({"id": "cust_test", "merchant_id": MERCHANT,
                        "name": "Real Customer", "email": "customer.real@example.com",
                        "phone": "+911111111111"})
    event = _ingest(_failed_envelope(email=VOID, contact="+911111111111"))

    assert event["customer_id"] == "cust_test"
    assert db.get_customer(MERCHANT, "cust_test")["email"] == "customer.real@example.com"

    notifs = db.list_notifications_for_event(event["event_id"])
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "customer.real@example.com"
    assert VOID not in (notifs[0]["recipient"] or "")


# ── §19: normal customer — full identity chain persisted ────────────────────
def test_normal_customer_full_chain(seeded_db):
    event = _ingest(_failed_envelope(email="alice@example.com",
                                     contact="+912222222222"))
    assert event["customer_id"]
    alice = db.get_customer(MERCHANT, event["customer_id"])
    assert alice["email"] == "alice@example.com"

    attempts = db.list_attempts_for_event(event["event_id"])
    assert len(attempts) == 1
    assert attempts[0]["customer_id"] == alice["id"]  # §8 attempt linkage

    notifs = db.list_notifications_for_event(event["event_id"])
    assert len(notifs) == 1
    assert notifs[0]["recipient"] == "alice@example.com"
    assert notifs[0]["customer_id"] == alice["id"]  # §16 audit field


# ── §20: second customer is isolated — no global/static email ───────────────
def test_second_customer_gets_own_email(seeded_db):
    first = _ingest(_failed_envelope(email="alice@example.com"))
    second = _ingest(_failed_envelope(email="bob@example.com"))

    assert first["customer_id"] != second["customer_id"]
    n1 = db.list_notifications_for_event(first["event_id"])[0]
    n2 = db.list_notifications_for_event(second["event_id"])[0]
    assert n1["recipient"] == "alice@example.com"
    assert n2["recipient"] == "bob@example.com"
    assert "alice" not in n2["recipient"]


# ── §21: placeholder with no alternative → skipped, Resend untouched ────────
def test_placeholder_no_alternative_skips(seeded_db, monkeypatch):
    _enable_live_email(monkeypatch)
    with patch.object(notification_service.ResendEmailProvider, "send_email",
                      side_effect=AssertionError("Resend must not be called")):
        event = _ingest(_failed_envelope(email=VOID))
        assert event["customer_id"] is None
        notifs = db.list_notifications_for_event(event["event_id"])
        assert notifs[0]["status"] == "skipped"
        assert notifs[0]["error"] == "No trusted customer email available"


# ── §12 CASE B: failed recovery payment resolves to attempt customer ────────
def test_case_b_failed_recovery_payment_reuses_attempt_customer(seeded_db):
    db.insert_customer({"id": "cust_caseb", "merchant_id": MERCHANT,
                        "name": "Case B", "email": "caseb@example.com",
                        "phone": "+913333333333"})
    event_id = f"evt_caseb_{uuid.uuid4().hex[:8]}"
    db.insert_event({"event_id": event_id, "merchant_id": MERCHANT,
                     "customer_id": "cust_caseb", "type": "payment_failed",
                     "error_code": "card_declined", "amount_paise": 99900,
                     "status": "detected", "origin": "synthetic",
                     "created_at": "2026-09-04T12:00:00Z",
                     "updated_at": "2026-09-04T12:00:00Z"})
    res = execution_service.execute_action(
        merchant_id=MERCHANT, event=db.get_event(event_id),
        action=Action.retry_and_notify,
        mechanism=ExecutionMechanism.new_recovery_payment,
        customer=db.get_customer(MERCHANT, "cust_caseb"))
    before = db.count_customers(MERCHANT)

    # Recovery payment fails: entity carries void email (typed nothing /
    # test dummy) but notes inherit Reviveo's link correlation keys.
    failed = _ingest(_failed_envelope(
        email=VOID, contact="+917830328929",
        entity_notes={"event_id": event_id,
                      "recovery_attempt_id": res.recovery_attempt_id,
                      "attempt_number": "1", "source": "reviveo"}))
    assert failed["customer_id"] == "cust_caseb"
    assert db.count_customers(MERCHANT) == before  # no brand-new customer
    assert db.query_all("SELECT * FROM customers WHERE email=?", (VOID,)) == []


# ── §23: payment-link correlation end to end ────────────────────────────────
def test_payment_link_correlation_back_to_customer(seeded_db):
    from app.enums import EventStatus
    from app.services import approvals
    # card_declined → retry_and_notify → approval → live link with plink id.
    event = _ingest(_failed_envelope(email="linkowner@example.com",
                                     error_reason="card_declined",
                                     amount=99900))
    assert event["status"] == EventStatus.approval_pending.value
    owner_id = event["customer_id"]
    pending = [a for a in db.list_pending_approvals(MERCHANT)
               if a["event_id"] == event["event_id"]]
    assert approvals.approve(pending[0]["id"], resolved_by="test")["ok"] is True

    attempts = db.list_attempts_for_event(event["event_id"])
    assert attempts[0]["razorpay_ref"]  # persisted plink id (§10)
    assert attempts[0]["customer_id"] == owner_id  # §8 attempt linkage

    # A later webhook tied to that link (notes keys) resolves to the owner.
    notes = {"event_id": event["event_id"],
             "recovery_attempt_id": attempts[0]["recovery_attempt_id"],
             "attempt_number": "1", "source": "reviveo"}
    later = _ingest(_failed_envelope(email=VOID, entity_notes=notes))
    assert later["customer_id"] == owner_id


# ── §24/25: Resend mock — exact recipient, provider recorded, failure kept ──
def test_resend_exact_recipient_and_provider(seeded_db, monkeypatch):
    _enable_live_email(monkeypatch)
    calls: list[dict] = []

    def fake_send(self, *, to, subject, text_body, html_body, from_email):
        calls.append({"to": to})
        return True, "re_msg_chain1", None

    with patch.object(notification_service.ResendEmailProvider, "send_email", fake_send):
        event = _ingest(_failed_envelope(email="chaina@example.com"))
        notifs = db.list_notifications_for_event(event["event_id"])
        assert notifs[0]["status"] == "sent"
        assert notifs[0]["provider"] == "resend"
        assert notifs[0]["provider_message_id"] == "re_msg_chain1"
    assert [c["to"] for c in calls] == ["chaina@example.com"]
    assert all(c["to"] != VOID for c in calls)


def test_resend_failure_never_sent(seeded_db, monkeypatch):
    _enable_live_email(monkeypatch)

    def fake_fail(self, *, to, subject, text_body, html_body, from_email):
        return False, None, "Resend API error (422): bad sender"

    with patch.object(notification_service.ResendEmailProvider, "send_email", fake_fail):
        event = _ingest(_failed_envelope(email="chainfail@example.com"))
        notifs = db.list_notifications_for_event(event["event_id"])
        assert notifs[0]["status"] == "failed"
        assert "422" in (notifs[0]["error"] or "")
        assert notifs[0]["provider_message_id"] is None
        assert notifs[0]["provider"] == "resend"


def test_simulated_rows_record_provider(seeded_db):
    event = _ingest(_failed_envelope(email="simchain@example.com"))
    notifs = db.list_notifications_for_event(event["event_id"])
    assert notifs[0]["status"] == "simulated"
    assert notifs[0]["provider"] == "simulated"


# ── §27: no hardcoded recipient anywhere in app source ──────────────────────
def test_no_hardcoded_email():
    import pathlib
    import re
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    # sender default + placeholder denylist + seed fixtures are the only
    # acceptable address literals (checked in review); no recipient fallback.
    forbidden = re.compile(
        r"(DEFAULT.*EMAIL|FALLBACK.*EMAIL|email\s*=\s*[\"'](?!void@razorpay|onboarding@)[^\"']*@[^\"']+[\"'])",
        re.IGNORECASE)
    hits = []
    for path in app_dir.rglob("*.py"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if forbidden.search(line):
                hits.append(f"{path.name}:{i}: {line.strip()}")
    assert hits == [], f"hardcoded recipient fallback found: {hits}"
