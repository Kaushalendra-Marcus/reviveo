"""Regression tests for the 2026-08-24 audit pass — out-of-order webhook
safety (doc §3.5/§3.6: late/stale webhooks must never regress a terminal
state), server-side merchant scoping, and subscription lifecycle recording.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("seeded_db")

H = {"X-API-Key": "reviveo-dev-key"}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _inject_waiting_event(client: TestClient) -> dict:
    """Push a live-origin payment_failed through the webhook, returning its
    event detail (event is auto-executed to waiting_for_outcome)."""
    fail_id = f"wh_fail_{uuid.uuid4().hex[:8]}"
    r = client.post("/webhooks/razorpay", json={
        "id": fail_id, "event": "payment.failed",
        "customer_id": "cust_sara", "error_code": "payment_timed_out",
        "amount_paise": 99900})
    assert r.status_code == 200
    waiting = client.get("/api/events?status=waiting_for_outcome", headers=H).json()
    target = next(e for e in waiting["items"] if e["origin"] == "live_test_mode")
    detail = client.get(f"/api/events/{target['event_id']}", headers=H).json()
    assert detail["attempts"]
    return detail


def _pay_link(client: TestClient, attempt: dict, pay_id: str) -> dict:
    return client.post("/webhooks/razorpay", json={
        "id": f"wh_paid_{uuid.uuid4().hex[:8]}", "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {
            "reference_id": attempt["reference_id"],
            "amount": attempt["amount_paise"], "id": pay_id}}}}).json()


class TestOutOfOrderOutcomeSafety:
    def test_late_link_expiry_cannot_regress_recovered_event(self, client):
        detail = _inject_waiting_event(client)
        attempt = detail["attempts"][0]
        pay_id = f"pay_confirm_{uuid.uuid4().hex[:8]}"
        paid = _pay_link(client, attempt, pay_id)
        assert paid == {"status": "outcome_applied", "paid": True}
        event_id = detail["event_id"]

        # A *different* link for a second attempt expires afterwards — this
        # must not flip the recovered event to expired. Simulate by expiring
        # via a fresh cancelled webhook on a synthetic second reference.
        late = client.post("/webhooks/razorpay", json={
            "id": f"wh_late_{uuid.uuid4().hex[:8]}", "event": "payment_link.cancelled",
            "payload": {"payment_link": {"entity": {
                "reference_id": f"rvo_second_{uuid.uuid4().hex[:8]}",
                "id": f"plink_late_{uuid.uuid4().hex[:6]}"}}}})
        assert late.status_code == 200  # uncorrelatable -> ok, no event touched

        # Direct regression check: expire the SAME attempt after recovery.
        expired = client.post("/webhooks/razorpay", json={
            "id": f"wh_exp_{uuid.uuid4().hex[:8]}", "event": "payment_link.expired",
            "payload": {"payment_link": {"entity": {
                "reference_id": attempt["reference_id"],
                "id": f"plink_exp_{uuid.uuid4().hex[:6]}"}}}}).json()
        assert expired["status"] == "ignored_terminal"
        assert client.get(f"/api/events/{event_id}", headers=H).json()["status"] == "recovered"

    def test_short_late_payment_does_not_close_a_recovered_event(self, client, temp_db):
        from app import db
        from app.pipeline import attribution

        detail = _inject_waiting_event(client)
        attempt = detail["attempts"][0]
        pay_id = f"pay_full_{uuid.uuid4().hex[:8]}"
        assert _pay_link(client, attempt, pay_id)["paid"] is True
        event_id = detail["event_id"]

        outcome = attribution.attribute_payment(
            recovery_attempt_id=attempt["recovery_attempt_id"],
            razorpay_payment_id=f"pay_short_{uuid.uuid4().hex[:8]}",
            amount_paise=1, recovery_window_days=7,
        )
        assert outcome.accepted is False
        assert db.get_event(event_id)["status"] == "recovered"


class TestWebhookScopingAndLifecycle:
    def test_flat_payload_merchant_id_is_not_trusted(self, client, temp_db):
        from app import db
        rogue_id = f"wh_rogue_{uuid.uuid4().hex[:8]}"
        r = client.post("/webhooks/razorpay", json={
            "id": rogue_id, "event": "payment.failed",
            "merchant_id": "some-other-merchant",
            "customer_id": "cust_priya", "error_code": "card_declined",
            "amount_paise": 123400})
        assert r.status_code == 200
        evs = db.list_events("codecraft", limit=50, offset=0)
        assert any(e["error_code"] == "card_declined" and e["amount_paise"] == 123400
                   for e in evs), "event must be stored under the server-side merchant"
        assert db.list_events("some-other-merchant", limit=10, offset=0) == []

    def test_subscription_state_event_records_before_and_after(self, client, temp_db):
        from app import db
        sub = db.get_subscription("sub_cust_neha")
        assert sub["state"] == "active"
        r = client.post("/webhooks/razorpay", json={
            "id": f"wh_sub_{uuid.uuid4().hex[:8]}", "event": "subscription.halted",
            "payload": {"subscription": {"entity": {"id": "sub_cust_neha"}}}})
        assert r.status_code == 200
        events = [e for e in db.list_events("codecraft", limit=50, offset=0)
                  if e["type"] == "subscription_halted"]
        latest = events[0]
        assert latest["subscription_state_before"] == "active"
        assert latest["subscription_state_after"] == "halted"
        assert db.get_subscription("sub_cust_neha")["state"] == "halted"
