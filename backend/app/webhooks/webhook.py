"""Razorpay webhook receiver (doc §3.6, A3).

Exact order, always: verify signature -> validate payload -> deduplicate by
`x-razorpay-event-id` -> persist raw payload -> process -> mark processed.
Razorpay documents HMAC-SHA256 signature verification, event-id-based
deduplication, and that delivery order is not guaranteed
(https://razorpay.com/docs/webhooks/validate-test/) — this handler is built
around those two guarantees/limitations rather than assuming either away.

Two families of events land on the same endpoint (Razorpay delivers every
subscribed event type to one configured URL):
  - inbound failure signals: payment.failed, subscription.pending, subscription.halted
  - outcome confirmations: payment_link.paid / .expired / .cancelled / .partially_paid

Note on scope: `subscription.pending`/`subscription.halted` routing is fully
implemented and will process a genuine Razorpay subscription correctly, but
this build's live demo path centers on `payment.failed` + Payment Link
outcomes (the "small live Razorpay test-mode flow" the project brief calls
for) — a full live Razorpay Subscriptions/Checkout integration is a
materially larger project and stays out of this MVP's scope; subscription
lifecycle scenarios are exercised via the synthetic batch simulator instead.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from .. import db
from ..config import settings
from ..enums import EventStatus, EventType
from ..logging_config import get_logger
from ..pipeline import attribution, pipeline
from ..services import razorpay_service

logger = get_logger("reviveo.webhook")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_INBOUND_EVENTS = {"payment.failed", "subscription.pending", "subscription.halted"}
_OUTCOME_EVENTS = {
    "payment_link.paid", "payment_link.expired",
    "payment_link.cancelled", "payment_link.partially_paid",
}


@router.post("/razorpay", status_code=status.HTTP_200_OK)
async def razorpay_webhook(request: Request) -> dict:
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")

    if not razorpay_service.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body") from exc

    event_name = payload.get("event", "")
    razorpay_event_id = request.headers.get("x-razorpay-event-id") or payload.get("id") or str(uuid.uuid4())
    merchant_id = settings.default_merchant_id  # single-merchant hackathon scope (doc §3.15)

    is_new = db.try_insert_webhook(merchant_id, razorpay_event_id, event_name, raw_body.decode("utf-8"))
    if not is_new:
        logger.info("duplicate webhook ignored", extra={"context": {
            "razorpay_event_id": razorpay_event_id, "event_name": event_name}})
        return {"status": "duplicate"}

    try:
        result = _route_event(merchant_id, event_name, payload)
        db.mark_webhook(merchant_id, razorpay_event_id, "processed")
    except Exception as exc:  # noqa: BLE001 — must record the failure, not crash the endpoint
        db.mark_webhook(merchant_id, razorpay_event_id, "failed", error=str(exc))
        logger.error("webhook processing failed", extra={"context": {
            "razorpay_event_id": razorpay_event_id, "event_name": event_name, "error": str(exc)}})
        # Still return 200 — Razorpay would otherwise retry indefinitely for
        # an error that re-processing won't fix (e.g. an unknown customer).
        # The failure is fully visible in webhook_events/status for operators.
        return {"status": "error_logged"}

    return result if result is not None else {"status": "ok"}


def _route_event(merchant_id: str, event_name: str, payload: dict) -> Optional[dict]:
    if event_name == "payment.failed":
        _handle_payment_failed(merchant_id, payload)
    elif event_name == "subscription.pending":
        _handle_subscription_state_event(merchant_id, payload, EventType.subscription_failed, "pending")
    elif event_name == "subscription.halted":
        _handle_subscription_state_event(merchant_id, payload, EventType.subscription_halted, "halted")
    elif event_name in _OUTCOME_EVENTS:
        return _handle_outcome_event(merchant_id, event_name, payload)
    else:
        logger.info("unhandled webhook event type", extra={"context": {"event_name": event_name}})
    return None


def _find_customer_by_contact(merchant_id: str, email: Optional[str], phone: Optional[str]) -> Optional[dict]:
    if email:
        row = db.query_one("SELECT * FROM customers WHERE merchant_id=? AND email=?", (merchant_id, email))
        if row:
            return row
    if phone:
        row = db.query_one("SELECT * FROM customers WHERE merchant_id=? AND phone=?", (merchant_id, phone))
        if row:
            return row
    return None


def _handle_payment_failed(merchant_id: str, payload: dict) -> None:
    # Support both real Razorpay envelope (payload.payload.payment.entity)
    # and flat synthetic payloads used by tests / `curl` demos.
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) if payload.get("payload") else {}
    flat = not entity
    if flat:
        # Flat synthetic: infer from top-level keys
        entity = {
            "email": payload.get("customer_email") or payload.get("email"),
            "contact": payload.get("customer_phone") or payload.get("contact"),
            "invoice_id": payload.get("invoice_id"),
            "error_reason": payload.get("error_code"),
            "error_code": payload.get("error_code"),
            "amount": payload.get("amount_paise", payload.get("amount", 0)),
            "id": payload.get("razorpay_payment_id") or payload.get("id"),
        }
    # `customer_id` direct field (synthetic tests) takes precedence over
    # email/phone lookup
    direct_customer_id = payload.get("customer_id")
    if direct_customer_id:
        customer = db.get_customer(merchant_id, direct_customer_id)
    else:
        customer = _find_customer_by_contact(merchant_id, entity.get("email"), entity.get("contact"))

    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:16]}",
        "merchant_id": payload.get("merchant_id", merchant_id),
        "customer_id": (customer["id"] if customer else direct_customer_id),
        "subscription_id": payload.get("subscription_id"),
        "invoice_id": entity.get("invoice_id"),
        "type": EventType.payment_failed.value,
        "error_code": entity.get("error_reason") or entity.get("error_code") or payload.get("error_code"),
        "amount_paise": entity.get("amount", 0) or payload.get("amount_paise", 0),
        "status": EventStatus.detected.value,
        "origin": "live_test_mode",
        "razorpay_payment_id": entity.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.insert_event(event)
    pipeline.process_event(db.get_event(event["event_id"]))


def _handle_subscription_state_event(
    merchant_id: str, payload: dict, event_type: EventType, new_state: str,
) -> None:
    entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    razorpay_sub_id = entity.get("id")

    # Best-effort correlation: this MVP's demo subscriptions are seeded
    # internally rather than created via a live Razorpay Subscription flow
    # (see module docstring); a merchant wiring up real subscriptions would
    # store the Razorpay subscription id on `subscriptions` at creation time
    # and look it up here the same way.
    subscription = db.query_one("SELECT * FROM subscriptions WHERE id=?", (razorpay_sub_id,))
    if subscription:
        db.update_subscription_state(subscription["id"], new_state)

    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:16]}",
        "merchant_id": merchant_id,
        "customer_id": subscription["customer_id"] if subscription else None,
        "subscription_id": subscription["id"] if subscription else razorpay_sub_id,
        "type": event_type.value,
        "error_code": None,
        "amount_paise": subscription["amount_paise"] if subscription else entity.get("amount", 0),
        "status": EventStatus.detected.value,
        "origin": "live_test_mode",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.insert_event(event)
    pipeline.process_event(db.get_event(event["event_id"]))


def _handle_outcome_event(merchant_id: str, event_name: str, payload: dict) -> dict:
    link_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = link_entity.get("notes", {}) or {}
    reference_id = link_entity.get("reference_id")

    attempt = None
    recovery_attempt_id = notes.get("recovery_attempt_id")
    if recovery_attempt_id:
        attempt = db.get_recovery_attempt(recovery_attempt_id)
    if attempt is None and reference_id:
        attempt = db.get_attempt_by_reference(reference_id)

    if attempt is None:
        logger.warning("outcome webhook could not be correlated to a recovery attempt", extra={
            "context": {"event_name": event_name, "reference_id": reference_id}})
        return {"status": "ok"}

    cfg = db.get_guardrail_config(merchant_id) or {}
    recovery_window_days = cfg.get("recovery_window_days", 7)

    if event_name == "payment_link.paid":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        result = attribution.attribute_payment(
            recovery_attempt_id=attempt["recovery_attempt_id"],
            razorpay_payment_id=payment_entity.get("id") or f"pay_{uuid.uuid4().hex[:10]}",
            amount_paise=payment_entity.get("amount", attempt["amount_paise"]),
            recovery_window_days=recovery_window_days,
        )
        db.insert_audit({
            "event_id": attempt["event_id"], "merchant_id": merchant_id, "stage": "outcome",
            "message": result.reason, "payload": {"event_name": event_name, "accepted": result.accepted},
        })
        # Enriched response (doc: outcome webhooks "close the loop to a real
        # recovered-revenue number") — `paid` reflects whether the payment
        # was actually counted as recovered revenue (within window + amount
        # satisfied), not merely that a `payment_link.paid` event arrived.
        return {"status": "outcome_applied", "paid": result.accepted}
    elif event_name in ("payment_link.expired", "payment_link.cancelled"):
        attribution.mark_attempt_failed(attempt["recovery_attempt_id"], event_name)
        db.update_event(attempt["event_id"], status=EventStatus.expired.value)
        db.insert_audit({
            "event_id": attempt["event_id"], "merchant_id": merchant_id, "stage": "outcome",
            "message": f"Payment link outcome: {event_name}", "payload": {"event_name": event_name},
        })
        return {"status": "outcome_applied", "paid": False}
    elif event_name == "payment_link.partially_paid":
        # Explicitly not counted as a full recovery (doc §3.1 amount rule) —
        # recorded for visibility without touching the headline metric.
        db.insert_audit({
            "event_id": attempt["event_id"], "merchant_id": merchant_id, "stage": "outcome",
            "message": "Partial payment received — not counted as a full recovery",
            "payload": {"event_name": event_name},
        })
        return {"status": "outcome_applied", "paid": False}
    return {"status": "ok"}
