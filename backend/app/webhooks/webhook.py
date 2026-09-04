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
from ..enums import TERMINAL_STATUSES, EventStatus, EventType
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
    """Legacy lookup-first helper kept for compatibility — resolution order
    A (email) then B (phone), normalized. Prefer `db.resolve_webhook_customer`
    for webhook ingest (adds Razorpay-id mapping + minimal-record creation)."""
    if db.normalize_email(email):
        row = db.get_customer_by_email(merchant_id, db.normalize_email(email))  # type: ignore[arg-type]
        if row:
            return row
    if db.normalize_phone(phone):
        row = db.get_customer_by_phone(merchant_id, db.normalize_phone(phone))  # type: ignore[arg-type]
        if row:
            return row
    return None


def _linked_recovery_customer(merchant_id: str, *note_sets: dict) -> Optional[str]:
    """CASE B correlation: return the Reviveo customer id when `notes` carry
    our own link correlation keys, else None. The referenced attempt/event
    must exist AND belong to this merchant — anything else is ignored, so a
    forged or stale reference can never hijack another customer's identity.
    """
    for notes in note_sets:
        if not isinstance(notes, dict):
            continue
        attempt_id = notes.get("recovery_attempt_id")
        if isinstance(attempt_id, str) and attempt_id:
            attempt = db.get_recovery_attempt(attempt_id)
            if attempt is not None and attempt.get("merchant_id") == merchant_id:
                event = db.get_event(attempt["event_id"])
                if event is not None and event.get("customer_id"):
                    return event["customer_id"]
        event_id = notes.get("event_id")
        if isinstance(event_id, str) and event_id:
            event = db.get_event(event_id)
            if (event is not None and event.get("merchant_id") == merchant_id
                    and event.get("customer_id")):
                return event["customer_id"]
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
            "customer_id": payload.get("razorpay_customer_id"),
            "invoice_id": payload.get("invoice_id"),
            "error_reason": payload.get("error_code"),
            "error_code": payload.get("error_code"),
            "amount": payload.get("amount_paise", payload.get("amount", 0)),
            "id": payload.get("razorpay_payment_id") or payload.get("id"),
        }
    # The webhook is a snapshot. If its email is absent or a known Razorpay
    # placeholder, ask Razorpay for the payment record before resolving the
    # customer. A failed fetch simply leaves the normal payload path intact.
    payment_id = entity.get("id")
    if payment_id and db.trusted_email(entity.get("email")) is None:
        fetched_payment = razorpay_service.fetch_razorpay_payment(payment_id)
        if fetched_payment:
            for field in ("email", "contact", "customer_id", "name"):
                if fetched_payment.get(field):
                    entity[field] = fetched_payment[field]
    # `customer_id` direct field (synthetic tests) takes precedence over
    # email/phone lookup
    direct_customer_id = payload.get("customer_id")
    if direct_customer_id:
        customer = db.get_customer(merchant_id, direct_customer_id)
        if customer:
            # Even a directly-addressed record must never carry a placeholder
            # into the pipeline: re-resolve its contact through the trust
            # layer (repairs rows previously poisoned with dummy addresses).
            customer = db.resolve_webhook_customer(
                merchant_id,
                # A supplied Reviveo customer id identifies the row, but the
                # Razorpay payment entity is still authoritative for the
                # payer contact captured on this transaction.
                email=entity.get("email") or customer.get("email"),
                phone=entity.get("contact") or customer.get("phone"),
                razorpay_customer_id=customer.get("razorpay_customer_id"),
                name=customer.get("name"),
            ) or customer
    else:
        # Real Razorpay payment entities carry `email`, `contact` (phone)
        # and `customer_id` (Razorpay `cust_…`) at the entity top level.
        # Higher-trust contact can also ride along in payload objects that
        # outrank the raw entity contact (Flow B: the payer typed their real
        # address on a payment-link/order checkout while the entity itself
        # carries a test-mode dummy like void@razorpay.com):
        #   payload.payment_link.entity.customer.{email,contact}
        #   payload.order.entity.notes.{email,contact}
        #   entity.notes.{email,contact,phone}
        # Plus SOURCE 6 below: one guarded Razorpay Customer API fetch, only
        # when the entity carries a cust_… id with no local mapping (miss-only,
        # failure-proof, still trust-validated before use).
        inner = payload.get("payload", {}) if isinstance(payload.get("payload"), dict) else {}
        link_customer = (inner.get("payment_link", {}) or {}).get("entity", {}).get("customer", {}) or {}
        link_notes = (inner.get("payment_link", {}) or {}).get("entity", {}).get("notes", {}) or {}
        if not isinstance(link_notes, dict):
            link_notes = {}
        order_notes = (inner.get("order", {}) or {}).get("entity", {}).get("notes", {}) or {}
        if not isinstance(order_notes, dict):
            order_notes = {}
        notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
        extra_contacts = [
            ("payment_link",
             link_customer.get("email") or link_notes.get("email"),
             link_customer.get("contact") or link_notes.get("contact") or link_notes.get("phone")),
            ("order",
             order_notes.get("email"), order_notes.get("contact") or order_notes.get("phone")),
            ("notes",
             notes.get("email"), notes.get("contact") or notes.get("phone")),
        ]
        # CASE B — failed recovery payment: entity.notes inherits Reviveo's
        # own link notes (event_id / recovery_attempt_id / source=reviveo).
        # When they point at a real attempt/event, that recovery customer is
        # authoritative — never mint a new customer from the entity contact.
        linked_customer_id = _linked_recovery_customer(merchant_id, notes, link_notes, order_notes)
        # SOURCE 6 — authoritative Razorpay customer record, fetched only on
        # local-mapping miss (no unnecessary API calls) and never trusted
        # blindly: the returned contact still passes trusted_email/normalize
        # validation inside the resolver, and any fetch failure degrades to
        # payload-local resolution.
        rzp_customer_id = entity.get("customer_id")
        if (rzp_customer_id and linked_customer_id is None
                and db.get_customer_by_razorpay_id(merchant_id, rzp_customer_id) is None):
            api_contact = razorpay_service.fetch_razorpay_customer(rzp_customer_id)
            if api_contact:
                extra_contacts.append(
                    ("razorpay_customer", api_contact.get("email"),
                     api_contact.get("contact")))
                if not notes.get("name") and api_contact.get("name"):
                    notes = {**notes, "name": api_contact.get("name")}
        customer = db.resolve_webhook_customer(
            merchant_id,
            email=(entity.get("email")),
            phone=(entity.get("contact")),
            razorpay_customer_id=rzp_customer_id,
            name=entity.get("name") or notes.get("name") or link_notes.get("name"),
            extra_contacts=extra_contacts,
            linked_customer_id=linked_customer_id,
        )

    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:16]}",
        # Server-side scoping only (doc §3.15) — never trust a caller-supplied
        # merchant_id from the request body.
        "merchant_id": merchant_id,
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
    if event["customer_id"]:
        db.incr_customer_failed_count(merchant_id, event["customer_id"])
    resolved = db.get_customer(merchant_id, event["customer_id"]) if event["customer_id"] else None
    logger.info("payment.failed customer resolution", extra={"context": {
        "event_id": event["event_id"],
        "customer_id": event["customer_id"],
        "has_trusted_email": bool(resolved and db.trusted_email(resolved.get("email"))),
        "recipient_domain": db._domain_of(resolved.get("email")) if resolved else "unknown",
    }})
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
    previous_state = subscription["state"] if subscription else None
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
        # Record the lifecycle transition on the event itself (doc §3.16:
        # subscription_state_before / subscription_state_after).
        "subscription_state_before": previous_state,
        "subscription_state_after": new_state,
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

    # Out-of-order protection (doc §3.5/§3.6): a late expiry/cancellation for a
    # link whose sibling attempt already recovered the event must never regress
    # a terminal state. Only `recovered` events keep their status here.
    current_status = (db.get_event(attempt["event_id"]) or {}).get("status")
    if (event_name in ("payment_link.expired", "payment_link.cancelled", "payment_link.partially_paid")
            and current_status in (s.value for s in TERMINAL_STATUSES)):
        logger.info("ignoring late outcome webhook for already-terminal event", extra={
            "context": {"event_name": event_name, "event_id": attempt["event_id"],
                         "current_status": current_status}})
        return {"status": "ignored_terminal"}

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
