"""Human approval workflow (doc A2, §3.12, §3.13).

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
from ..agent import ai_service
from ..config import settings
from ..enums import Action, ApprovalStatus, AuditStage, EventStatus
from ..logging_config import get_logger

logger = get_logger("reviveo.approvals")


def enqueue(
    merchant_id: str,
    event: dict,
    decision: dict,
    *,
    reason: str = "",
) -> int:
    """Route an event to a human. Inserts the approval row + approval audit."""
    summary = None
    ai_summary = ai_service.summarize_for_approval({
        "cause": decision.get("cause"),
        "action": decision.get("action"),
        "amount_rupees": event["amount_paise"] / 100,
        "reason": reason or decision.get("reasoning"),
        "customer": db.get_customer(merchant_id, event.get("customer_id") or ""),
    })
    if ai_summary is not None:
        summary, _latency = ai_summary

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
    })
    return approval_id


def approve(approval_id: int, resolved_by: str = "merchant-dashboard") -> dict:
    """Atomically claim + execute an approved action through the shared path."""
    from ..guardrails.guardrails import evaluate
    from ..pipeline import executor

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

    # Fresh guardrails at execution time — approval is not a bypass.
    guard = evaluate(row["merchant_id"], event, row["proposed_action"],
                     row["amount_paise"], cfg=cfg)
    if not guard.passed:
        transition_failed(event, row)
        return finish(ApprovalStatus.execution_failed,
                      f"Guardrails blocked approved action: {'; '.join(guard.blocked_reasons)}",
                      {"blocked_reasons": guard.blocked_reasons})

    decision = {
        "action": row["proposed_action"],
        "mechanism": row["execution_mechanism"],
        "ai_used": False,
    }
    result = executor.execute_decision(event, decision)

    if result["attempt"]["status"] == "failed":
        return finish(ApprovalStatus.execution_failed,
                      "Execution failed at the payment provider.", {})
    return finish(ApprovalStatus.executed,
                  f"Approved by {resolved_by} and executed via shared execution path.",
                  {"recovery_attempt_id": result["attempt"]["recovery_attempt_id"]})


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
    from .state_machine import transition

    transition(event["event_id"], EventStatus.failed)
