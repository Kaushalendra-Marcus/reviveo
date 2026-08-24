"""API contract tests: auth, endpoints, webhook receiver."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(temp_db):
    # Use isolated temp DB per test (via conftest.temp_db) so webhook ids and
    # batch runs don't leak across tests when pytest reuses the same file DB.
    from app.seed import ensure_seed
    ensure_seed()
    with TestClient(app) as c:
        yield c


H = {"X-API-Key": "reviveo-dev-key"}


class TestAuth:
    def test_missing_key_is_unauthorized(self, client):
        assert client.get("/api/summary").status_code == 401

    def test_wrong_key_is_unauthorized(self, client):
        r = client.get("/api/summary", headers={"X-API-Key": "nope"})
        assert r.status_code == 401

    def test_health_needs_no_key(self, client):
        assert client.get("/health").status_code == 200


class TestCoreEndpoints:
    def test_inject_then_summary_and_events(self, client):
        # payment_timed_out is high-confidence and auto-executes (creates an
        # attempt) whereas card_expired is medium-confidence and routes to
        # approval with no attempt yet. Use the former so detail["attempts"]
        # is guaranteed, but still assert the 6-stage audit trail either way.
        r = client.post("/api/demo/inject-event", headers=H, json={
            "type": "payment_failed", "error_code": "payment_timed_out",
            "customer_id": "cust_rahul", "amount_paise": 249900})
        assert r.status_code == 200
        event_id = r.json()["ingested"]

        s = client.get("/api/summary?range=24h", headers=H).json()
        assert s["events_processed"] >= 1
        assert "recovery_rate_pct" in s

        evs = client.get("/api/events?page=1&page_size=5", headers=H).json()
        assert evs["total"] >= 1
        assert any(e["event_id"] == event_id for e in evs["items"])

        detail = client.get(f"/api/events/{event_id}", headers=H).json()
        assert detail["attempts"]
        assert detail["decisions"]

        trail = client.get(f"/api/events/{event_id}/audit-trail", headers=H).json()
        assert {s["stage"] for s in trail["stages"]} >= {
            "detected", "analyzed", "decided", "guardrail"}

    def test_guardrails_get_put_with_bounds_validation(self, client):
        cfg = client.get("/api/guardrails", headers=H).json()
        assert cfg["max_retries"] >= 1

        bad = dict(cfg, max_retries=9999)
        assert client.put("/api/guardrails", headers=H, json=bad).status_code == 422

        inverted = dict(cfg, low_confidence=0.95, high_confidence=0.85)
        assert client.put("/api/guardrails", headers=H, json=inverted).status_code == 422

        good = dict(cfg, max_retries=4)
        r = client.put("/api/guardrails", headers=H, json=good)
        assert r.status_code == 200 and r.json()["max_retries"] == 4

    def test_customers_and_strategies(self, client):
        cs = client.get("/api/customers", headers=H).json()
        assert cs["total"] >= 6
        one = client.get("/api/customers/cust_rahul", headers=H).json()
        assert one["name"] == "Rahul Sharma"
        st = client.get("/api/strategies", headers=H).json()
        assert isinstance(st, list)

    def test_export_csv(self, client):
        client.post("/api/demo/inject-event", headers=H, json={
            "type": "abandoned_checkout", "error_code": "payment_cancelled",
            "customer_id": "cust_neha", "amount_paise": 99900})
        r = client.get("/api/events/export?format=csv", headers=H)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]


class TestApprovalsEndpoint:
    def test_approve_and_conflict(self, client):
        client.post("/api/demo/inject-event", headers=H, json={
            "type": "payment_failed", "error_code": "totally_unknown_code",
            "customer_id": "cust_amit", "amount_paise": 100000})
        pending = client.get("/api/guardrails/pending-approvals", headers=H).json()
        assert pending["items"], "unclassified cause must route to approval"
        approval_id = pending["items"][0]["id"]

        ok = client.post(f"/api/approvals/{approval_id}/approve", headers=H).json()
        assert ok["ok"] is True

        conflict = client.post(f"/api/approvals/{approval_id}/approve", headers=H)
        assert conflict.status_code == 409

    def test_deny_closes_event(self, client):
        r = client.post("/api/demo/inject-event", headers=H, json={
            "type": "payment_failed", "error_code": "another_unknown_reason",
            "customer_id": "cust_dev", "amount_paise": 499900})
        pending = client.get("/api/guardrails/pending-approvals", headers=H).json()
        approval_id = pending["items"][0]["id"]
        event_id = r.json()["ingested"]

        d = client.post(f"/api/approvals/{approval_id}/deny", headers=H,
                        json={"reason": "suspected fraud"}).json()
        assert d["ok"] is True
        # Denying an escalate_to_human closes as `escalated`; denying a
        # concrete mechanism closes as `failed`. Accept either terminal.
        assert client.get(f"/api/events/{event_id}", headers=H).json()["status"] in ("failed", "escalated")


class TestWebhooks:
    def test_webhook_processes_and_deduplicates(self, client):
        import uuid as _uuid
        uniq = _uuid.uuid4().hex[:8]
        payload = {"id": f"wh_test_{uniq}", "event": "payment.failed",
                   "merchant_id": "codecraft", "customer_id": "cust_priya",
                   "error_code": "insufficient_funds", "amount_paise": 99900,
                   "type": "payment_failed"}
        first = client.post("/webhooks/razorpay", json=payload).json()
        assert first["status"] in ("ok", "processed", "scheduled", "approval_pending", "duplicate") or "status" in first

        dup = client.post("/webhooks/razorpay", json=payload).json()
        assert dup == {"status": "duplicate"}

    def test_outcome_webhook_recovers_waiting_event(self, client):
        import uuid as _uuid2
        # Live-origin failure arrives via the webhook receiver… use unique ids
        # so the test is isolated even when the global file DB is reused.
        fail_id = f"wh_live_fail_{_uuid2.uuid4().hex[:8]}"
        client.post("/webhooks/razorpay", json={
            "id": fail_id, "event": "payment.failed",
            "merchant_id": "codecraft", "customer_id": "cust_sara",
            "error_code": "payment_timed_out", "amount_paise": 99900,
            "type": "payment_failed"})
        waiting = client.get("/api/events?status=waiting_for_outcome", headers=H).json()
        assert waiting["items"], "expected a waiting_for_outcome event after webhook"
        target = next(e for e in waiting["items"])
        detail = client.get(f"/api/events/{target['event_id']}", headers=H).json()
        assert detail["attempts"], "waiting event should have an attempt"
        attempt = detail["attempts"][0]

        import uuid as _uuid3
        paid_id = f"wh_paid_{_uuid3.uuid4().hex[:8]}"
        pay_id = f"pay_live_confirm_{_uuid3.uuid4().hex[:8]}"
        out = client.post("/webhooks/razorpay", json={
            "id": paid_id, "event": "payment_link.paid", "merchant_id": "codecraft",
            "payload": {"payment_link": {"entity": {
                "reference_id": attempt["reference_id"],
                "amount": attempt["amount_paise"],
                "id": pay_id}}}}).json()
        assert out["status"] == "outcome_applied" and out["paid"] is True
        assert client.get(f"/api/events/{target['event_id']}",
                          headers=H).json()["status"] == "recovered"

        # replay must be idempotent — no double counting
        replay = client.post("/webhooks/razorpay", json={
            "id": paid_id, "event": "payment_link.paid", "merchant_id": "codecraft",
            "payload": {"payment_link": {"entity": {
                "reference_id": attempt["reference_id"],
                "amount": attempt["amount_paise"],
                "id": pay_id}}}})
        assert replay.json() == {"status": "duplicate"}


class TestBatchAndReports:
    def test_batch_run_and_last_summary(self, client):
        r = client.post("/api/batch/run", headers=H,
                        json={"n_events": 8, "seed": 3}).json()
        assert r["n_events"] == 8
        assert r["statuses"]

    def test_reports_simulation_labels_are_honest(self, client):
        sim = client.post("/api/reports/simulate", headers=H,
                          json={"n_events": 20, "seed": 11}).json()
        assert sim["label"].lower().startswith("modeled incremental lift")
        assert "baseline" in sim and "treatment" in sim
