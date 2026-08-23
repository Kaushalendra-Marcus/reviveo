"""Razorpay webhook receiver (doc §3.6 order, A3 outcome webhooks).

Exact order: verify signature → validate payload → deduplicate by
x-razorpay-event-id → persist raw payload → process → mark processed.
Out-of-order/outcome events are resolved by state precedence in the state
machine; duplicates are idempotent at both the envelope and payment-id level.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import db
from ..config import settings
from ..enums import EventType
from ..logging_config import get_logger
from ..pipeline import attribution
from ..pipeline import pipeline
from ..services import razorpay_service

logger = get_logger("reviveo.webhooks")

router = APIRouter()

# Outcome events that resolve an existing recovery attempt (doc A3).
_OUTCOME_PAID = {"payment_link.paid"}
_OUTCOME_FAILED = {"payment_link.expired", "payment_link.cancelled"}

# Inbound failure events → internal EventType vocabulary. Razorpay's real
# names are covered; the synthetic generator emits these same values.
_INBOUND_MAP: dict[str, EventType] = {
    "payment.failed": EventType.payment_failed,
    "subscription.failed": EventType.subscription_failed,
    "subscription.charged": EventType.subscription_failed,  # failed charge cycle
    "subscription.halted": EventType.subscription_halted,
    "checkout.abandoned": EventType.abandoned_checkout,
}


def _extract(payload: dict) -> dict:
    """Pull a normalized shape out of either a Razorpay envelope or our
    synthetic generator's flat payload."""
    inner = payload.get("payload") or {}
    entity = {}
    for group in inner.values():
        if isinstance(group, dict) and isinstance(group.get("entity"), dict):
            entity = group["entity"]
            break
    return {
        "razorpay_event_id": payload.get("id")
        or payload.get("event_id")
        or f"whsyn_{uuid.uuid4().hex[:12]}",
        "event_name": payload.get("event") or payload.get("type") or "",
        "merchant_id": payload.get("merchant_id"),
        "customer_id": payload.get("customer_id") or entity.get("customer_id"),
        "subscription_id": payload.get("subscription_id") or entity.get("subscription_id"),
        "invoice_id": payload.get("invoice_id") or entity.get("invoice_id"),
        "error_code": payload.get("error_code")
        or ((entity.get("error_reason") or entity.get("error_code"))
            if isinstance(entity, dict) else None),
        "amount_paise": payload.get("amount_paise") or entity.get("amount"),
        "reference_id": payload.get("reference_id") or entity.get("reference_id"),
        "payment_id": payload.get("razorpay_payment_id") or entity.get("id"),
        "occurred_at": entity.get("paid_at") and str(entity["paid_at"]),
    }


def route_payload(payload: dict) -> dict:
    x = _extract(payload)
    name = x["event_name"]

    if name in _OUTCOME_PAID or name in _OUTCOME_FAILED:
        attempt = db.get_attempt_by_reference(x["reference_id"] or "")
        if attempt is None:
            return {"status": "ignored", "reason": "no matching recovery attempt"}
        event = db.get_event(attempt["event_id"])
        paid = name in _OUTCOME_PAID
        attribution.apply_outcome(
            event, attempt,
            paid=paid,
            razorpay_payment_id=x["payment_id"],
            amount_paise=x["amount_paise"] or attempt["amount_paise"],
        )
        return {"status": "outcome_applied", "paid": paid}

    event_type = _INBOUND_MAP.get(name) or (
        EventType(name) if name in EventType._value2member_map_ else None
    )
    if event_type is None:
        return {"status": "ignored", "reason": f"unhandled event '{name}'"}

    ev = pipeline.ingest_event({
        "merchant_id": x["merchant_id"],
        "type": event_type.value,
        "customer_id": x["customer_id"],
        "subscription_id": x["subscription_id"],
        "invoice_id": x["invoice_id"],
        "error_code": x["error_code"],
        "amount_paise": x["amount_paise"] or 0,
        "origin": "live_test_mode",
        "razorpay_payment_id": x["payment_id"],
    })
    summary = pipeline.process_event(ev["event_id"])
    return {"status": "processed", "event_id": ev["event_id"], **summary}


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    # validate payload first (we need the event id to persist/dedup)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse({"status": "rejected", "reason": "invalid JSON"}, status_code=400)

    x = _extract(payload)

    # deduplicate + persist raw payload atomically (§3.6)
    merchant_id = x["merchant_id"] or settings.default_merchant_id
    fresh = db.try_insert_webhook(merchant_id, x["razorpay_event_id"],
                                  x["event_name"], body.decode(errors="replace"))

    if not fresh:
        return {"status": "duplicate"}

    # verify signature only once we know this is a fresh envelope
    if not razorpay_service.verify_webhook_signature(body, signature):
        db.mark_webhook(merchant_id, x["razorpay_event_id"], "failed",
                        "signature verification failed")
        return JSONResponse({"status": "rejected", "reason": "bad signature"}, status_code=400)

    try:
        result = route_payload(payload)
        db.mark_webhook(merchant_id, x["razorpay_event_id"], "processed")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("webhook processing failed: %s", exc)
        db.mark_webhook(merchant_id, x["razorpay_event_id"], "failed", str(exc))
        # 200 keeps Razorpay from retry-storming during demos; the failure is
        # persisted and visible in webhook_events.
        return {"status": "error", "detail": str(exc)}
