"""Frontend-facing REST API (doc A1/A5). Single X-API-Key auth (A4)."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import db
from ..config import settings
from ..deps import require_api_key
from ..domain.cause_analysis import classify_cause
from ..enums import Cause, EventStatus, EventType
from ..logging_config import get_logger

logger = get_logger("reviveo.api")

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

_MERCHANT = settings.default_merchant_id  # single default merchant (§3.15)

_RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7),
           "30d": timedelta(days=30), "all": None}

_KNOWN_CHANNELS = {"email", "payment_link", "sms", "whatsapp"}


def _since(range_key: str, previous: bool = False) -> str:
    delta = _RANGES.get(range_key)
    if range_key not in _RANGES:
        raise HTTPException(400, f"range must be one of {sorted(_RANGES)}")
    now = datetime.now(timezone.utc)
    if delta is None:
        return "1970-01-01T00:00:00+00:00"
    base = now - (2 * delta if previous else delta)
    return base.isoformat()


# ── summary ──────────────────────────────────────────────────────────────────
@router.get("/summary")
def summary(range: str = Query("7d")):
    cur = db.summary_metrics(_MERCHANT, _since(range))
    prev = db.summary_metrics(_MERCHANT, _since(range, previous=True))

    def pct(new: float, old: float) -> Optional[float]:
        if old == 0:
            return None
        return round((new - old) / old * 100, 1)

    recovery_rate = (cur["recovered_paise"] / cur["revenue_at_risk_paise"] * 100
                     if cur["revenue_at_risk_paise"] else 0.0)
    success_rate = (cur["actions_succeeded"] / cur["actions_executed"] * 100
                    if cur["actions_executed"] else 0.0)
    return {
        "range": range,
        "revenue_at_risk_paise": cur["revenue_at_risk_paise"],
        "recovered_paise": cur["recovered_paise"],
        "recovery_rate_pct": round(recovery_rate, 1),
        "events_processed": cur["events_processed"],
        "recovered_count": cur["recovered_count"],
        "actions_executed": cur["actions_executed"],
        "action_success_rate_pct": round(success_rate, 1),
        "deltas_vs_previous": {
            "revenue_at_risk_pct": pct(cur["revenue_at_risk_paise"], prev["revenue_at_risk_paise"]),
            "recovered_paise_pct": pct(cur["recovered_paise"], prev["recovered_paise"]),
            "events_processed_pct": pct(cur["events_processed"], prev["events_processed"]),
        },
    }


@router.get("/summary/timeseries")
def timeseries(range: str = Query("7d"), granularity: str = Query("day")):
    since = _since(range)
    at_risk = db.timeseries_at_risk(_MERCHANT, since)
    recovered = db.timeseries_recovered(_MERCHANT, since)
    days = sorted({r["day"] for r in at_risk} | {r["day"] for r in recovered})
    risk_by_day = {r["day"]: r for r in at_risk}
    rec_by_day = {r["day"]: r for r in recovered}
    return [
        {"day": d,
         "at_risk_paise": risk_by_day.get(d, {}).get("amount_paise", 0),
         "recovered_paise": rec_by_day.get(d, {}).get("amount_paise", 0)}
        for d in days
    ]


@router.get("/summary/strategy-breakdown")
def strategy_breakdown(range: str = Query("7d")):
    rows = db.strategy_breakdown(_MERCHANT, _since(range))
    total = sum(r["attempts"] for r in rows) or 1
    for r in rows:
        r["share_pct"] = round(r["attempts"] / total * 100, 1)
    return rows


# ── events ───────────────────────────────────────────────────────────────────
def _decorate(ev: dict) -> dict:
    decision = db.get_latest_decision(ev["event_id"])
    ev["latest_decision"] = (
        {k: decision[k] for k in ("action", "confidence", "risk_tier", "reasoning")}
        if decision else None
    )
    ev["attempt_count"] = db.count_attempts(ev["event_id"])
    return ev


@router.get("/events")
def list_events(status: Optional[str] = None, cause: Optional[str] = None,
                page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    offset = (page - 1) * page_size
    rows = db.list_events(_MERCHANT, status=status, cause=cause,
                          limit=page_size, offset=offset)
    total = db.count_events(_MERCHANT, status=status, cause=cause)
    return {"page": page, "page_size": page_size, "total": total,
            "items": [_decorate(r) for r in rows]}


@router.get("/events/export")
def export_events(format: str = Query("csv")):
    rows = db.list_events(_MERCHANT, limit=10_000, offset=0)
    if format == "json":
        return {"items": rows}
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition":
                                      'attachment; filename="reviveo-events.csv"'})


@router.get("/events/{event_id}")
def get_event_detail(event_id: str):
    ev = db.get_event(event_id)
    if ev is None or ev["merchant_id"] != _MERCHANT:
        raise HTTPException(404, f"event '{event_id}' not found")
    payload = _decorate(ev)
    payload["decisions"] = db.query_all(
        "SELECT * FROM decisions WHERE event_id=? ORDER BY id", (event_id,))
    payload["attempts"] = db.list_attempts_for_event(event_id)
    payload["approvals"] = db.query_all(
        "SELECT id, status, proposed_action, amount_paise, reason, ai_summary, created_at "
        "FROM pending_approvals WHERE event_id=? ORDER BY id", (event_id,))
    return payload


@router.get("/events/{event_id}/audit-trail")
def event_audit_trail(event_id: str):
    ev = db.get_event(event_id)
    if ev is None or ev["merchant_id"] != _MERCHANT:
        raise HTTPException(404, f"event '{event_id}' not found")
    return {"event_id": event_id, "status": ev["status"],
            "stages": db.list_audit_for_event(event_id)}


@router.get("/events/{event_id}/raw-log")
def event_raw_log(event_id: str):
    rows = db.query_all(
        "SELECT razorpay_event_id, event_name, raw_payload, status, received_at "
        "FROM webhook_events WHERE raw_payload LIKE ? ORDER BY id",
        (f"%{event_id}%",),
    )
    return {"event_id": event_id, "webhooks": rows}


# ── customers ────────────────────────────────────────────────────────────────
@router.get("/customers")
def list_customers(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    offset = (page - 1) * page_size
    return {"page": page, "total": db.count_customers(_MERCHANT),
            "items": db.list_customers(_MERCHANT, page_size, offset)}


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: str):
    c = db.get_customer(_MERCHANT, customer_id)
    if c is None:
        raise HTTPException(404, f"customer '{customer_id}' not found")
    c["subscriptions"] = db.query_all(
        "SELECT * FROM subscriptions WHERE merchant_id=? AND customer_id=?",
        (_MERCHANT, customer_id))
    c["events"] = db.list_events(_MERCHANT, limit=50, offset=0)
    c["events"] = [e for e in c["events"] if e.get("customer_id") == customer_id]
    return c


# ── guardrails ───────────────────────────────────────────────────────────────
@router.get("/guardrails")
def get_guardrails():
    cfg = db.get_guardrail_config(_MERCHANT)
    counter = db.get_daily_counter(_MERCHANT)
    return {**cfg, "daily_counters": counter}


@router.put("/guardrails")
def put_guardrails(cfg: dict):
    """Server-side bounds validation — the frontend form is never trusted."""
    try:
        environment = cfg.get("environment", "test")
        if environment not in ("test", "production"):
            raise ValueError("environment must be test|production")
        channels = cfg.get("allowed_channels", ["email", "payment_link"])
        unknown = set(channels) - _KNOWN_CHANNELS
        if unknown:
            raise ValueError(f"unknown channels: {sorted(unknown)}")

        def bounded_int(key: str, lo: int, hi: int) -> int:
            v = int(cfg.get(key))
            if not (lo <= v <= hi):
                raise ValueError(f"{key} must be within [{lo}, {hi}]")
            return v

        def bounded_float(key: str, lo: float, hi: float) -> float:
            v = float(cfg.get(key))
            if not (lo <= v <= hi):
                raise ValueError(f"{key} must be within [{lo}, {hi}]")
            return v

        validated = {
            "environment": environment,
            "allowed_channels": list(channels),
            "recovery_window_days": bounded_int("recovery_window_days", 1, 30),
            "high_confidence": bounded_float("high_confidence", 0.5, 1.0),
            "low_confidence": bounded_float("low_confidence", 0.0, 0.9),
            "max_retries": bounded_int("max_retries", 1, 10),
            "cooldown_hours": bounded_int("cooldown_hours", 0, 168),
            "max_autonomous_recovery_amount_paise":
                bounded_int("max_autonomous_recovery_amount_paise", 100, 100_000_000),
            "daily_recovery_value_cap_paise":
                bounded_int("daily_recovery_value_cap_paise", 100, 1_000_000_000),
            "daily_contact_cap": bounded_int("daily_contact_cap", 0, 100_000),
        }
        if validated["low_confidence"] >= validated["high_confidence"]:
            raise ValueError("low_confidence must be below high_confidence")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    return db.upsert_guardrail_config(_MERCHANT, validated)


@router.get("/guardrails/pending-approvals")
def pending_approvals():
    return {"items": db.list_pending_approvals(_MERCHANT)}


# ── strategies ───────────────────────────────────────────────────────────────
@router.get("/strategies")
def strategies(range: str = Query("30d")):
    rows = db.strategy_breakdown(_MERCHANT, _since(range))
    for r in rows:
        r["success_rate_pct"] = (round(r["recovered_count"] / r["attempts"] * 100, 1)
                                 if r["attempts"] else 0.0)
    return rows


# ── approvals ────────────────────────────────────────────────────────────────
@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: int):
    from ..services import approvals as approvals_service

    try:
        result = approvals_service.approve(approval_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    if not result.get("ok") and result.get("error") == "conflict":
        raise HTTPException(409, result.get("detail", "conflict"))
    return result


@router.post("/approvals/{approval_id}/deny")
def deny(approval_id: int, body: dict | None = None):
    from ..services import approvals as approvals_service

    reason = (body or {}).get("reason", "")
    try:
        result = approvals_service.deny(approval_id, reason=reason)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    if not result.get("ok"):
        raise HTTPException(409, result.get("detail", "conflict"))
    return result


# ── global audit trail ───────────────────────────────────────────────────────
@router.get("/audit-trail")
def global_audit_trail(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    offset = (page - 1) * page_size
    items = db.list_all_audit(_MERCHANT, page_size, offset)
    return {"page": page, "items": items}


# ── demo injection (synthetic mode only) ─────────────────────────────────────
@router.post("/demo/inject-event")
def demo_inject_event(body: dict):
    if settings.is_live:
        raise HTTPException(403, "Injection disabled in live mode.")
    from ..pipeline import pipeline

    event_type = body.get("type", "payment_failed")
    if event_type not in EventType._value2member_map_:
        raise HTTPException(422, f"type must be one of {sorted(EventType._value2member_map_)}")
    error_code = body.get("error_code")
    if error_code is not None:
        classify_cause(error_code)  # raises nothing; just sanity

    customers = db.list_customers(_MERCHANT, 1, 0)
    customer_id = body.get("customer_id") or (customers[0]["id"] if customers else None)

    ev = pipeline.ingest_event({
        "merchant_id": _MERCHANT,
        "type": event_type,
        "customer_id": customer_id,
        "subscription_id": body.get("subscription_id"),
        "invoice_id": body.get("invoice_id"),
        "error_code": error_code or "card_expired",
        "amount_paise": int(body.get("amount_paise", 99900)),
        "origin": "synthetic",
    })
    result = pipeline.process_event(ev["event_id"])
    return {"ingested": ev["event_id"], "result": result}


# ── batch ────────────────────────────────────────────────────────────────────
@router.post("/batch/run")
def batch_run(body: dict):
    from ..batch.batch_runner import run_batch

    n = int(body.get("n_events", 25))
    n = max(1, min(n, 500))
    use_ai = bool(body.get("use_ai", False))
    dry_run = bool(body.get("dry_run", True))
    seed = body.get("seed")
    return run_batch(n_events=n, dry_run=dry_run, use_ai=use_ai,
                     seed=int(seed) if seed is not None else None)


@router.get("/batch/last-summary")
def batch_last_summary():
    last = db.get_last_simulation(_MERCHANT)
    if last is None:
        raise HTTPException(404, "no simulation run yet — POST /api/reports/simulate first")
    return last


@router.post("/reports/simulate")
def reports_simulate(body: dict):
    from ..batch.batch_runner import run_simulation

    n = int((body or {}).get("n_events", 200))
    seed = (body or {}).get("seed")
    return run_simulation(n_events=max(20, min(n, 1000)),
                          seed=int(seed) if seed is not None else None)


# keep linters honest about intentionally-imported enums used in docs above
_ = (Cause, EventStatus)
