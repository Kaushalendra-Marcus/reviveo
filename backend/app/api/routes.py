"""REST API for the Reviveo dashboard (doc A1). Every route is protected by
the shared X-API-Key header (doc A4) except the Razorpay webhook, which is
authenticated by signature instead and lives in `webhooks/webhook.py`.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from .. import db
from ..config import settings
from ..deps import require_api_key
from ..enums import EventStatus
from . import schemas

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(require_api_key)])


def _merchant_id() -> str:
    # Single-merchant hackathon scope (doc §3.15); every query is still
    # merchant-scoped so this is the only place that would change to add
    # real multi-tenant auth.
    return settings.default_merchant_id


def _since(range_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=range_days)).isoformat()


# ── Summary / dashboard ───────────────────────────────────────────────────────
@router.get("/summary", response_model=schemas.SummaryOut)
def get_summary(range: int = Query(default=30, ge=1, le=365, alias="range")) -> schemas.SummaryOut:
    merchant_id = _merchant_id()
    m = db.summary_metrics(merchant_id, _since(range))
    recovery_rate = (m["recovered_count"] / m["events_processed"]) if m["events_processed"] else 0.0
    return schemas.SummaryOut(range_days=range, recovery_rate=round(recovery_rate, 4), **m)


@router.get("/summary/timeseries", response_model=list[schemas.TimeseriesPoint])
def get_timeseries(
    range: int = Query(default=30, ge=1, le=365, alias="range"),
    metric: str = Query(default="recovered", pattern="^(recovered|at_risk)$"),
) -> list[schemas.TimeseriesPoint]:
    merchant_id = _merchant_id()
    since = _since(range)
    rows = (db.timeseries_recovered if metric == "recovered" else db.timeseries_at_risk)(merchant_id, since)
    return [schemas.TimeseriesPoint(**r) for r in rows]


@router.get("/summary/strategy-breakdown", response_model=list[schemas.StrategyBreakdownRow])
def get_strategy_breakdown(range: int = Query(default=30, ge=1, le=365, alias="range")) -> list[schemas.StrategyBreakdownRow]:
    merchant_id = _merchant_id()
    rows = db.strategy_breakdown(merchant_id, _since(range))
    out = []
    for r in rows:
        rate = (r["recovered_count"] / r["attempts"]) if r["attempts"] else 0.0
        out.append(schemas.StrategyBreakdownRow(
            mechanism=r["mechanism"] or "unknown", attempts=r["attempts"],
            recovered_paise=r["recovered_paise"], recovered_count=r["recovered_count"],
            success_rate=round(rate, 4),
        ))
    return out


# ── Events ────────────────────────────────────────────────────────────────────
def _event_to_out(row: dict) -> schemas.EventOut:
    decision = db.get_latest_decision(row["event_id"])
    return schemas.EventOut(
        **{**row, "payment_recovered": bool(row["payment_recovered"]),
           "subscription_restored": bool(row["subscription_restored"])},
        latest_action=decision["action"] if decision else None,
        latest_confidence=decision["confidence"] if decision else None,
        latest_risk_tier=decision["risk_tier"] if decision else None,
    )


@router.get("/events", response_model=schemas.PaginatedEvents)
def list_events(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    cause: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> schemas.PaginatedEvents:
    merchant_id = _merchant_id()
    offset = (page - 1) * page_size
    rows = db.list_events(merchant_id, status=status_filter, cause=cause, limit=page_size, offset=offset)
    total = db.count_events(merchant_id, status=status_filter, cause=cause)
    return schemas.PaginatedEvents(items=[_event_to_out(r) for r in rows], total=total,
                                    page=page, page_size=page_size)


@router.get("/events/export")
def export_events(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
) -> StreamingResponse:
    merchant_id = _merchant_id()
    rows = db.list_events(merchant_id, status=status_filter, limit=10_000, offset=0)
    if format == "json":
        import json
        buf = io.StringIO(json.dumps(rows, default=str))
        return StreamingResponse(iter([buf.getvalue()]), media_type="application/json",
                                  headers={"Content-Disposition": "attachment; filename=events.json"})

    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                              headers={"Content-Disposition": "attachment; filename=events.csv"})


@router.get("/events/{event_id}", response_model=schemas.EventDetailOut)
def get_event_detail(event_id: str) -> schemas.EventDetailOut:
    row = db.get_event(event_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    decision = db.get_latest_decision(event_id)
    attempts = db.list_attempts_for_event(event_id)
    return schemas.EventDetailOut(
        **{**row, "payment_recovered": bool(row["payment_recovered"]),
           "subscription_restored": bool(row["subscription_restored"])},
        latest_action=decision["action"] if decision else None,
        latest_confidence=decision["confidence"] if decision else None,
        latest_risk_tier=decision["risk_tier"] if decision else None,
        attempts=[schemas.RecoveryAttemptOut(**a) for a in attempts],
    )


@router.get("/events/{event_id}/audit-trail", response_model=list[schemas.AuditEntryOut])
def get_event_audit_trail(event_id: str) -> list[schemas.AuditEntryOut]:
    if db.get_event(event_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    rows = db.list_audit_for_event(event_id)
    return [schemas.AuditEntryOut(**{**r, "ai_used": bool(r["ai_used"]),
                                      "fallback_triggered": bool(r["fallback_triggered"])})
            for r in rows]


@router.get("/events/{event_id}/raw-log")
def get_event_raw_log(event_id: str) -> dict:
    if db.get_event(event_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return {
        "event": db.get_event(event_id),
        "audit_log": db.list_audit_for_event(event_id),
        "decisions": db.query_all("SELECT * FROM decisions WHERE event_id=? ORDER BY id", (event_id,)),
        "recovery_attempts": db.list_attempts_for_event(event_id),
    }


@router.get("/audit-trail", response_model=list[schemas.AuditEntryOut])
def get_global_audit_trail(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=500),
) -> list[schemas.AuditEntryOut]:
    merchant_id = _merchant_id()
    offset = (page - 1) * page_size
    rows = db.list_all_audit(merchant_id, limit=page_size, offset=offset)
    return [schemas.AuditEntryOut(**{**r, "ai_used": bool(r["ai_used"]),
                                      "fallback_triggered": bool(r["fallback_triggered"])})
            for r in rows]


# ── Customers ─────────────────────────────────────────────────────────────────
@router.get("/customers", response_model=schemas.PaginatedCustomers)
def list_customers_route(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=200)) -> schemas.PaginatedCustomers:
    merchant_id = _merchant_id()
    offset = (page - 1) * page_size
    rows = db.list_customers(merchant_id, limit=page_size, offset=offset)
    total = db.count_customers(merchant_id)
    return schemas.PaginatedCustomers(items=[schemas.CustomerOut(**r) for r in rows],
                                       total=total, page=page, page_size=page_size)


@router.get("/customers/{customer_id}", response_model=schemas.CustomerOut)
def get_customer_route(customer_id: str) -> schemas.CustomerOut:
    row = db.get_customer(_merchant_id(), customer_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return schemas.CustomerOut(**row)


# ── Guardrails ────────────────────────────────────────────────────────────────
_VALID_CHANNELS = {"email", "payment_link", "sms"}


@router.get("/guardrails", response_model=schemas.GuardrailConfigOut)
def get_guardrails_route() -> schemas.GuardrailConfigOut:
    cfg = db.get_guardrail_config(_merchant_id())
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guardrail config not found")
    return schemas.GuardrailConfigOut(**cfg)


@router.put("/guardrails", response_model=schemas.GuardrailConfigOut)
def put_guardrails_route(body: schemas.GuardrailConfigIn) -> schemas.GuardrailConfigOut:
    if body.low_confidence >= body.high_confidence:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                             "low_confidence must be less than high_confidence")
    unknown = set(body.allowed_channels) - _VALID_CHANNELS
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unsupported channel(s) {sorted(unknown)} — only {sorted(_VALID_CHANNELS)} are wired up; "
            f"WhatsApp/Voice are not yet integrated and must not be toggleable as if they were.",
        )
    cfg = db.upsert_guardrail_config(_merchant_id(), body.model_dump())
    return schemas.GuardrailConfigOut(**cfg)


@router.get("/guardrails/pending-approvals", response_model=list[schemas.PendingApprovalOut])
def get_pending_approvals_route() -> list[schemas.PendingApprovalOut]:
    rows = db.list_pending_approvals(_merchant_id())
    return [schemas.PendingApprovalOut(**r) for r in rows]


# ── Strategies ────────────────────────────────────────────────────────────────
@router.get("/strategies", response_model=list[schemas.StrategyOut])
def get_strategies_route(range: int = Query(default=90, ge=1, le=365, alias="range")) -> list[schemas.StrategyOut]:
    rows = db.strategy_breakdown(_merchant_id(), _since(range))
    out = []
    for r in rows:
        rate = (r["recovered_count"] / r["attempts"]) if r["attempts"] else 0.0
        out.append(schemas.StrategyOut(
            mechanism=r["mechanism"] or "unknown", attempts=r["attempts"],
            recovered_paise=r["recovered_paise"], recovered_count=r["recovered_count"],
            success_rate=round(rate, 4),
        ))
    return out


# ── Approvals (doc §3.12: pending -> approved -> executing -> executed, ──────
#    each transition claimed atomically so double-clicks/concurrent
#    reviewers cannot trigger duplicate money-moving operations) ─────────────
@router.post("/approvals/{approval_id}/approve", response_model=schemas.ApprovalActionOut)
def approve_approval(approval_id: int, body: schemas.ApprovalActionIn = schemas.ApprovalActionIn()) -> schemas.ApprovalActionOut:
    approval = db.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")

    if not db.set_approval_status(approval_id, from_status="pending", to_status="approved",
                                   resolved_by=body.resolved_by):
        raise HTTPException(status.HTTP_409_CONFLICT,
                             "This approval was already resolved by someone else.")
    if not db.set_approval_status(approval_id, from_status="approved", to_status="executing",
                                   resolved_by=body.resolved_by):
        # Should be unreachable (we just claimed it above), but the atomic
        # claim below is the real safety net if it ever races.
        raise HTTPException(status.HTTP_409_CONFLICT, "This approval is already executing.")

    event = db.get_event(approval["event_id"])
    proposed_action = approval["proposed_action"]
    execution_mechanism = approval["execution_mechanism"]

    # Stale-decision protection (doc §3.13): if the underlying decision has
    # expired, re-analyze before acting on it rather than executing a
    # possibly-outdated proposal.
    latest_decision = db.get_latest_decision(approval["event_id"])
    if latest_decision and latest_decision.get("decision_expires_at"):
        from datetime import datetime, timezone
        expires_at = datetime.fromisoformat(latest_decision["decision_expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            from ..pipeline import pipeline as pipeline_module
            fresh = pipeline_module.reanalyze_decision(event)
            proposed_action, execution_mechanism = fresh["action"], fresh["execution_mechanism"]
            db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                              "stage": "decided", "message": "Re-analyzed stale decision before approval execution",
                              "payload": {"approval_id": approval_id, "fresh_action": proposed_action}})

    recovery_attempt_id = None
    if execution_mechanism:
        from ..enums import Action, ExecutionMechanism
        from ..services import execution_service
        customer = db.get_customer(approval["merchant_id"], event["customer_id"]) if event.get("customer_id") else None
        result = execution_service.execute_action(
            merchant_id=approval["merchant_id"], event=event,
            action=Action(proposed_action), mechanism=ExecutionMechanism(execution_mechanism),
            customer=customer,
        )
        recovery_attempt_id = result.recovery_attempt_id
        new_status = EventStatus.scheduled.value if result.status == "scheduled" else EventStatus.waiting_for_outcome.value
        db.update_event(approval["event_id"], status=new_status)
        db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                          "stage": "executed", "message": f"Approved and executed via {result.execution_mechanism}",
                          "payload": {"approval_id": approval_id, "recovery_attempt_id": recovery_attempt_id}})
    else:
        # A genuine escalate_to_human proposal — there is no automated
        # mechanism to run; approving records that a human is handling this
        # outside the system (e.g. a manual call), and closes the event.
        db.update_event(approval["event_id"], status=EventStatus.closed.value)
        db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                          "stage": "outcome", "message": "Approved for manual handling by a human",
                          "payload": {"approval_id": approval_id}})

    db.set_approval_status(approval_id, from_status="executing", to_status="executed", resolved_by=body.resolved_by)
    return schemas.ApprovalActionOut(id=approval_id, status="executed", event_id=approval["event_id"],
                                      recovery_attempt_id=recovery_attempt_id)


@router.post("/approvals/{approval_id}/deny", response_model=schemas.ApprovalActionOut)
def deny_approval(approval_id: int, body: schemas.ApprovalActionIn = schemas.ApprovalActionIn()) -> schemas.ApprovalActionOut:
    approval = db.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")

    claimed = db.set_approval_status(approval_id, from_status="pending", to_status="denied",
                                      resolved_by=body.resolved_by)
    if not claimed:
        raise HTTPException(status.HTTP_409_CONFLICT,
                             "This approval was already resolved by someone else.")

    # A genuine escalation that's denied means no further recovery will be
    # attempted (terminal `escalated`); a denied executable action is a
    # deliberate non-execution (terminal `failed`) rather than a system error.
    final_status = (EventStatus.escalated.value if not approval["execution_mechanism"]
                    else EventStatus.failed.value)
    db.update_event(approval["event_id"], status=final_status)
    db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                      "stage": "outcome", "message": f"Approval denied by {body.resolved_by}",
                      "payload": {"approval_id": approval_id, "status": final_status}})
    return schemas.ApprovalActionOut(id=approval_id, status="denied", event_id=approval["event_id"],
                                      recovery_attempt_id=approval.get("recovery_attempt_id"))


# ── Batch (demo control) ───────────────────────────────────────────────────────
@router.post("/batch/run", response_model=schemas.BatchRunOut)
def run_batch_route(body: schemas.BatchRunIn) -> schemas.BatchRunOut:
    from ..batch import batch_runner
    result = batch_runner.run_batch(
        merchant_id=_merchant_id(), n_events=body.n_events, dry_run=body.dry_run,
        use_ai=body.use_ai, random_seed=body.random_seed,
    )
    return schemas.BatchRunOut(**result)


@router.get("/batch/last-summary", response_model=Optional[schemas.BatchRunOut])
def get_last_batch_summary() -> Optional[schemas.BatchRunOut]:
    row = db.get_last_simulation(_merchant_id())
    if row is None:
        return None
    return schemas.BatchRunOut(
        simulation_run_id=row["simulation_run_id"], n_events=row["n_events"],
        use_ai=bool(row["use_ai"]), dry_run=bool(row["dry_run"]),
        baseline=row["baseline"], treatment=row["treatment"], created_at=row["created_at"],
    )
