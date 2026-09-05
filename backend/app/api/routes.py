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
from ..enums import EventStatus, TERMINAL_STATUSES
from . import schemas

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(require_api_key)])


def _merchant_id() -> str:
    # Single-merchant hackathon scope (doc §3.15); every query is still
    # merchant-scoped so this is the only place that would change to add
    # real multi-tenant auth.
    return settings.default_merchant_id


def _since(range_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=range_days)).isoformat()


def _parse_range(value: str | int) -> int:
    """Accepts 30, "30", "30d", "24h", "7d" — tests and frontend both vary."""
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    # Strip trailing unit letters (d/h/m) and parse leading int
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            break
    try:
        n = int(num) if num else int(s)
    except ValueError:
        n = 30
    # Clamp to valid range 1..365; interpret hours as days ceiling
    if s.endswith("h"):
        n = max(1, (n + 23) // 24)
    return max(1, min(365, n))


# ── Summary / dashboard ───────────────────────────────────────────────────────
_ORIGIN_PATTERN = "^(synthetic|live_test_mode)$"


@router.get("/summary", response_model=schemas.SummaryOut)
def get_summary(
    range: str = Query(default="30", alias="range"),
    origin: Optional[str] = Query(default=None, pattern=_ORIGIN_PATTERN),
) -> schemas.SummaryOut:
    range_days = _parse_range(range)
    merchant_id = _merchant_id()
    since = _since(range_days)
    m = db.summary_metrics(merchant_id, since, origin=origin)
    recovery_rate = (m["recovered_count"] / m["events_processed"]) if m["events_processed"] else 0.0

    # Period-over-period comparison vs. the immediately preceding window of
    # equal length (doc A1 "deltas_vs_previous"). None when the prior period
    # had no baseline to compare against (e.g. a brand-new merchant).
    prev_since = _since(2 * range_days)
    prev = db.summary_metrics(merchant_id, prev_since, until=since, origin=origin)
    prev_rate = (prev["recovered_count"] / prev["events_processed"]) if prev["events_processed"] else 0.0

    def pct_change(curr: int, prior: int) -> Optional[float]:
        if not prior:
            return None
        return round(((curr - prior) / prior) * 100, 1)

    return schemas.SummaryOut(
        range_days=range_days, recovery_rate=round(recovery_rate, 4), **m,
        delta_revenue_at_risk_pct=pct_change(m["revenue_at_risk_paise"], prev["revenue_at_risk_paise"]),
        delta_recovered_pct=pct_change(m["recovered_paise"], prev["recovered_paise"]),
        delta_recovery_rate_pct=(
            round((recovery_rate - prev_rate) * 100, 1) if prev["events_processed"] else None
        ),
    )


@router.get("/summary/timeseries", response_model=list[schemas.TimeseriesPoint])
def get_timeseries(
    range: str = Query(default="30", alias="range"),
    metric: str = Query(default="recovered", pattern="^(recovered|at_risk)$"),
    origin: Optional[str] = Query(default=None, pattern=_ORIGIN_PATTERN),
) -> list[schemas.TimeseriesPoint]:
    range_days = _parse_range(range)
    merchant_id = _merchant_id()
    since = _since(range_days)
    rows = (db.timeseries_recovered if metric == "recovered" else db.timeseries_at_risk)(
        merchant_id, since, origin=origin)
    return [schemas.TimeseriesPoint(**r) for r in rows]


@router.get("/summary/strategy-breakdown", response_model=list[schemas.StrategyBreakdownRow])
def get_strategy_breakdown(range: str = Query(default="30", alias="range")) -> list[schemas.StrategyBreakdownRow]:
    range_days = _parse_range(range)
    merchant_id = _merchant_id()
    rows = db.strategy_breakdown(merchant_id, _since(range_days))
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
    origin: Optional[str] = Query(default=None, pattern=_ORIGIN_PATTERN),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> schemas.PaginatedEvents:
    merchant_id = _merchant_id()
    offset = (page - 1) * page_size
    rows = db.list_events(merchant_id, status=status_filter, cause=cause, origin=origin,
                          limit=page_size, offset=offset)
    total = db.count_events(merchant_id, status=status_filter, cause=cause, origin=origin)
    return schemas.PaginatedEvents(items=[_event_to_out(r) for r in rows], total=total,
                                    page=page, page_size=page_size)


_MAX_EXPORT = 50_000


@router.get("/events/export")
def export_events(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    cause: Optional[str] = Query(default=None),
    limit: int = Query(default=10_000, ge=1, le=_MAX_EXPORT),
) -> StreamingResponse:
    merchant_id = _merchant_id()
    rows = db.list_events(merchant_id, status=status_filter, cause=cause, limit=limit, offset=0)
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
    decisions = db.list_decisions_for_event(event_id)
    notifications = db.list_notifications_for_event(event_id)
    return schemas.EventDetailOut(
        **{**row, "payment_recovered": bool(row["payment_recovered"]),
           "subscription_restored": bool(row["subscription_restored"])},
        latest_action=decision["action"] if decision else None,
        latest_confidence=decision["confidence"] if decision else None,
        latest_risk_tier=decision["risk_tier"] if decision else None,
        attempts=[schemas.RecoveryAttemptOut(**a) for a in attempts],
        decisions=[schemas.DecisionOut(**{**d, "requires_approval": bool(d["requires_approval"]),
                                           "ai_used": bool(d["ai_used"])}) for d in decisions],
        notifications=[schemas.NotificationOut(**{**n, "ai_generated": bool(n["ai_generated"])}) for n in notifications],
    )


@router.get("/events/{event_id}/audit-trail", response_model=schemas.AuditTrailOut)
def get_event_audit_trail(event_id: str) -> schemas.AuditTrailOut:
    if db.get_event(event_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    rows = db.list_audit_for_event(event_id)
    stages = [schemas.AuditEntryOut(**{**r, "ai_used": bool(r["ai_used"]),
                                        "fallback_triggered": bool(r["fallback_triggered"])})
              for r in rows]
    return schemas.AuditTrailOut(event_id=event_id, stages=stages)


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


@router.get("/audit-trail", response_model=schemas.PaginatedAudit)
def get_global_audit_trail(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=500),
) -> schemas.PaginatedAudit:
    merchant_id = _merchant_id()
    offset = (page - 1) * page_size
    rows = db.list_all_audit(merchant_id, limit=page_size, offset=offset)
    total = db.count_all_audit(merchant_id)
    items = [schemas.AuditEntryOut(**{**r, "ai_used": bool(r["ai_used"]),
                                       "fallback_triggered": bool(r["fallback_triggered"])})
             for r in rows]
    return schemas.PaginatedAudit(items=items, total=total, page=page, page_size=page_size)


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


@router.put("/customers/{customer_id}", response_model=schemas.CustomerOut)
def update_customer_route(customer_id: str, body: schemas.CustomerUpdateIn) -> schemas.CustomerOut:
    """Attach/correct a customer's contact details (merchant-authoritative —
    the single most trusted source, outranking any webhook field). Used to
    supply a real email the payment webhooks never carried, after which
    POST /events/{id}/notifications/retry can deliver the pending message.
    """
    merchant_id = _merchant_id()
    if db.get_customer(merchant_id, customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    updates: dict[str, str] = {}
    if body.name is not None and body.name.strip():
        updates["name"] = body.name.strip()
    if body.email is not None and body.email.strip():
        trusted = db.trusted_email(body.email)
        if trusted is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "email must be valid and not a known test placeholder")
        updates["email"] = trusted
    if body.phone is not None and body.phone.strip():
        phone = db.normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "phone must be a plausible dialable number")
        updates["phone"] = phone
    if not updates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "provide at least one of name, email, phone")
    row = db.update_customer(merchant_id, customer_id, **updates)
    assert row is not None  # existence checked above
    return schemas.CustomerOut(**row)


@router.post("/events/{event_id}/notifications/retry",
             response_model=schemas.NotificationOut)
def retry_event_notification(event_id: str) -> schemas.NotificationOut:
    """Explicit merchant retry of a NON-delivered notification (skipped or
    failed only). Replaces that row and re-dispatches against the customer's
    current stored contact — the path to deliver after attaching a real
    email via PUT /customers/{id}. Delivered rows (sent/simulated) return
    409: idempotency is never bypassed, nothing is ever double-sent.
    """
    from ..services import notification_service

    merchant_id = _merchant_id()
    event = db.get_event(event_id)
    if event is None or event.get("merchant_id") != merchant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if event.get("status") == EventStatus.recovered.value:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Event already recovered — no recovery message to send")

    attempts = db.list_attempts_for_event(event_id)
    if not attempts:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "No recovery attempt yet — nothing to notify about")
    attempt = attempts[-1]
    if attempt.get("status") != "awaiting_outcome":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Latest attempt is '{attempt.get('status')}' — "
                            "retry is only available once a recovery link is awaiting outcome")

    existing = db.get_notification_by_attempt(attempt["recovery_attempt_id"])
    if existing is not None and existing.get("status") in ("sent", "simulated"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Notification already '{existing.get('status')}' — refusing duplicate send")
    if existing is not None:
        db.delete_notification(attempt["recovery_attempt_id"])

    customer = (db.get_customer(merchant_id, event["customer_id"])
                if event.get("customer_id") else None)
    result = notification_service.send_customer_notification(
        merchant_id=merchant_id, event=event,
        recovery_attempt=db.get_recovery_attempt(attempt["recovery_attempt_id"]),
        customer=customer,
        short_url=attempt.get("short_url"),
    )
    row = db.get_notification_by_attempt(attempt["recovery_attempt_id"])
    assert row is not None
    return schemas.NotificationOut(**{**row, "ai_generated": bool(row["ai_generated"])})


# ── Guardrails ────────────────────────────────────────────────────────────────
_VALID_CHANNELS = {"email", "payment_link", "sms"}


def _with_effective_max_retries(cfg: dict) -> schemas.GuardrailConfigOut:
    return schemas.GuardrailConfigOut(
        **cfg, effective_max_retries=min(cfg["max_retries"], settings.max_recovery_attempts),
    )


@router.get("/guardrails", response_model=schemas.GuardrailConfigOut)
def get_guardrails_route() -> schemas.GuardrailConfigOut:
    cfg = db.get_guardrail_config(_merchant_id())
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guardrail config not found")
    return _with_effective_max_retries(cfg)


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
    return _with_effective_max_retries(cfg)


@router.get("/guardrails/pending-approvals", response_model=schemas.PaginatedPendingApprovals)
def get_pending_approvals_route() -> schemas.PaginatedPendingApprovals:
    rows = db.list_pending_approvals(_merchant_id())
    items = [schemas.PendingApprovalOut(**r) for r in rows]
    return schemas.PaginatedPendingApprovals(items=items, total=len(items))


# ── Strategies ────────────────────────────────────────────────────────────────
@router.get("/strategies", response_model=list[schemas.StrategyOut])
def get_strategies_route(range: str = Query(default="90", alias="range")) -> list[schemas.StrategyOut]:
    range_days = _parse_range(range)
    rows = db.strategy_breakdown(_merchant_id(), _since(range_days))
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

    # Out-of-order protection (doc §3.6): the event may have reached a
    # terminal state through another path (outcome webhook, expiry sweep)
    # while this approval sat in the queue — executing now would regress it.
    if event is None:
        db.set_approval_status(approval_id, from_status="executing", to_status="execution_failed",
                                resolved_by=body.resolved_by)
        raise HTTPException(status.HTTP_409_CONFLICT,
                             f"Event for this approval no longer exists.")
    if event["status"] in ("recovered", "expired", "escalated", "closed", "failed"):
        db.set_approval_status(approval_id, from_status="executing", to_status="execution_failed",
                                resolved_by=body.resolved_by)
        db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                          "stage": "outcome",
                          "message": f"Approval discarded — event already {event['status']}",
                          "payload": {"approval_id": approval_id}})
        return schemas.ApprovalActionOut(id=approval_id, status="execution_failed",
                                          event_id=approval["event_id"], ok=False)

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
    short_url = None
    if execution_mechanism:
        try:
            from ..enums import Action, ExecutionMechanism
            from ..services import execution_service
            customer = db.get_customer(approval["merchant_id"], event["customer_id"]) if event.get("customer_id") else None
            result = execution_service.execute_action(
                merchant_id=approval["merchant_id"], event=event,
                action=Action(proposed_action), mechanism=ExecutionMechanism(execution_mechanism),
                customer=customer,
            )
        except Exception as exc:  # noqa: BLE001 — a raised error must not leave the
            # approval stuck in 'executing' with the event frozen mid-transition;
            # mark execution_failed so the failure is visible and retryable.
            db.set_approval_status(approval_id, from_status="executing",
                                    to_status="execution_failed", resolved_by=body.resolved_by)
            db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                              "stage": "executed",
                              "message": f"Approval execution raised an error: {exc}",
                              "payload": {"approval_id": approval_id, "error": str(exc)}})
            return schemas.ApprovalActionOut(id=approval_id, status="execution_failed",
                                              event_id=approval["event_id"], ok=False)
        recovery_attempt_id = result.recovery_attempt_id
        short_url = result.short_url
        new_status = EventStatus.scheduled.value if result.status == "scheduled" else EventStatus.waiting_for_outcome.value
        db.update_event(approval["event_id"], status=new_status)
        db.insert_audit({"event_id": approval["event_id"], "merchant_id": approval["merchant_id"],
                          "stage": "executed", "message": f"Approved and executed via {result.execution_mechanism}",
                          "payload": {"approval_id": approval_id, "recovery_attempt_id": recovery_attempt_id,
                                      "short_url": short_url}})
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
                                      recovery_attempt_id=recovery_attempt_id, short_url=short_url)


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


# ── Demo (single-event injection, synthetic mode only) ──────────────────────
@router.post("/demo/inject-event", response_model=schemas.DemoInjectOut)
def inject_demo_event(body: schemas.DemoInjectIn) -> schemas.DemoInjectOut:
    """Injects one synthetic event straight through the real pipeline — the
    manual, single-event alternative to the batch runner, documented in
    status.md's quick-start (`POST /api/demo/inject-event`). Disabled in
    live mode: live events must come from real Razorpay webhooks only,
    never a synthetic side door (doc §3.14 origin separation).
    """
    if settings.is_live:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Demo event injection is disabled in live mode; live events must come from "
            "real Razorpay webhooks, not a synthetic side door.",
        )
    merchant_id = _merchant_id()
    amount_paise = body.amount_paise
    if amount_paise is None:
        subscription = db.get_subscription(body.subscription_id) if body.subscription_id else None
        if subscription is None and body.customer_id:
            subscription = db.get_subscription(f"sub_{body.customer_id}")
        amount_paise = subscription["amount_paise"] if subscription else 99_900

    event_id = f"evt_demo_{uuid.uuid4().hex[:16]}"
    event = {
        "event_id": event_id, "merchant_id": merchant_id,
        "customer_id": body.customer_id, "subscription_id": body.subscription_id,
        "invoice_id": None, "type": body.type, "error_code": body.error_code,
        "amount_paise": amount_paise, "status": EventStatus.detected.value,
        "origin": "synthetic", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.insert_event(event)

    from ..pipeline import pipeline as pipeline_module
    result = pipeline_module.process_event(db.get_event(event_id))
    return schemas.DemoInjectOut(ingested=event_id, result=result)


# ── Batch (demo control) ───────────────────────────────────────────────────────
@router.post("/batch/run", response_model=schemas.BatchRunOut)
def run_batch_route(body: schemas.BatchRunIn) -> schemas.BatchRunOut:
    from ..batch import batch_runner
    result = batch_runner.run_batch(
        merchant_id=_merchant_id(), n_events=body.n_events, dry_run=body.dry_run,
        use_ai=body.use_ai, random_seed=body.random_seed,
    )
    return schemas.BatchRunOut(**result)


# ── Reports (alias of /batch/run using status.md's quick-start field names) ──
@router.post("/reports/simulate", response_model=schemas.BatchRunOut)
def simulate_report_route(body: schemas.ReportSimulateIn) -> schemas.BatchRunOut:
    """Same simulation as POST /api/batch/run, under the endpoint name and
    field names (`n_events`/`seed`) documented in status.md's quick-start.
    Always a free, deterministic dry-run — never live Razorpay calls.
    """
    from ..batch import batch_runner
    result = batch_runner.run_batch(
        merchant_id=_merchant_id(), n_events=body.n_events, dry_run=True,
        use_ai=False, random_seed=body.seed,
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
