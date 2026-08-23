"""API contract tests: auth, endpoints, webhook receiver."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
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
        r = client.post("/api/demo/inject-event", headers=H, json={
            "type": "payment_failed", "error_code": "card_expired",
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
        assert client.get(f"/api/events/{event_id}", headers=H).json()["status"] == "failed"


class TestWebhooks:
    def test_webhook_processes_and_deduplicates(self, client):
        payload = {"id": "wh_test_42", "event": "payment.failed",
                   "merchant_id": "codecraft", "customer_id": "cust_priya",
                   "error_code": "insufficient_funds", "amount_paise": 99900,
                   "type": "payment_failed"}
        first = client.post("/webhooks/razorpay", json=payload).json()
        assert first["status"] in ("processed", "scheduled", "approval_pending")

        dup = client.post("/webhooks/razorpay", json=payload).json()
        assert dup == {"status": "duplicate"}

    def test_outcome_webhook_recovers_waiting_event(self, client):
        # Live-origin failure arrives via the webhook receiver…
        client.post("/webhooks/razorpay", json={
            "id": "wh_live_fail_1", "event": "payment.failed",
            "merchant_id": "codecraft", "customer_id": "cust_sara",
            "error_code": "payment_timed_out", "amount_paise": 99900,
            "type": "payment_failed"})
        waiting = client.get("/api/events?status=waiting_for_outcome", headers=H).json()
        target = next(e for e in waiting["items"])
        detail = client.get(f"/api/events/{target['event_id']}", headers=H).json()
        attempt = detail["attempts"][0]

        out = client.post("/webhooks/razorpay", json={
            "id": "wh_paid_1", "event": "payment_link.paid", "merchant_id": "codecraft",
            "payload": {"payment_link": {"entity": {
                "reference_id": attempt["reference_id"],
                "amount": attempt["amount_paise"],
                "id": "pay_live_confirm_1"}}}}).json()
        assert out["status"] == "outcome_applied" and out["paid"] is True
        assert client.get(f"/api/events/{target['event_id']}",
                          headers=H).json()["status"] == "recovered"

        # replay must be idempotent — no double counting
        replay = client.post("/webhooks/razorpay", json={
            "id": "wh_paid_1", "event": "payment_link.paid", "merchant_id": "codecraft",
            "payload": {"payment_link": {"entity": {
                "reference_id": attempt["reference_id"],
                "amount": attempt["amount_paise"],
                "id": "pay_live_confirm_1"}}}})
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
        assert sim["label"].startswith("modeled incremental lift")
        assert "baseline" in sim and "treatment" in sim
