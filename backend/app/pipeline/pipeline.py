"""Per-event recovery pipeline (doc C5, §3.17).

Deterministic path: ingest → analyze → decide → guard → execute/escalate →
outcome/attribution. The agentic layer (Part C) replaces steps 2–4 with a
tool-calling loop when `use_ai=True`; every AI-touched audit row records
ai_used/model/latency/fallback so the fallback story stays provable (C7).
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..agent import ai_service, loop as agent_loop
from ..config import settings
from ..domain.cause_analysis import classify_cause
from ..domain.decision_engine import POLICY_VERSION, as_decision_dict, decide
from ..enums import Action, AuditStage, Cause, EventStatus
from ..logging_config import get_logger
from ..services import approvals as approvals_service
from . import attribution, executor
from .state_machine import is_terminal, transition

logger = get_logger("reviveo.pipeline")


# ── ingestion ────────────────────────────────────────────────────────────────
def ingest_event(payload: dict) -> dict:
    """Persist a new event at status=detected + the first audit stage."""
    merchant_id = payload.get("merchant_id") or settings.default_merchant_id
    event_id = payload.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"
    sub_state = None
    if payload.get("subscription_id"):
        sub = db.get_subscription(payload["subscription_id"])
        sub_state = sub["state"] if sub else None

    event = {
        "event_id": event_id,
        "merchant_id": merchant_id,
        "customer_id": payload.get("customer_id"),
        "subscription_id": payload.get("subscription_id"),
        "invoice_id": payload.get("invoice_id"),
        "type": payload["type"],
        "error_code": payload.get("error_code"),
        "amount_paise": int(payload.get("amount_paise", 0)),
        "status": EventStatus.detected.value,
        "subscription_state_before": payload.get("subscription_state_before", sub_state),
        "origin": payload.get("origin", "synthetic"),
        "razorpay_payment_id": payload.get("razorpay_payment_id"),
    }
    db.insert_event(event)
    if event["customer_id"]:
        db.incr_customer_failed_count(merchant_id, event["customer_id"])
    db.insert_audit({
        "event_id": event_id, "merchant_id": merchant_id,
        "stage": AuditStage.detected.value,
        "message": f"Detected {event['type']} of ₹{event['amount_paise'] / 100:.2f}"
                   + (f" (subscription {event['subscription_state_before']})"
                      if event["subscription_state_before"] else ""),
        "payload": {"source": event["origin"], "razorpay_payment_id": event["razorpay_payment_id"]},
    })
    return db.get_event(event_id)  # type: ignore[return-value]


# ── decision + guard + execution ─────────────────────────────────────────────
def process_event(event_id: str, *, use_ai: bool = False) -> dict:
    ev = db.get_event(event_id)
    if ev is None:
        raise KeyError(f"Unknown event '{event_id}'")
    if is_terminal(ev):
        return {"event_id": event_id, "skipped": f"terminal ({ev['status']})"}

    merchant_id = ev["merchant_id"]
    cfg = db.get_guardrail_config(merchant_id)
    ai_meta: dict = {"ai_used": False, "fallback_triggered": False}

    # 1. analyze — deterministic cause classification.
    transition(event_id, EventStatus.analyzing)
    cause = classify_cause(ev.get("error_code"))
    ai_note = ""
    if cause is Cause.unclassified:
        # Advisory-only AI classification (doc C6); the low-confidence rule
        # still gates the action no matter what it returns.
        suggestion = ai_service.classify_unknown_cause(
            ev.get("error_code") or "", ev.get("error_code") or "")
        if suggestion is None:
            ai_meta["fallback_triggered"] = bool(use_ai and settings.ai_configured)
        else:
            label, latency = suggestion
            ai_meta.update({"ai_used": True, "ai_model": settings.ai_model_fast,
                            "ai_latency_ms": latency})
            ai_note = f"AI suggests '{label}' but confidence gating still applies; "
    db.update_event(event_id, cause=cause.value)
    db.insert_audit({
        "event_id": event_id, "merchant_id": merchant_id,
        "stage": AuditStage.analyzed.value,
        "message": f"{ai_note}Cause classified as '{cause.value}' from error signal "
                   f"'{ev.get('error_code')}'.",
        "payload": {"cause": cause.value, "error_code": ev.get("error_code")},
        **_ai_fields(ai_meta),
    })

    attempts_used = db.count_attempts(event_id)
    current_sub_state = None
    if ev.get("subscription_id"):
        sub = db.get_subscription(ev["subscription_id"])
        current_sub_state = sub["state"] if sub else None

    started = time.monotonic()
    decision: Optional[dict] = None

    # 2. decide — agent tool-loop first when enabled, deterministic otherwise.
    if use_ai:
        agent_result = agent_loop.run_agent(db.get_event(event_id), cfg=cfg)
        if agent_result is not None:
            decision = agent_result["decision"]
            ai_meta.update(agent_result["meta"])
        else:
            ai_meta["fallback_triggered"] = True
    if decision is None:
        d = decide(
            event_type=ev["type"],
            subscription_state=current_sub_state,
            cause=cause,
            attempts_count=attempts_used,
            low_confidence=cfg["low_confidence"],
            high_confidence=cfg["high_confidence"],
        )
        decision = as_decision_dict(d)

    reasoning_text = decision["reasoning"]
    if settings.ai_configured:
        phrased = ai_service.generate_reasoning_text({
            "cause": cause.value, "action": decision["action"],
            "confidence": decision["confidence"], "amount_rupees": ev["amount_paise"] / 100,
        })
        if phrased is not None:
            text, latency = phrased
            reasoning_text = text
            ai_meta.update({"ai_used": True, "ai_model": settings.ai_model_fast,
                            "ai_latency_ms": latency})
        elif use_ai:
            ai_meta["fallback_triggered"] = True
    decision["reasoning"] = reasoning_text

    decision_expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=settings.decision_ttl_hours)
    ).isoformat()
    db.insert_decision({
        "event_id": event_id, "merchant_id": merchant_id,
        **{k: decision[k] for k in
           ("action", "mechanism", "confidence", "risk_tier", "requires_approval",
            "reasoning", "policy_version")},
        "ai_used": ai_meta["ai_used"],
        "decision_expires_at": decision_expires_at,
    })
    db.update_event(event_id, decision_expires_at=decision_expires_at)
    transition(event_id, EventStatus.action_selected)
    db.insert_audit({
        "event_id": event_id, "merchant_id": merchant_id,
        "stage": AuditStage.decided.value,
        "message": reasoning_text,
        "payload": {"action": decision["action"], "mechanism": decision["mechanism"],
                    "confidence": decision["confidence"],
                    "risk_tier": decision["risk_tier"],
                    "requires_approval": decision["requires_approval"],
                    "policy_version": decision["policy_version"],
                    "agent_latency_ms": int((time.monotonic() - started) * 1000)},
        **_ai_fields(ai_meta),
    })

    # 3. guard — enforcement lives here, not in any model's judgment (C4).
    from ..guardrails.guardrails import evaluate

    amount = ev["amount_paise"]
    guard = evaluate(merchant_id, db.get_event(event_id), decision["action"], amount, cfg=cfg)
    db.insert_audit({
        "event_id": event_id, "merchant_id": merchant_id,
        "stage": AuditStage.guardrail.value,
        "message": ("All guardrails passed." if guard.passed
                    else f"Blocked: {'; '.join(guard.blocked_reasons)}.")
                   + (" Approval required by policy." if guard.requires_approval else ""),
        "payload": guard.as_payload(),
    })

    final_action = Action(decision["action"])
    if not guard.passed and final_action is not Action.escalate_to_human:
        decision = {
            **decision,
            "action": Action.escalate_to_human.value,
            "mechanism": None,
            "risk_tier": "safe",
            "requires_approval": False,
            "reasoning": decision["reasoning"]
                         + " Guardrails blocked execution — escalating to a human instead.",
        }
        final_action = Action.escalate_to_human

    # 4. approval gate or 5. execution.
    if final_action is Action.escalate_to_human or guard.requires_approval \
            or decision.get("requires_approval"):
        reason = ("guardrail policy requires review"
                  if guard.requires_approval or decision.get("requires_approval")
                  else "; ".join(guard.blocked_reasons))
        approval_id = approvals_service.enqueue(merchant_id, db.get_event(event_id),
                                                decision, reason=reason)
        transition(event_id, EventStatus.approval_pending)
        return {"event_id": event_id, "approval_id": approval_id,
                "status": EventStatus.approval_pending.value}

    result = executor.execute_decision(
        db.get_event(event_id), decision,
        scheduled_for=None,  # smart_retry_24h schedules itself inside executor
    )
    refreshed = db.get_event(event_id)

    # Synthetic dry-runs resolve immediately so demos show the full chain;
    # live executions wait for the real Razorpay outcome webhook.
    # Synthetic dry-runs resolve immediately so demos show the full chain;
    # live-origin executions always wait for the real Razorpay outcome
    # webhook (§3.14 — synthetic vs live_test_mode stay separate).
    attempt = result["attempt"]
    if (attempt["status"] == "awaiting_outcome"
            and attempt["execution_mode"] == "dry_run"
            and refreshed["origin"] == "synthetic"):
        stored = db.get_recovery_attempt(attempt["recovery_attempt_id"])
        sim = attribution.simulate_outcome(stored)
        attribution.apply_outcome(refreshed, stored, **sim)
        refreshed = db.get_event(event_id)

    return {"event_id": event_id, "status": refreshed["status"],
            "attempt": attempt, "scheduled": result["scheduled"]}


def _ai_fields(meta: dict) -> dict:
    return {
        "ai_used": int(bool(meta.get("ai_used"))),
        "ai_model": meta.get("ai_model"),
        "ai_latency_ms": meta.get("ai_latency_ms"),
        "fallback_triggered": int(bool(meta.get("fallback_triggered"))),
    }


def reanalyze_stale_event(event_id: str) -> dict:
    """§3.13 — stale approvals/scheduled actions re-enter analysis."""
    return process_event(event_id)
