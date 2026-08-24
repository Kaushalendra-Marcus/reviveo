"""Human approval workflow (doc A2, §3.12, §3.13).

AUDIT NOTE (2026-08-24): this module is NOT wired into the live app.
`api/routes.py`'s `POST /api/approvals/{id}/approve` and `/deny` endpoints —
the actual HTTP-facing approval flow — implement their own inline logic and
never call `approve()`/`deny()`/`enqueue()` below (verified by reading every
import in `api/routes.py`). Nothing in the deterministic pipeline
(`pipeline.py`) or the agentic loop (`services/agent_service.py`) calls
`enqueue()` either — both insert into `pending_approvals` directly. The only
caller of this module was `agent/tools.py`'s `escalate_to_human` tool, which
is itself unreachable (see that module's docstring).

This module has been fixed (routed through the canonical
`services/execution_service.execute_action` and `domain/guardrails.
check_guardrails`, and the canonical `services/ai_service.py` interface)
so it is no longer a landmine if it's ever revived, but it remains inert
duplicate code today. See AUDIT_REPORT.md and TODO.md for the recommended
cleanup (delete this module, or wire `api/routes.py` to call it, once
independently re-verified).

State machine: pending → approved → executing → executed (branches: denied,
expired, execution_failed). Claims are atomic (`UPDATE ... WHERE status=?`,
rowcount==1) so double-clicks and concurrent reviewers can never trigger
duplicate money-moving operations. Stale decisions are re-checked before any
execution (§3.13).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..config import settings
from ..domain.guardrails import check_guardrails
from ..enums import Action, ApprovalStatus, AuditStage, ExecutionMechanism, EventStatus
from ..logging_config import get_logger
from . import ai_service, execution_service

logger = get_logger("reviveo.approvals")


def enqueue(
    merchant_id: str,
    event: dict,
    decision: dict,
    *,
    reason: str = "",
) -> int:
    """Route an event to a human. Inserts the approval row + approval audit."""
    ai_result = ai_service.summarize_for_approval(
        event=event,
        decision=decision,
        guardrail_reason=reason or None,
        fallback=reason or decision.get("reasoning") or "Routed to human approval.",
    )
    summary = ai_result.text

    approval_id = db.insert_approval({
        "merchant_id": merchant_id,
        "event_id": event["event_id"],
        "proposed_action": decision["action"],
        "execution_mechanism": decision.get("mechanism"),
        "amount_paise": event["amount_paise"],
        "reason": reason or decision.get("reasoning"),
        "ai_summary": summary,
    })
    db.insert_audit({
        "event_id": event["event_id"], "merchant_id": merchant_id,
        "stage": AuditStage.guardrail.value,
        "message": f"Routed to human approval ({decision['action']}): "
                   f"{reason or 'policy requires review'}.",
        "payload": {"approval_id": approval_id, "ai_summary_attached": summary is not None},
        "ai_used": ai_result.used, "ai_model": ai_result.model,
        "ai_latency_ms": ai_result.latency_ms, "fallback_triggered": ai_result.fallback_triggered,
    })
    return approval_id


def approve(approval_id: int, resolved_by: str = "merchant-dashboard") -> dict:
    """Atomically claim + execute an approved action through the shared path."""
    row = db.get_approval(approval_id)
    if row is None:
        raise KeyError(f"Unknown approval {approval_id}")

    # §3.12 — atomic claim; only one caller can win.
    if not db.set_approval_status(approval_id, ApprovalStatus.pending.value,
                                  ApprovalStatus.approved.value, resolved_by):
        return {"ok": False, "error": "conflict", "detail":
                f"Approval {approval_id} is '{row['status']}', not pending."}

    if not db.set_approval_status(approval_id, ApprovalStatus.approved.value,
                                  ApprovalStatus.executing.value, resolved_by):
        return {"ok": False, "error": "conflict"}

    event = db.get_event(row["event_id"])
    cfg = db.get_guardrail_config(row["merchant_id"])

    def finish(status: ApprovalStatus, message: str, payload: dict) -> dict:
        db.set_approval_status(approval_id, ApprovalStatus.executing.value, status.value,
                               resolved_by)
        db.insert_audit({
            "event_id": row["event_id"], "merchant_id": row["merchant_id"],
            "stage": AuditStage.executed.value, "message": message, "payload": payload,
        })
        return {"ok": status is ApprovalStatus.executed, "status": status.value}

    # §3.13 — stale decision protection: never execute on an expired decision.
    expires_at = event.get("decision_expires_at")
    if expires_at and datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
        db.set_approval_status(approval_id, ApprovalStatus.executing.value,
                               ApprovalStatus.expired.value, resolved_by)
        db.update_event(row["event_id"], status=EventStatus.analyzing.value)
        db.insert_audit({
            "event_id": row["event_id"], "merchant_id": row["merchant_id"],
            "stage": AuditStage.guardrail.value,
            "message": "Approval arrived after the decision expired — event sent for "
                       "re-analysis instead of executing stale instructions.",
            "payload": {"approval_id": approval_id},
        })
        return {"ok": False, "status": "expired",
                "detail": "Decision stale — event queued for re-analysis."}

    if event["status"] in ("failed", "closed"):
        return finish(ApprovalStatus.execution_failed,
                      f"Event already {event['status']}; nothing to execute.", {})

    if row["execution_mechanism"] is None:
        # A genuine escalate_to_human proposal — there is no automated
        # mechanism to run; approving records that a human handles this
        # outside the system.
        db.update_event(row["event_id"], status=EventStatus.closed.value)
        return finish(ApprovalStatus.executed, f"Approved by {resolved_by} for manual handling.", {})

    # Fresh guardrails at execution time — approval is not a bypass (doc C4).
    attempt_count = db.count_attempts(row["event_id"])
    last_attempt_at = db.last_attempt_time(row["event_id"])
    guard = check_guardrails(
        merchant_id=row["merchant_id"], cfg=cfg, action=Action(row["proposed_action"]),
        amount_paise=row["amount_paise"], attempt_count=attempt_count,
        last_attempt_at=last_attempt_at, event_created_at=event["created_at"],
    )
    if guard.blocked:
        transition_failed(event, row)
        return finish(ApprovalStatus.execution_failed,
                      f"Guardrails blocked approved action: {guard.reason}",
                      {"code": guard.code, "reason": guard.reason})

    customer = db.get_customer(row["merchant_id"], event["customer_id"]) if event.get("customer_id") else None
    result = execution_service.execute_action(
        merchant_id=row["merchant_id"], event=event,
        action=Action(row["proposed_action"]),
        mechanism=ExecutionMechanism(row["execution_mechanism"]),
        customer=customer,
    )
    if result.status == "scheduled":
        db.update_event(row["event_id"], status=EventStatus.scheduled.value)
    elif result.status == "failed":
        db.update_event(row["event_id"], status=EventStatus.failed.value)
    else:
        db.update_event(row["event_id"], status=EventStatus.waiting_for_outcome.value)

    if result.status == "failed":
        return finish(ApprovalStatus.execution_failed,
                      f"Execution failed at the payment provider: {result.error}",
                      {"recovery_attempt_id": result.recovery_attempt_id, "error": result.error})
    return finish(ApprovalStatus.executed,
                  f"Approved by {resolved_by} and executed via shared execution path.",
                  {"recovery_attempt_id": result.recovery_attempt_id})


def deny(approval_id: int, resolved_by: str = "merchant-dashboard",
         reason: str = "") -> dict:
    """Deny writes a failed outcome (doc A2) — the event closes honestly."""
    row = db.get_approval(approval_id)
    if row is None:
        raise KeyError(f"Unknown approval {approval_id}")
    if not db.set_approval_status(approval_id, ApprovalStatus.pending.value,
                                  ApprovalStatus.denied.value, resolved_by):
        return {"ok": False, "error": "conflict",
                "detail": f"Approval {approval_id} is '{row['status']}', not pending."}
    db.update_event(row["event_id"], status=EventStatus.failed.value)
    db.insert_audit({
        "event_id": row["event_id"], "merchant_id": row["merchant_id"],
        "stage": AuditStage.outcome.value,
        "message": f"Recovery denied by {resolved_by}"
                   + (f" — {reason}" if reason else "")
                   + "; no further automated attempts.",
        "payload": {"approval_id": approval_id},
    })
    return {"ok": True, "status": "denied"}


def expire_stale() -> int:
    """Pending approvals older than the decision TTL expire (§3.12/§3.13)."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=settings.decision_ttl_hours)
    ).isoformat()
    rows = db.query_all(
        "SELECT id FROM pending_approvals WHERE status='pending' AND created_at < ?",
        (cutoff,),
    )
    n = 0
    for r in rows:
        if db.set_approval_status(r["id"], ApprovalStatus.pending.value,
                                  ApprovalStatus.expired.value, "system-ttl"):
            ev = db.get_approval(r["id"])
            if ev and db.get_event(ev["event_id"]) is not None:
                db.update_event(ev["event_id"], status=EventStatus.analyzing.value)
            n += 1
    return n


def transition_failed(event: dict, row: dict) -> None:
    # NOTE: the original version of this file imported `.state_machine`,
    # which does not exist under `services/` (state_machine.py lives under
    # `pipeline/`) — that would have raised ImportError the first time this
    # dead branch actually ran. Fixed as part of the 2026-08-24 audit.
    from ..pipeline.state_machine import transition

    transition(event["event_id"], EventStatus.failed)
