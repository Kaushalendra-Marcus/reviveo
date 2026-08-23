"""Agentic tool-use orchestration loop (doc C0-C5). Replaces the fixed
deterministic sequence with the model genuinely choosing which tool to call
next — but every tool is backed by the exact same guarded Python functions
the deterministic pipeline uses (doc C4: guardrail logic lives inside the
tool's Python code, never in the model's judgment), so the safety
guarantees are identical either way; only who drives the sequence changes.

No agent framework (doc C1) — native Claude tool_use, 6 tools, a short loop
bounded by MAX_AGENT_STEPS_PER_EVENT / MAX_TOOL_CALLS_PER_EVENT /
MAX_AGENT_WALL_TIME_SECONDS (doc §3.10). If the model stalls, loops, or the
API call fails outright, the loop always resolves to an escalation rather
than ever leaving an event stuck (doc C9/C10 — "what happens if the AI call
fails?").
"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

from .. import db
from ..config import settings
from ..domain import cause_analysis, decision_engine, guardrails
from ..enums import Action, AuditStage, Cause, EventStatus, ExecutionMechanism
from ..logging_config import get_logger
from . import ai_service, execution_service

logger = get_logger("reviveo.agent_service")

AGENT_VERSION = "agent-v1"

# doc C3 — exactly these six tools.
_TOOLS = [
    {
        "name": "get_customer_history",
        "description": (
            "Look up a customer's payment history: total amount recovered from them so far "
            "and how many of their payments have failed. Use this to judge how much "
            "benefit-of-the-doubt an automated recovery attempt deserves."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "classify_cause",
        "description": (
            "Classify a payment failure error code into exactly one cause: card_expired, "
            "insufficient_funds, payment_timeout, bank_declined, checkout_abandoned, or "
            "unclassified. Call this before proposing any action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "error_code": {"type": "string"},
                "error_description": {"type": "string"},
            },
            "required": ["error_code"],
        },
    },
    {
        "name": "check_guardrails",
        "description": (
            "Propose an action and get back the enforced verdict: whether it's blocked, "
            "whether it needs human approval, its confidence and risk tier — and if your "
            "proposed action isn't permitted for this cause, the action the policy engine "
            "used instead. This always runs the real policy and guardrail checks; you cannot "
            "bypass them by proposing something else. You MUST call this before calling any "
            "execution tool. Valid actions: send_reminder, smart_retry_24h, immediate_retry, "
            "retry_and_notify, send_payment_update_link, monitor_native_retry, "
            "escalate_to_human."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string"}},
            "required": ["action"],
        },
    },
    {
        "name": "create_payment_link",
        "description": (
            "Execute the action check_guardrails just cleared, when it involves sending the "
            "customer a payment link, checkout link, or reminder (send_reminder, "
            "smart_retry_24h, retry_and_notify, send_payment_update_link). Do not call this "
            "if check_guardrails returned blocked=true or requires_approval=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_paise": {"type": "integer"},
                "customer_email": {"type": "string"},
                "reason": {"type": "string", "description": "One-sentence reason, used in the audit trail."},
            },
            "required": ["reason"],
        },
    },
    {
        "name": "trigger_retry",
        "description": (
            "Execute the action check_guardrails just cleared, when it is immediate_retry or "
            "monitor_native_retry. Do not call this if check_guardrails returned "
            "blocked=true or requires_approval=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand this event to a human reviewer instead of acting automatically. Use this "
            "whenever check_guardrails blocked your proposal, returned requires_approval=true, "
            "or the classified cause is unclassified."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "summary": {"type": "string", "description": "1-2 sentence summary for a merchant reviewing this in a dashboard."},
            },
            "required": ["reason", "summary"],
        },
    },
]

_SYSTEM_PROMPT = (
    "You are Reviveo, an AI revenue-recovery agent for a Razorpay merchant. You are given "
    "one failed-payment event and must decide how to recover it, using only the tools "
    "provided.\n\n"
    "Rules you must follow exactly:\n"
    "1. Always call classify_cause first.\n"
    "2. Always call check_guardrails with your proposed action before executing anything — "
    "it enforces the real policy and you cannot override or skip it.\n"
    "3. If check_guardrails returns blocked=true or requires_approval=true, or the cause is "
    "unclassified, call escalate_to_human — do not retry with a different guess.\n"
    "4. Otherwise call exactly one matching execution tool (create_payment_link or "
    "trigger_retry) to finish.\n"
    "5. Never call the same tool with the same arguments twice. Stop after your one "
    "execution tool call."
)


class _AgentContext:
    """Mutable state threaded through one event's tool calls. The actual
    source of truth for what gets executed is always `checked_action` /
    `checked_mechanism`, set only by the `check_guardrails` tool — never
    whatever the model claims in a later tool call's own arguments."""

    def __init__(self, event: dict, cfg: dict, customer: Optional[dict], subscription: Optional[dict]):
        self.event = event
        self.cfg = cfg
        self.customer = customer
        self.subscription = subscription
        self.cause: Cause = Cause.unclassified
        self.checked_action: Optional[Action] = None
        self.checked_mechanism: Optional[ExecutionMechanism] = None
        self.checked_requires_approval: bool = False
        self.checked_blocked: bool = False
        self.checked_reason: Optional[str] = None
        self.executed = False
        self.result_summary: dict = {}
        self.tool_call_count = 0


def run_agent_for_event(*, event: dict, cfg: dict, audit: Callable[..., None]) -> dict:
    """The agentic replacement for the deterministic pipeline's stages 2-6.
    Falls back to the deterministic path outright if AI isn't actually
    configured/live — `use_ai=True` must never crash or hang the pipeline.
    """
    if not (settings.is_live and settings.ai_configured):
        from ..pipeline import pipeline as pipeline_module
        logger.info("use_ai requested but AI is not configured/live — falling back to deterministic path")
        return pipeline_module._process_event_deterministic(event, cfg)

    merchant_id = event["merchant_id"]
    customer = db.get_customer(merchant_id, event["customer_id"]) if event.get("customer_id") else None
    subscription = db.get_subscription(event["subscription_id"]) if event.get("subscription_id") else None
    ctx = _AgentContext(event, cfg, customer, subscription)

    client = ai_service.get_raw_client()
    messages: list[dict] = [{
        "role": "user",
        "content": json.dumps({
            "event_id": event["event_id"], "type": event["type"],
            "error_code": event.get("error_code"), "amount_paise": event["amount_paise"],
            "customer_id": event.get("customer_id"),
            "subscription_state": subscription["state"] if subscription else None,
        }),
    }]

    start = time.monotonic()
    steps = 0
    final_text: Optional[str] = None

    while steps < settings.max_agent_steps_per_event:
        if time.monotonic() - start > settings.max_agent_wall_time_seconds:
            logger.warning("agent wall time exceeded", extra={"context": {"event_id": event["event_id"]}})
            _force_escalate(ctx, merchant_id, "Agent exceeded its time budget", audit)
            break
        if ctx.tool_call_count >= settings.max_tool_calls_per_event:
            logger.warning("agent tool-call budget exceeded", extra={"context": {"event_id": event["event_id"]}})
            _force_escalate(ctx, merchant_id, "Agent exceeded its tool-call budget", audit)
            break

        steps += 1
        try:
            resp = client.messages.create(
                model=settings.ai_model_fast, max_tokens=1024, system=_SYSTEM_PROMPT,
                tools=_TOOLS, messages=messages,
            )
        except Exception as exc:  # noqa: BLE001 — the agent loop must never crash the pipeline
            logger.warning("agent Claude call failed", extra={"context": {"error": str(exc)}})
            _force_escalate(ctx, merchant_id, f"AI call failed: {exc}", audit)
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

        if not tool_uses:
            text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            final_text = "\n".join(t for t in text_blocks if t).strip() or None
            break

        tool_results = []
        for tool_use in tool_uses:
            ctx.tool_call_count += 1
            result = _dispatch_tool(tool_use.name, tool_use.input or {}, ctx, merchant_id, audit)
            tool_results.append({
                "type": "tool_result", "tool_use_id": tool_use.id,
                "content": json.dumps(result, default=str),
            })
            if ctx.executed:
                break
        messages.append({"role": "user", "content": tool_results})

        if ctx.executed:
            break

    if not ctx.executed:
        # Loop ended (max steps, or a final text reply with no execution)
        # without ever calling an execution tool — never leave the event stuck.
        _force_escalate(ctx, merchant_id, final_text or "Agent loop ended without executing an action", audit)

    audit(event_id=event["event_id"], merchant_id=merchant_id, stage=AuditStage.outcome,
          message="Agent loop finished", payload={"summary": ctx.result_summary, "steps": steps,
                                                    "tool_calls": ctx.tool_call_count})
    return {"event_id": event["event_id"], **ctx.result_summary}


def _dispatch_tool(name: str, args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    handler = {
        "get_customer_history": _tool_get_customer_history,
        "classify_cause": _tool_classify_cause,
        "check_guardrails": _tool_check_guardrails,
        "create_payment_link": _tool_create_payment_link,
        "trigger_retry": _tool_trigger_retry,
        "escalate_to_human": _tool_escalate_to_human,
    }.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'"}
    return handler(args, ctx, merchant_id, audit)


def _tool_get_customer_history(args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    customer_id = args.get("customer_id") or (ctx.customer or {}).get("id")
    customer = db.get_customer(merchant_id, customer_id) if customer_id else ctx.customer
    if not customer:
        return {"found": False}
    return {
        "found": True,
        "total_recovered_paise": customer.get("total_recovered_paise", 0),
        "failed_payment_count": customer.get("failed_payment_count", 0),
        "prior_attempts_on_this_event": db.count_attempts(ctx.event["event_id"]),
    }


def _tool_classify_cause(args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    error_code = args.get("error_code") or ctx.event.get("error_code")
    cause = cause_analysis.classify_cause(error_code, args.get("error_description"))
    ctx.cause = cause
    db.update_event(ctx.event["event_id"], cause=cause.value, status=EventStatus.analyzing.value,
                     subscription_state_before=ctx.subscription["state"] if ctx.subscription else None)
    audit(event_id=ctx.event["event_id"], merchant_id=merchant_id, stage=AuditStage.analyzed,
          message=f"Agent classified cause: {cause.value}",
          payload={"cause": cause.value, "via": "agent_tool"}, ai_used=True)
    return {
        "cause": cause.value,
        "allowed_actions": [a.value for a in decision_engine.ALLOWED_ACTIONS_BY_CAUSE.get(cause, ())],
    }


def _tool_check_guardrails(args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    try:
        requested = Action(args.get("action"))
    except ValueError:
        requested = None

    attempt_count = db.count_attempts(ctx.event["event_id"])
    decision = decision_engine.decide(
        cause=ctx.cause, event_type=ctx.event["type"],
        subscription_state=ctx.subscription["state"] if ctx.subscription else None,
        customer=ctx.customer, attempt_count=attempt_count,
        high_confidence=ctx.cfg["high_confidence"], low_confidence=ctx.cfg["low_confidence"],
        requested_action=requested,
    )
    last_attempt_at = db.last_attempt_time(ctx.event["event_id"])
    g = guardrails.check_guardrails(
        merchant_id=merchant_id, cfg=ctx.cfg, action=decision.action,
        amount_paise=ctx.event["amount_paise"], attempt_count=attempt_count,
        last_attempt_at=last_attempt_at, event_created_at=ctx.event["created_at"],
    )

    ctx.checked_action = decision.action
    ctx.checked_mechanism = decision.execution_mechanism
    ctx.checked_requires_approval = (
        decision.requires_approval or g.requires_approval or decision.action == Action.escalate_to_human
    )
    ctx.checked_blocked = g.blocked
    ctx.checked_reason = g.reason or decision.reasoning

    db.insert_decision({
        "event_id": ctx.event["event_id"], "merchant_id": merchant_id, "action": decision.action.value,
        "execution_mechanism": decision.execution_mechanism.value if decision.execution_mechanism else None,
        "confidence": decision.confidence, "risk_tier": decision.risk_tier.value,
        "requires_approval": ctx.checked_requires_approval, "reasoning": decision.reasoning,
        "ai_used": True, "policy_version": decision_engine.POLICY_VERSION,
    })
    db.update_event(ctx.event["event_id"], status=EventStatus.action_selected.value)
    audit(event_id=ctx.event["event_id"], merchant_id=merchant_id, stage=AuditStage.decided,
          message=f"Agent proposed '{args.get('action')}'; policy resolved to '{decision.action.value}'",
          payload={"proposed": args.get("action"), "resolved_action": decision.action.value,
                    "confidence": decision.confidence, "proposal_rejected": decision.blocked_invalid_proposal},
          ai_used=True)
    audit(event_id=ctx.event["event_id"], merchant_id=merchant_id, stage=AuditStage.guardrail,
          message="Guardrails blocked this action" if g.blocked else "Guardrails passed",
          payload={"blocked": g.blocked, "code": g.code, "reason": g.reason})

    return {
        "blocked": g.blocked,
        "action": decision.action.value,
        "execution_mechanism": decision.execution_mechanism.value if decision.execution_mechanism else None,
        "confidence": decision.confidence,
        "risk_tier": decision.risk_tier.value,
        "requires_approval": ctx.checked_requires_approval,
        "reason": ctx.checked_reason,
        "proposal_rejected": decision.blocked_invalid_proposal,
    }


def _execute_checked_action(ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    if ctx.checked_action is None:
        return {"error": "check_guardrails must be called before executing an action."}
    if ctx.checked_blocked or ctx.checked_requires_approval:
        return {
            "error": "This action is blocked or requires human approval — call escalate_to_human instead.",
            "blocked": ctx.checked_blocked, "requires_approval": ctx.checked_requires_approval,
        }

    result = execution_service.execute_action(
        merchant_id=merchant_id, event=ctx.event, action=ctx.checked_action,
        mechanism=ctx.checked_mechanism or ExecutionMechanism.reminder_only, customer=ctx.customer,
    )
    new_status = EventStatus.scheduled.value if result.status == "scheduled" else EventStatus.waiting_for_outcome.value
    db.update_event(ctx.event["event_id"], status=new_status)
    audit(event_id=ctx.event["event_id"], merchant_id=merchant_id, stage=AuditStage.executed,
          message=f"Agent executed via {result.execution_mechanism}",
          payload={"recovery_attempt_id": result.recovery_attempt_id, "execution_mode": result.execution_mode},
          ai_used=True)
    ctx.executed = True
    ctx.result_summary = {"status": new_status, "action": ctx.checked_action.value,
                           "recovery_attempt_id": result.recovery_attempt_id}
    return {"executed": True, "recovery_attempt_id": result.recovery_attempt_id, "status": new_status}


def _tool_create_payment_link(args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    return _execute_checked_action(ctx, merchant_id, audit)


def _tool_trigger_retry(args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    return _execute_checked_action(ctx, merchant_id, audit)


def _tool_escalate_to_human(args: dict, ctx: _AgentContext, merchant_id: str, audit: Callable) -> dict:
    reason = args.get("reason") or ctx.checked_reason or "Escalated by agent"
    summary_text = args.get("summary", "")
    approval_id = db.insert_approval({
        "merchant_id": merchant_id, "event_id": ctx.event["event_id"],
        "proposed_action": ctx.checked_action.value if ctx.checked_action else Action.escalate_to_human.value,
        "execution_mechanism": (
            ctx.checked_mechanism.value if (ctx.checked_mechanism and not ctx.checked_blocked) else None
        ),
        "amount_paise": ctx.event["amount_paise"], "reason": reason, "ai_summary": summary_text,
    })
    db.update_event(ctx.event["event_id"], status=EventStatus.approval_pending.value)
    audit(event_id=ctx.event["event_id"], merchant_id=merchant_id, stage=AuditStage.executed,
          message="Agent escalated to human", payload={"approval_id": approval_id, "reason": reason}, ai_used=True)
    ctx.executed = True
    ctx.result_summary = {"status": EventStatus.approval_pending.value, "action": "escalate_to_human",
                           "approval_id": approval_id}
    return {"escalated": True, "approval_id": approval_id}


def _force_escalate(ctx: _AgentContext, merchant_id: str, reason: str, audit: Callable) -> None:
    """The deterministic safety net (doc C10): whatever goes wrong in the
    loop — timeout, tool-call budget, API failure, or a model that just
    stops without deciding — this always resolves to a real, visible
    escalation instead of a silently stuck event."""
    approval_id = db.insert_approval({
        "merchant_id": merchant_id, "event_id": ctx.event["event_id"],
        "proposed_action": ctx.checked_action.value if ctx.checked_action else Action.escalate_to_human.value,
        "execution_mechanism": None,
        "amount_paise": ctx.event["amount_paise"], "reason": reason, "ai_summary": reason,
    })
    db.update_event(ctx.event["event_id"], status=EventStatus.approval_pending.value)
    audit(event_id=ctx.event["event_id"], merchant_id=merchant_id, stage=AuditStage.executed,
          message=f"Force-escalated: {reason}", payload={"approval_id": approval_id}, fallback_triggered=True)
    ctx.executed = True
    ctx.result_summary = {"status": EventStatus.approval_pending.value, "action": "escalate_to_human",
                           "approval_id": approval_id, "forced": True}
