"""Single shared execution path — compatibility shim (doc §3.8/§3.11).

The live single writer of `recovery_attempts` and sole Razorpay caller is
`services/execution_service.execute_action` (per §3.8). This module previously
duplicated that logic with diverging Razorpay calls (`send_reminder`,
`manual_charge`, `monitor_native` missing on `razorpay_service`). Consolidated
2026-08-24: now delegates to the live service so every caller — `pipeline`,
`scheduler`, `agent`, and any legacy `pipeline.executor` import — goes through
the same code path. New code should import `services.execution_service`.

Implements the same `execute_decision` / `resume_scheduled_attempt` surface
for backward compatibility, but execution mode and customer resolution now use
the live service's production logic (dry_run vs live_call derived from
`settings.is_live` + `razorpay_configured`).
"""

from __future__ import annotations

from typing import Optional

from ..enums import Action, ExecutionMechanism, ExecutionMode
from ..services import execution_service as _live
from ..services.execution_service import ExecutionResult  # re-export

# Keep original helpers for callers that imported them
_FALLBACK_MESSAGE = (
    "We couldn't process your recent payment. Please complete your payment securely "
    "using the link below to keep your subscription active. Amount due: ₹{rupees}."
)


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
    """Legacy `execute_decision` shape → delegates to live `execute_action`.

    Returns ``{"attempt": ..., "outcome": ..., "scheduled": bool}`` for
    backward compatibility with any external callers that still import this
    path.

    `scheduled_for` forces an immediate execution (mirrors the
    `smart_retry_24h` + scheduler flow where the shim's caller has already
    decided the cooldown has elapsed). `execution_mode` is honored only as a
    hint — live `execution_service` derives the canonical mode from
    `settings.is_live` + `razorpay_configured`, which is the auditable
    `dry_run` vs `live_call` truth per §3.14.
    """
    from .. import db as _db

    action = Action(decision["action"])
    mechanism_raw = decision.get("mechanism")
    mechanism = ExecutionMechanism(mechanism_raw) if mechanism_raw else ExecutionMechanism.reminder_only
    # Resolve customer for audit/logging parity with live path
    customer = None
    try:
        cid = event.get("customer_id")
        if cid:
            customer = _db.get_customer(event["merchant_id"], cid)
    except Exception:
        customer = None
    result: ExecutionResult = _live.execute_action(
        merchant_id=event["merchant_id"], event=event,
        action=action, mechanism=mechanism,
        customer=customer, immediate=scheduled_for is not None,
    )
    attempt = {
        "recovery_attempt_id": result.recovery_attempt_id,
        "status": result.status,
        "execution_mechanism": result.execution_mechanism,
        "execution_mode": result.execution_mode,
        "razorpay_ref": result.razorpay_ref,
        "reference_id": f"rvo_{result.recovery_attempt_id}"[:40],
    }
    # Map ExecutionResult → old outcome shape
    outcome = None
    if result.status == "failed":
        outcome = type("Outcome", (), {"ok": False, "error": result.error, "razorpay_ref": result.razorpay_ref})()
    elif result.razorpay_ref:
        outcome = type("Outcome", (), {"ok": True, "razorpay_ref": result.razorpay_ref})()
    return {"attempt": attempt, "outcome": outcome, "scheduled": result.status == "scheduled"}


def resume_scheduled_attempt(attempt: dict) -> dict:
    """Legacy `resume_scheduled_attempt` → delegates to live pipeline
    revalidation path (`pipeline.revalidate_and_execute_scheduled`)."""
    from ..pipeline import pipeline as _pipeline
    # Live revalidation is now in `pipeline.revalidate_and_execute_scheduled`
    # which already handles guardrail + execution via `execution_service`.
    try:
        _pipeline.revalidate_and_execute_scheduled(attempt)
        return {"executed": True}
    except Exception as exc:  # noqa: BLE001
        return {"executed": False, "error": str(exc)}
