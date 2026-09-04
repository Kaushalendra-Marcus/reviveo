"""Execution service (doc A0 `execution.py`) — turns an approved or
auto-executable decision into a real `recovery_attempts` row. This is the
ONLY module that writes `recovery_attempts` and calls `razorpay_service`;
the deterministic pipeline, the agent's tools, and the approval-execution
endpoint all go through this single function, so there is exactly one code
path for "an action actually happened" (doc §0 — same function, same code
path, keeps the audit story simple).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..config import settings
from ..enums import Action, ExecutionMechanism, ExecutionMode
from ..logging_config import get_logger
from . import razorpay_service

logger = get_logger("reviveo.execution_service")

_CONTACT_ACTIONS = {
    Action.send_reminder, Action.retry_and_notify, Action.send_payment_update_link,
    Action.smart_retry_24h, Action.immediate_retry,
}

@dataclass(frozen=True)
class ExecutionResult:
    recovery_attempt_id: str
    status: str  # 'awaiting_outcome' | 'scheduled' | 'failed'
    execution_mechanism: str
    execution_mode: str
    razorpay_ref: Optional[str]
    short_url: Optional[str]
    scheduled_for: Optional[str]
    error: Optional[str] = None  # set iff status == 'failed'


def execute_action(
    *,
    merchant_id: str,
    event: dict,
    action: Action,
    mechanism: ExecutionMechanism,
    customer: Optional[dict],
    immediate: bool = False,
) -> ExecutionResult:
    """Executes (or schedules) the given action. Always creates exactly one
    new `recovery_attempts` row — `UNIQUE(event_id, attempt_number)` in the
    schema makes double-execution structurally impossible even under retry.

    `immediate=True` is used by the scheduler once a previously-scheduled
    action's time has actually arrived (doc §3.11) — it forces real
    execution instead of scheduling again, which would otherwise loop
    `smart_retry_24h` forever without ever creating a Payment Link.
    """
    event_id = event["event_id"]
    attempt_number = db.next_attempt_number(event_id)
    recovery_attempt_id = f"ra_{uuid.uuid4().hex[:16]}"
    execution_mode = (
        ExecutionMode.live_call.value
        if (settings.is_live and settings.razorpay_configured)
        else ExecutionMode.dry_run.value
    )

    scheduled_for: Optional[str] = None
    razorpay_ref: Optional[str] = None
    short_url: Optional[str] = None
    error_message: Optional[str] = None
    status = "awaiting_outcome"

    if action == Action.smart_retry_24h and not immediate:
        scheduled_for = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        status = "scheduled"
    elif mechanism == ExecutionMechanism.native_subscription_retry:
        status = "awaiting_outcome"  # nothing to call — Razorpay is already retrying natively
    elif mechanism == ExecutionMechanism.reminder_only:
        status = "awaiting_outcome"  # message-only; outcome still tracked via a later payment webhook
    else:
        # Every remaining mechanism (payment_link, checkout, manual_charge,
        # new_recovery_payment, scheduled_recovery_payment, and a now-due
        # smart_retry_24h) collects money via a fresh Payment Link in this
        # MVP; the internal mechanism label recorded on the attempt always
        # stays the real, specific one (doc §3.4).
        result = razorpay_service.create_payment_link(
            amount_paise=event["amount_paise"],
            customer_name=(customer or {}).get("name", "Customer"),
            customer_email=(customer or {}).get("email"),
            customer_phone=(customer or {}).get("phone"),
            description=f"Reviveo recovery — {mechanism.value} (attempt {attempt_number})",
            event_id=event_id, recovery_attempt_id=recovery_attempt_id,
            attempt_number=attempt_number,
        )
        razorpay_ref = result.razorpay_ref
        short_url = result.short_url
        if not result.ok:
            # A live Razorpay call failed (network/API error) — record a real
            # failed attempt rather than pretending it's awaiting an outcome
            # that will never arrive (production-readiness fix, 2026-08-24 audit).
            status = "failed"
            error_message = result.error
            logger.warning("execution failed at payment provider", extra={"context": {
                "event_id": event_id, "recovery_attempt_id": recovery_attempt_id,
                "mechanism": mechanism.value, "error": error_message,
            }})

    db.insert_recovery_attempt({
        "recovery_attempt_id": recovery_attempt_id,
        "event_id": event_id,
        "merchant_id": merchant_id,
        "attempt_number": attempt_number,
        "action": action.value,
        "execution_mechanism": mechanism.value,
        "amount_paise": event["amount_paise"],
        "status": status,
        "execution_mode": execution_mode,
        "razorpay_ref": razorpay_ref,
        "reference_id": f"rvo_{recovery_attempt_id}"[:40],
        "notes": {
            "event_id": event_id, "recovery_attempt_id": recovery_attempt_id,
            "attempt_number": attempt_number, "short_url": short_url,
        },
        "scheduled_for": scheduled_for,
    })

    if status != "failed":
        # A failed live call never actually reached the customer or put money
        # at risk, so it must not consume the daily contact/value caps.
        is_contact = action in _CONTACT_ACTIONS
        db.incr_daily_counter(
            merchant_id,
            value_paise=event["amount_paise"],
            contacts=1 if is_contact else 0,
        )

        if is_contact and status != "scheduled":
            from . import notification_service
            attempt_record = db.get_recovery_attempt(recovery_attempt_id)
            if attempt_record:
                notification_service.send_customer_notification(
                    merchant_id=merchant_id,
                    event=event,
                    recovery_attempt=attempt_record,
                    customer=customer,
                    short_url=short_url,
                )

    logger.info("action executed", extra={"context": {
        "event_id": event_id, "recovery_attempt_id": recovery_attempt_id,
        "action": action.value, "mechanism": mechanism.value,
        "execution_mode": execution_mode, "status": status,
    }})

    return ExecutionResult(
        recovery_attempt_id=recovery_attempt_id, status=status,
        execution_mechanism=mechanism.value, execution_mode=execution_mode,
        razorpay_ref=razorpay_ref, short_url=short_url, scheduled_for=scheduled_for,
        error=error_message,
    )
