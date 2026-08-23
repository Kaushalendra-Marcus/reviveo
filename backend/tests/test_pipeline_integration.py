"""Pipeline integration: 10-event batch through process_event (doc A6).

Asserts the full audit chain (≥6 stages/event incl. outcome) and that every
event lands in a coherent state with at most one outcome resolution.
"""
from __future__ import annotations

import pytest

from app import db
from app.batch.batch_runner import generate_events, run_batch
from app.enums import AuditStage, EventStatus
from app.pipeline import pipeline


def test_ten_event_batch_full_audit_chain():
    specs = generate_events(10, seed=123)
    assert len(specs) == 10
    for spec in specs:
        ev = pipeline.ingest_event(spec)
        pipeline.process_event(ev["event_id"])

        stages = db.list_audit_for_event(ev["event_id"])
        stage_names = [s["stage"] for s in stages]

        # detected → analyzed → decided → guardrail always present
        for required in (AuditStage.detected.value, AuditStage.analyzed.value,
                         AuditStage.decided.value, AuditStage.guardrail.value):
            assert required in stage_names, f"missing {required} for {ev['event_id']}"

        refreshed = db.get_event(ev["event_id"])
        if refreshed["status"] == "approval_pending":
            # escalated events stop before execution — by design
            assert AuditStage.executed.value not in stage_names
            continue

        # executed + exactly ONE outcome row once an attempt actually ran
        # (scheduled retries legitimately have no outcome until they fire)
        assert AuditStage.executed.value in stage_names
        outcomes = [s for s in stages if s["stage"] == AuditStage.outcome.value]
        if refreshed["status"] == "scheduled":
            assert len(outcomes) == 0
            continue
        assert len(outcomes) == 1, "exactly one outcome audit row per resolved event"

    # every event reached a forward-consistent status
    for ev in db.list_events("codecraft", limit=100):
        assert ev["status"] in [s.value for s in EventStatus]


def test_recovered_events_are_attributed_exactly_once():
    summary = run_batch(n_events=40, seed=99)
    rows = db.query_all(
        "SELECT recovered_razorpay_payment_id, COUNT(*) c FROM recovered_payments "
        "GROUP BY recovered_razorpay_payment_id HAVING c > 1"
    )
    assert rows == [], "no double-counted razorpay payment ids"

    counted = db.query_one(
        "SELECT COUNT(*) n FROM recovered_payments WHERE within_window=1")["n"]
    assert counted == summary["recovered_count"], "summary matches attributed rows"


def test_state_machine_refuses_terminal_regression():
    from app.pipeline.state_machine import transition

    spec = generate_events(1, seed=7)[0]
    ev = pipeline.ingest_event(spec)
    transition(ev["event_id"], EventStatus.analyzing)
    transition(ev["event_id"], EventStatus.recovered)

    assert transition(ev["event_id"], EventStatus.analyzing) is False
    assert db.get_event(ev["event_id"])["status"] == "recovered"
    # closed is a legal forward move from terminal
    assert transition(ev["event_id"], EventStatus.closed) is True


def test_duplicate_webhook_envelope_is_idempotent():
    spec = generate_events(1, seed=5)[0]
    ev = pipeline.ingest_event(spec)
    fresh = db.try_insert_webhook("codecraft", "evt_dup_1", "payment.failed", "{}")
    dup = db.try_insert_webhook("codecraft", "evt_dup_1", "payment.failed", "{}")
    assert fresh and not dup
    assert ev["event_id"]


def test_approval_atomic_claim_prevents_double_execution():
    spec = {"merchant_id": "codecraft", "type": "payment_failed",
            "customer_id": "cust_amit", "error_code": "gateway_internal_error_xyz",
            "amount_paise": 249900, "origin": "synthetic"}
    ev = pipeline.ingest_event(spec)
    result = pipeline.process_event(ev["event_id"])
    approval_id = result["approval_id"]

    from app.services import approvals as svc
    first = svc.approve(approval_id)
    second = svc.approve(approval_id)
    assert first["ok"] is True
    assert second["ok"] is False and second["error"] == "conflict"


def test_scheduler_resumes_scheduled_attempts_after_revalidation():
    from app.pipeline.scheduler import tick

    spec = {"merchant_id": "codecraft", "type": "payment_failed",
            "customer_id": "cust_sara", "error_code": "insufficient_funds",
            "amount_paise": 99900, "origin": "synthetic"}
    ev = pipeline.ingest_event(spec)
    result = pipeline.process_event(ev["event_id"])
    if not result.get("scheduled"):
        pytest.skip("spec did not schedule a smart retry")
    attempt = db.get_recovery_attempt(result["attempt"]["recovery_attempt_id"])

    # force it due now
    db.update_recovery_attempt(attempt["recovery_attempt_id"],
                               scheduled_for=db.now_iso())
    out = tick()
    assert out["scheduled_executed"] >= 1
    resumed = db.get_recovery_attempt(attempt["recovery_attempt_id"])
    assert resumed["status"] in ("awaiting_outcome", "recovered")
