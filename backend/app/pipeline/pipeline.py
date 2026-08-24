"""The deterministic recovery pipeline (doc A0 `pipeline.py`; final flow
doc §3.17). `process_event()` is the single entrypoint both the webhook
handler and the synthetic batch runner call — it always writes exactly the
same 6-stage audit trail (doc C5: detected/analyzed/decided/guardrail/
executed/outcome) regardless of which branch the event takes, so the audit
trail is uniform and testable (doc A6).

When `use_ai=True`, stages 2-5 are delegated to the agentic tool-use loop
(`services.agent_service`) instead of being called directly here — but every
tool the agent can call is the exact same guarded Python function used in
the deterministic path, so the safety guarantees (doc C4/§3.8) are identical
either way.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from .. import db
from ..config import settings
from ..domain import cause_analysis, decision_engine, guardrails
from ..enums import Action, AuditStage, Cause, EventStatus, ExecutionMechanism
from ..logging_config import get_logger
from ..services import ai_service, execution_service
from . import attribution

logger = get_logger("reviveo.pipeline")

AuditFn = Callable[..., None]


def _audit(*, event_id: str, merchant_id: str, stage: AuditStage, message: str,
           payload: Optional[dict] = None, ai_used: bool = False, ai_model: Optional[str] = None,
           ai_latency_ms: Optional[int] = None, fallback_triggered: bool = False) -> None:
    db.insert_audit({
        "event_id": event_id, "merchant_id": merchant_id, "stage": stage.value,
        "message": message, "payload": payload or {}, "ai_used": ai_used,
        "ai_model": ai_model, "ai_latency_ms": ai_latency_ms,
        "fallback_triggered": fallback_triggered,
    })


def process_event(event: dict, *, use_ai: bool = False) -> dict:
    """Runs the full pipeline for an already-persisted event (status must
    already be 'detected' — the caller is responsible for `db.insert_event`).
    Returns a small summary dict describing where the event ended up.
    """
    event_id = event["event_id"]
    merchant_id = event["merchant_id"]
    cfg = db.get_guardrail_config(merchant_id)

    # ── Stage 1: detected ───────────────────────────────────────────────────
    _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.detected,
           message=f"Event detected: {event['type']}",
           payload={"type": event["type"], "amount_paise": event["amount_paise"],
                     "origin": event.get("origin")})

    if use_ai:
        from ..services import agent_service
        return agent_service.run_agent_for_event(event=event, cfg=cfg, audit=_audit)

    return _process_event_deterministic(event, cfg)


def _process_event_deterministic(event: dict, cfg: dict) -> dict:
    event_id = event["event_id"]
    merchant_id = event["merchant_id"]

    # ── Stage 2: analyzed ────────────────────────────────────────────────────
    cause = cause_analysis.classify_cause(event.get("error_code"), event.get("error_description"))
    ai_used_for_cause = False
    fallback_used = False
    if cause == Cause.unclassified and event.get("error_code"):
        # AI enrichment only (doc C6) — never changes the deterministic
        # policy path; `cause` stays `unclassified` regardless of what
        # comes back, so the low-confidence auto-escalate rule always holds.
        ai_result = ai_service.classify_unknown_cause(
            error_code=event.get("error_code"), error_description=event.get("error_description"))
        ai_used_for_cause = ai_result.used
        fallback_used = ai_result.fallback_triggered

    customer = db.get_customer(merchant_id, event["customer_id"]) if event.get("customer_id") else None
    subscription = db.get_subscription(event["subscription_id"]) if event.get("subscription_id") else None
    # Live current state drives the policy decision (a halted subscription must
    # be decided on *now* semantics), while the persisted
    # subscription_state_before keeps the ingest-time transition visible on
    # the dashboard (doc §3.16).
    sub_state_live = subscription["state"] if subscription else None

    db.update_event(event_id, cause=cause.value, status=EventStatus.analyzing.value,
                     subscription_state_before=event.get("subscription_state_before") or sub_state_live)
    _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.analyzed,
           message=f"Classified cause: {cause.value}",
           payload={"cause": cause.value, "customer_id": event.get("customer_id"),
                     "subscription_state": sub_state_live},
           ai_used=ai_used_for_cause, fallback_triggered=fallback_used)

    # ── Stage 3: decided ─────────────────────────────────────────────────────
    attempt_count = db.count_attempts(event_id)
    decision = decision_engine.decide(
        cause=cause, event_type=event["type"], subscription_state=sub_state_live,
        customer=customer, attempt_count=attempt_count,
        high_confidence=cfg["high_confidence"], low_confidence=cfg["low_confidence"],
    )
    reasoning_result = ai_service.generate_reasoning_text(
        cause=cause.value, action=decision.action.value, confidence=decision.confidence,
        fallback=decision.reasoning,
    )
    decision_expires_at = (datetime.now(timezone.utc) + timedelta(hours=settings.decision_ttl_hours)).isoformat()
    db.insert_decision({
        "event_id": event_id, "merchant_id": merchant_id, "action": decision.action.value,
        "execution_mechanism": decision.execution_mechanism.value if decision.execution_mechanism else None,
        "confidence": decision.confidence, "risk_tier": decision.risk_tier.value,
        "requires_approval": decision.requires_approval, "reasoning": reasoning_result.text,
        "ai_used": reasoning_result.used, "policy_version": decision_engine.POLICY_VERSION,
        "decision_expires_at": decision_expires_at,
    })
    db.update_event(event_id, status=EventStatus.action_selected.value)
    _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.decided,
           message=f"Selected action: {decision.action.value}",
           payload={"action": decision.action.value, "confidence": decision.confidence,
                     "risk_tier": decision.risk_tier.value, "reasoning": reasoning_result.text},
           ai_used=reasoning_result.used, ai_model=reasoning_result.model,
           ai_latency_ms=reasoning_result.latency_ms,
           fallback_triggered=reasoning_result.fallback_triggered)

    # ── Stage 4: guardrail ───────────────────────────────────────────────────
    last_attempt_at = db.last_attempt_time(event_id)
    g = guardrails.check_guardrails(
        merchant_id=merchant_id, cfg=cfg, action=decision.action,
        amount_paise=event["amount_paise"], attempt_count=attempt_count,
        last_attempt_at=last_attempt_at, event_created_at=event["created_at"],
    )
    _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.guardrail,
           message="Guardrails blocked this action" if g.blocked else "Guardrails passed",
           payload={"blocked": g.blocked, "code": g.code, "reason": g.reason,
                     "requires_approval": g.requires_approval})

    needs_approval = (
        decision.action == Action.escalate_to_human
        or decision.requires_approval
        or g.requires_approval
        or (g.blocked and g.code not in ("recovery_window_expired", "cooldown_active"))
    )

    # ── Stage 5 & 6: executed / outcome ──────────────────────────────────────
    if g.blocked and g.code == "recovery_window_expired":
        attribution.mark_expired(event_id, g.reason or "recovery window expired")
        _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.executed,
               message="Skipped — recovery window expired", payload={"skipped": True})
        _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.outcome,
               message="Event expired", payload={"status": EventStatus.expired.value})
        return {"event_id": event_id, "status": EventStatus.expired.value, "action": decision.action.value}

    if g.blocked and g.code == "cooldown_active":
        # Not a failure — reschedule the same action for when the cooldown
        # lifts instead of escalating to a human unnecessarily.
        db.update_event(event_id, status=EventStatus.scheduled.value)
        _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.executed,
               message="Scheduled — cooldown active", payload={"scheduled_for": g.retry_after})
        _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.outcome,
               message="Awaiting cooldown before retrying", payload={"status": "pending"})
        return {"event_id": event_id, "status": EventStatus.scheduled.value, "action": decision.action.value}

    if needs_approval:
        ai_summary = ai_service.summarize_for_approval(
            event=event, decision={"action": decision.action.value, "confidence": decision.confidence},
            guardrail_reason=g.reason, fallback=decision.reasoning,
        )
        approval_id = db.insert_approval({
            "merchant_id": merchant_id, "event_id": event_id,
            "proposed_action": decision.action.value,
            "execution_mechanism": decision.execution_mechanism.value if decision.execution_mechanism else None,
            "amount_paise": event["amount_paise"], "reason": g.reason or decision.reasoning,
            "ai_summary": ai_summary.text,
        })
        db.update_event(event_id, status=EventStatus.approval_pending.value)
        _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.executed,
               message="Routed to approval queue", payload={"approval_id": approval_id},
               ai_used=ai_summary.used, ai_model=ai_summary.model,
               ai_latency_ms=ai_summary.latency_ms, fallback_triggered=ai_summary.fallback_triggered)
        _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.outcome,
               message="Pending human approval", payload={"status": "pending", "approval_id": approval_id})
        return {"event_id": event_id, "status": EventStatus.approval_pending.value, "action": decision.action.value}

    # Auto-execute path (high confidence, or medium-confidence low-risk).
    result = execution_service.execute_action(
        merchant_id=merchant_id, event=event, action=decision.action,
        mechanism=decision.execution_mechanism or ExecutionMechanism.reminder_only,
        customer=customer,
    )
    if result.status == "scheduled":
        new_status = EventStatus.scheduled.value
    elif result.status == "failed":
        # A live Razorpay call failed at the provider (network/API error) —
        # a real, visible failure, never silently treated as "awaiting outcome".
        new_status = EventStatus.failed.value
    else:
        new_status = EventStatus.waiting_for_outcome.value
    db.update_event(event_id, status=new_status)
    _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.executed,
           message=(f"Execution failed at the payment provider: {result.error}" if result.status == "failed"
                    else f"Executed via {result.execution_mechanism}"),
           payload={"recovery_attempt_id": result.recovery_attempt_id,
                     "execution_mode": result.execution_mode, "razorpay_ref": result.razorpay_ref,
                     "error": result.error})
    _audit(event_id=event_id, merchant_id=merchant_id, stage=AuditStage.outcome,
           message="Execution failed — no outcome to await" if result.status == "failed" else "Awaiting payment outcome",
           payload={"status": "failed" if result.status == "failed" else "pending",
                     "recovery_attempt_id": result.recovery_attempt_id})
    return {"event_id": event_id, "status": new_status, "action": decision.action.value,
            "recovery_attempt_id": result.recovery_attempt_id}


_RESOLVED_STATUSES = {
    EventStatus.recovered.value, EventStatus.expired.value, EventStatus.closed.value,
    EventStatus.escalated.value, EventStatus.failed.value,
}


def revalidate_and_execute_scheduled(attempt: dict) -> None:
    """Before any scheduled action executes: revalidate event status,
    recovery state, recovery window, cooldown, retry count, and every
    guardrail — this re-enters the exact same policy + execution path,
    never a shortcut (doc §3.11).
    """
    event = db.get_event(attempt["event_id"])
    if event is None or event["status"] in _RESOLVED_STATUSES:
        # Already resolved via another path (e.g. an outcome webhook arrived
        # first) — a stale scheduled attempt must not act on it.
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="expired")
        return

    merchant_id = event["merchant_id"]
    cfg = db.get_guardrail_config(merchant_id)
    customer = db.get_customer(merchant_id, event["customer_id"]) if event.get("customer_id") else None
    action = Action(attempt["action"])

    # This scheduled attempt already has its own row in recovery_attempts;
    # subtract 1 so the count matches what it was at the moment the action
    # was originally scheduled (consistent with how it was first checked).
    prior_attempt_count = max(0, db.count_attempts(event["event_id"]) - 1)

    g = guardrails.check_guardrails(
        merchant_id=merchant_id, cfg=cfg, action=action, amount_paise=attempt["amount_paise"],
        attempt_count=prior_attempt_count, last_attempt_at=None,
        event_created_at=event["created_at"],
    )
    _audit(event_id=event["event_id"], merchant_id=merchant_id, stage=AuditStage.guardrail,
           message="Revalidated scheduled action" + (" — blocked" if g.blocked else " — passed"),
           payload={"blocked": g.blocked, "code": g.code, "reason": g.reason})

    if g.blocked and g.code == "recovery_window_expired":
        attribution.mark_expired(event["event_id"], g.reason or "expired")
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="expired")
        _audit(event_id=event["event_id"], merchant_id=merchant_id, stage=AuditStage.outcome,
               message="Event expired at scheduled execution time", payload={"status": "expired"})
        return

    if g.blocked:
        db.update_recovery_attempt(attempt["recovery_attempt_id"], status="failed")
        db.update_event(event["event_id"], status=EventStatus.escalated.value)
        _audit(event_id=event["event_id"], merchant_id=merchant_id, stage=AuditStage.outcome,
               message=f"Scheduled action blocked at execution time: {g.reason}",
               payload={"status": "escalated"})
        return

    mechanism = ExecutionMechanism(attempt["execution_mechanism"])
    result = execution_service.execute_action(
        merchant_id=merchant_id, event=event, action=action, mechanism=mechanism,
        customer=customer, immediate=True,
    )
    # The original scheduled row is superseded by the freshly-executed one —
    # mark it resolved so the scheduler never picks it up again.
    db.update_recovery_attempt(attempt["recovery_attempt_id"], status="failed",
                                resolved_at=datetime.now(timezone.utc).isoformat())
    db.update_event(event["event_id"], status=EventStatus.waiting_for_outcome.value)
    _audit(event_id=event["event_id"], merchant_id=merchant_id, stage=AuditStage.executed,
           message=f"Executed scheduled action via {result.execution_mechanism}",
           payload={"recovery_attempt_id": result.recovery_attempt_id})
    _audit(event_id=event["event_id"], merchant_id=merchant_id, stage=AuditStage.outcome,
           message="Awaiting payment outcome", payload={"status": "pending"})


def reanalyze_decision(event: dict) -> dict:
    """Re-runs cause classification + the decision engine against the
    event's *current* state (doc §3.13: "if a delayed action or approval is
    stale, re-check/re-analyze before execution"). Used by the approval
    endpoint when the stored decision has passed its `decision_expires_at`.
    Does not execute anything — only returns a fresh action/mechanism.
    """
    merchant_id = event["merchant_id"]
    cfg = db.get_guardrail_config(merchant_id)
    cause = cause_analysis.classify_cause(event.get("error_code"), event.get("error_description"))
    customer = db.get_customer(merchant_id, event["customer_id"]) if event.get("customer_id") else None
    subscription = db.get_subscription(event["subscription_id"]) if event.get("subscription_id") else None
    attempt_count = db.count_attempts(event["event_id"])

    decision = decision_engine.decide(
        cause=cause, event_type=event["type"],
        subscription_state=subscription["state"] if subscription else None,
        customer=customer, attempt_count=attempt_count,
        high_confidence=cfg["high_confidence"], low_confidence=cfg["low_confidence"],
    )
    decision_expires_at = (datetime.now(timezone.utc) + timedelta(hours=settings.decision_ttl_hours)).isoformat()
    db.insert_decision({
        "event_id": event["event_id"], "merchant_id": merchant_id, "action": decision.action.value,
        "execution_mechanism": decision.execution_mechanism.value if decision.execution_mechanism else None,
        "confidence": decision.confidence, "risk_tier": decision.risk_tier.value,
        "requires_approval": decision.requires_approval, "reasoning": f"[re-analyzed] {decision.reasoning}",
        "ai_used": False, "policy_version": decision_engine.POLICY_VERSION,
        "decision_expires_at": decision_expires_at,
    })
    return {
        "action": decision.action.value,
        "execution_mechanism": decision.execution_mechanism.value if decision.execution_mechanism else None,
        "confidence": decision.confidence,
    }
