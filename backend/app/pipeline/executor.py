"""Single shared execution path (doc §3.8/§3.11).

AUDIT NOTE (2026-08-24): despite the module docstring below, this is NOT
the execution path actually used by the live app. The real single shared
execution path is `services/execution_service.execute_action`, called by
`pipeline.py`, `services/agent_service.py`, and `api/routes.py`'s
`approve_approval`. This module's only caller was `services/approvals.py`
(itself unreachable from any route — see that module's docstring), which
has been fixed to call `execution_service.execute_action` instead, so
`execute_decision`/`resume_scheduled_attempt` below are now fully
unreferenced. They are also independently broken: `execute_decision` calls
`razorpay_service.send_reminder(...)`, `razorpay_service.manual_charge(...)`,
and `razorpay_service.monitor_native(...)`, none of which exist on
`services/razorpay_service.py` (only `create_payment_link`,
`fetch_payment_link`, and `verify_webhook_signature` are defined there) —
calling this function would raise `AttributeError` for every mechanism
except `checkout`/`payment_link`. Left unfixed deliberately: rewriting this
to be correct would just duplicate `execution_service.py`. Recommended
action is deletion — see AUDIT_REPORT.md and TODO.md.

Pipeline, approvals, scheduler and agent tools ALL execute through
`execute_decision` / `resume_scheduled_attempt`. There is no side door around
policy checks: guardrails run before anything here is called, and this module
persists the recovery_attempt + audit rows that attribution later resolves.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..agent import ai_service
from ..enums import Action, AuditStage, EventStatus, ExecutionMechanism, ExecutionMode
from ..logging_config import get_logger
from ..services import razorpay_service
from .state_machine import transition

logger = get_logger("reviveo.executor")

_FALLBACK_MESSAGE = (
    "We couldn't process your recent payment. Please complete your payment securely "
    "using the link below to keep your subscription active. Amount due: ₹{rupees}."
)


def _customer_message(event: dict, amount_paise: int, ai_used: bool = False) -> str:
    """AI-drafted copy with a deterministic template fallback (doc C6)."""
    if not ai_used:
        return _FALLBACK_MESSAGE.format(rupees=amount_paise / 100)
    drafted = ai_service.draft_customer_message({
        "amount_rupees": amount_paise / 100,
        "cause": event.get("cause"),
        "plan": "subscription",
    })
    if drafted is None:
        return _FALLBACK_MESSAGE.format(rupees=amount_paise / 100)
    text, _latency = drafted
    return text


def _resolve_mode(event: dict, override: Optional[ExecutionMode]) -> ExecutionMode:
    if override is not None:
        return override
    if settings_is_live() and event.get("origin") == "live_test_mode":
        return ExecutionMode.live_call
    return ExecutionMode.dry_run


def settings_is_live() -> bool:
    from ..config import settings

    return settings.is_live


def execute_decision(
    event: dict,
    decision: dict,
    *,
    scheduled_for: Optional[str] = None,
    execution_mode: Optional[ExecutionMode] = None,
) -> dict:
    """Create the recovery_attempt row and perform the real mechanism.

    Returns {"attempt": ..., "outcome": ..., "scheduled": bool}."""
    merchant_id = event["merchant_id"]
    action = Action(decision["action"])
    mechanism = (
        ExecutionMechanism(decision["mechanism"])
        if decision.get("mechanism") else None
    )
    mode = _resolve_mode(event, execution_mode)
    n = db.next_attempt_number(event["event_id"])
    rid = f"ra_{uuid.uuid4().hex[:12]}"
    reference_id = f"rev-{event['event_id']}-{n}"
    notes = {
        "event_id": event["event_id"],
        "recovery_attempt_id": rid,
        "attempt_number": n,
        "merchant_id": merchant_id,
    }

    outcome = None
    status = "awaiting_outcome"
    is_scheduled = False

    customer = db.get_customer(merchant_id, event.get("customer_id") or "")
    email = (customer or {}).get("email", "")

    if mechanism in (None, ExecutionMechanism.reminder_only):
        outcome = razorpay_service.send_reminder(email)
        if mechanism is None:
            status = "pending"  # approval-routed placeholder; no external action yet
    elif scheduled_for is not None or mechanism is ExecutionMechanism.scheduled_recovery_payment:
        # Nothing touches Razorpay yet — the scheduler revalidates first (§3.11).
        scheduled_for = scheduled_for or (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat()
        status = "scheduled"
        is_scheduled = True
    elif mechanism in (ExecutionMechanism.checkout, ExecutionMechanism.payment_link):
        outcome = razorpay_service.create_payment_link(
            amount_paise=event["amount_paise"],
            customer_email=email,
            customer_name=(customer or {}).get("name", ""),
            description=_customer_message(event, event["amount_paise"],
                                          ai_used=bool(decision.get("ai_used"))),
            reference_id=reference_id,
            notes=notes,
            execution_mode=mode,
        )
    elif mechanism in (ExecutionMechanism.new_recovery_payment,
                       ExecutionMechanism.manual_charge):
        outcome = razorpay_service.manual_charge(execution_mode=mode,
                                                 reference_id=reference_id)
    elif mechanism is ExecutionMechanism.native_subscription_retry:
        sub = db.get_subscription(event["subscription_id"]) if event.get("subscription_id") else None
        outcome = razorpay_service.monitor_native((sub or {}).get("id"))
    else:  # pragma: no cover — vocabulary is closed
        raise ValueError(f"Unhandled mechanism {mechanism}")

    attempt = {
        "recovery_attempt_id": rid,
        "event_id": event["event_id"],
        "merchant_id": merchant_id,
        "attempt_number": n,
        "action": action.value,
        "execution_mechanism": mechanism.value if mechanism else "none",
        "amount_paise": event["amount_paise"],
        "status": status,
        "execution_mode": mode.value,
        "razorpay_ref": outcome.razorpay_ref if outcome else None,
        "reference_id": reference_id,
        "notes": notes,
        "scheduled_for": scheduled_for if is_scheduled else None,
    }
    db.insert_recovery_attempt(attempt)

    audit_payload = {
        "recovery_attempt_id": rid,
        "attempt_number": n,
        "action": action.value,
        "mechanism": attempt["execution_mechanism"],
        "mode": mode.value,
        "razorpay_ref": attempt["razorpay_ref"],
    }
    if outcome is not None and not outcome.ok:
        message = f"Execution failed: {outcome.error}"
        db.update_recovery_attempt(rid, status="failed", resolved_at=db.now_iso())
        attempt["status"] = "failed"
    elif is_scheduled:
        message = (f"Scheduled '{action.value}' for "
                   f"{scheduled_for} — will revalidate all policy checks before executing.")
    else:
        message = f"Executed '{action.value}' via {attempt['execution_mechanism']} ({mode.value})."
        if action in (Action.send_reminder, Action.retry_and_notify,
                      Action.send_payment_update_link):
            db.incr_daily_counter(merchant_id, contacts=1)

    db.insert_audit({
        "event_id": event["event_id"], "merchant_id": merchant_id,
        "stage": AuditStage.executed.value, "message": message,
        "payload": audit_payload,
    })

    if attempt["status"] == "failed":
        cfg = db.get_guardrail_config(merchant_id)
        used = db.count_attempts(event["event_id"])
        if used >= cfg["max_retries"]:
            transition(event["event_id"], EventStatus.failed)
        else:
            transition(event["event_id"], EventStatus.waiting_for_outcome)
    elif is_scheduled:
        transition(event["event_id"], EventStatus.scheduled)
    else:
        transition(event["event_id"], EventStatus.waiting_for_outcome)

    return {"attempt": attempt, "outcome": outcome, "scheduled": is_scheduled}


def resume_scheduled_attempt(attempt: dict) -> dict:
    """§3.11 — a scheduled action re-enters the SAME policy + execution path.

    Revalidates: event status, obligation/recovery window, retry count, and
    every guardrail, before any Razorpay call happens."""
    from ..guardrails.guardrails import evaluate

    event = db.get_event(attempt["event_id"])
    if event is None:
        return {"skipped": "event missing"}
    merchant_id = attempt["merchant_id"]
    cfg = db.get_guardrail_config(merchant_id)

    def fail(reason: str) -> dict:
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="expired",
                                   resolved_at=db.now_iso())
        db.insert_audit({
            "event_id": attempt["event_id"], "merchant_id": merchant_id,
            "stage": AuditStage.executed.value,
            "message": f"Scheduled action cancelled before execution: {reason}",
            "payload": {"recovery_attempt_id": attempt["recovery_attempt_id"]},
        })
        return {"skipped": reason}

    if event["status"] in ("failed", "closed", "recovered"):
        return fail(f"event already terminal ({event['status']})")
    if db.count_attempts(attempt["event_id"]) > cfg["max_retries"]:
        return fail("retry limit exceeded")
    guard = evaluate(merchant_id, event, attempt["action"], attempt["amount_paise"],
                     cfg=cfg, exclude_attempt_id=attempt["recovery_attempt_id"])
    if not guard.passed:
        return fail("; ".join(guard.blocked_reasons))

    mode = ExecutionMode(attempt["execution_mode"])
    customer = db.get_customer(merchant_id, event.get("customer_id") or "")
    mechanism = ExecutionMechanism(attempt["execution_mechanism"])

    if mechanism in (ExecutionMechanism.checkout, ExecutionMechanism.payment_link):
        outcome = razorpay_service.create_payment_link(
            amount_paise=attempt["amount_paise"],
            customer_email=(customer or {}).get("email", ""),
            customer_name=(customer or {}).get("name", ""),
            description=_FALLBACK_MESSAGE.format(rupees=attempt["amount_paise"] / 100),
            reference_id=attempt["reference_id"] or f"rev-{attempt['event_id']}-{attempt['attempt_number']}",
            notes={"event_id": attempt["event_id"],
                   "recovery_attempt_id": attempt["recovery_attempt_id"],
                   "attempt_number": attempt["attempt_number"]},
            execution_mode=mode,
        )
        ref = outcome.razorpay_ref
    else:
        outcome = razorpay_service.manual_charge(execution_mode=mode,
                                                 reference_id=attempt["reference_id"] or attempt["recovery_attempt_id"])
        ref = outcome.razorpay_ref

    if not outcome.ok:
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="failed",
                                   resolved_at=db.now_iso())
        db.insert_audit({
            "event_id": attempt["event_id"], "merchant_id": merchant_id,
            "stage": AuditStage.executed.value,
            "message": f"Scheduled execution failed: {outcome.error}", "payload": {},
        })
        return {"executed": False, "error": outcome.error}

    db.update_recovery_attempt(
        attempt["recovery_attempt_id"],
        status="awaiting_outcome", razorpay_ref=ref,
        scheduled_for=None,
    )
    db.incr_daily_counter(merchant_id, contacts=1)
    db.insert_audit({
        "event_id": attempt["event_id"], "merchant_id": merchant_id,
        "stage": AuditStage.executed.value,
        "message": "Scheduled action revalidated (window/cooldown/guardrails) and executed.",
        "payload": {"recovery_attempt_id": attempt["recovery_attempt_id"],
                    "razorpay_ref": ref, "mode": mode.value},
    })
    transition(attempt["event_id"], EventStatus.waiting_for_outcome)
    return {"executed": True, "razorpay_ref": ref}
