"""Agent tool layer (doc Part C).

AUDIT NOTE (2026-08-24): NOT wired into the live app. `run_agent_for_event`
in `services/agent_service.py` — the module `pipeline.process_event` actually
calls when `use_ai=True` — has its own independent tool implementation and
never imports this file. This module is only reachable via `agent/loop.py`
(itself unreferenced by anything live) and `services/approvals.py` (also
dead — see that module's docstring). Its previously-broken import
(`ACTION_MECHANISM`/`CAUSE_CONFIDENCE` from decision_engine) was fixed via
public aliases added there, but that only stops an ImportError — it does
not make this the live implementation. See AUDIT_REPORT.md and TODO.md.

Six bounded tools back onto existing deterministic implementations. Per C4,
guardrail enforcement lives INSIDE the tools' Python code — the model cannot
propose its way past `check_guardrails`, and mutating tools refuse to record a
choice the guardrails blocked. Per §3.8 the model never calls Razorpay
directly and never invents amounts: the final API operation is performed by
execution services after every policy check passes (same code path as the
deterministic pipeline).
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .. import db
from ..config import settings
from ..domain.cause_analysis import classify_cause
from ..domain.decision_engine import ACTION_MECHANISM, ACTION_RISK, CAUSE_CONFIDENCE
from ..enums import Action
from ..logging_config import get_logger
from ..services import approvals as approvals_service

logger = get_logger("reviveo.agent.tools")

_SYSTEM_PROMPT = """You are Reviveo's recovery agent for failed subscription payments.
You choose ONE recovery action per failed payment from this whitelist:
send_reminder, smart_retry_24h, immediate_retry, retry_and_notify,
send_payment_update_link, monitor_native_retry, escalate_to_human.

Rules you cannot break (enforced by tools, not by your judgment):
- Unknown/unclassified causes permit ONLY escalate_to_human.
- Guardrails cap retries, cooldowns, daily value/contact limits and the recovery window.
- You never move money directly; you only select the action. Execution services
  perform the final Razorpay operation after all checks pass.

Available context about the failing payment is provided. Inspect it, optionally
check guardrails, then commit to exactly one action tool call. Prefer the least
risky effective action; escalate when unsure."""


TOOL_SCHEMAS: list[dict] = [
    {
        "name": "get_customer_history",
        "description": "Look up the customer's profile, lifetime recovered value and prior failure count.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "classify_cause",
        "description": "Deterministically map a Razorpay error reason/code onto the internal cause vocabulary.",
        "input_schema": {
            "type": "object",
            "properties": {"error_code": {"type": "string"}},
            "required": ["error_code"],
        },
    },
    {
        "name": "check_guardrails",
        "description": "Run the deterministic guardrail checks for a candidate action. Enforcement, not advice.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": [a.value for a in Action]},
                "amount_paise": {"type": "integer"},
            },
            "required": ["action", "amount_paise"],
        },
    },
    {
        "name": "create_payment_link",
        "description": "Select 'send a payment/update link to the customer' as the recovery action "
                       "(checkout card-update or payment link). Amount and recipient are taken from "
                       "the event server-side — you cannot change them.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "trigger_retry",
        "description": "Select a retry-style action: immediate_retry (now), retry_and_notify, or smart_retry_24h (scheduled).",
        "input_schema": {
            "type": "object",
            "properties": {
                "variant": {"type": "string",
                            "enum": ["immediate_retry", "retry_and_notify", "smart_retry_24h"]},
                "reason": {"type": "string"},
            },
            "required": ["variant", "reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Route this case to a human reviewer. Required for unclassified causes.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

_MUTATING_TOOLS = {"create_payment_link", "trigger_retry", "escalate_to_human"}

_ACTION_FOR_TOOL = {
    "create_payment_link": None,  # resolved from cause below
    "trigger_retry": None,
}


def _confidence_band(value: float, cfg: dict) -> str:
    if value >= cfg["high_confidence"]:
        return "high"
    if value >= cfg["low_confidence"]:
        return "medium"
    return "low"


def _build_decision(action: Action, cause_value: str, reasoning: str, cfg: dict) -> dict:
    confidence = CAUSE_CONFIDENCE.get(cause_value, 0.5)
    risk = ACTION_RISK[action].value
    mechanism = ACTION_MECHANISM[action]
    mechanism_val = mechanism.value if mechanism else None
    band = _confidence_band(confidence, cfg)
    requires_approval = band == "medium" and risk != "low"
    return {
        "action": action.value,
        "mechanism": mechanism_val,
        "confidence": round(confidence, 4),
        "risk_tier": risk,
        "requires_approval": requires_approval,
        "reasoning": reasoning,
        "cause": cause_value,
        "policy_version": f"{settings.ai_model_fast}-agentic",
        "ai_used": True,
    }


def execute_tool(
    name: str,
    tool_input: dict[str, Any],
    event: dict,
    cfg: Optional[dict],
    ctx: dict,
) -> dict:
    """Run one tool call against real state. Returns a JSON-serializable dict."""
    cfg = cfg or db.get_guardrail_config(event["merchant_id"])
    merchant_id = event["merchant_id"]

    if name == "get_customer_history":
        customer = db.get_customer(merchant_id, tool_input.get("customer_id") or "")
        if customer is None:
            return {"error": f"customer '{tool_input.get('customer_id')}' not found"}
        return {k: customer[k] for k in
                ("id", "name", "email", "total_recovered_paise", "failed_payment_count")}

    if name == "classify_cause":
        cause = classify_cause(tool_input.get("error_code"))
        return {"cause": cause.value}

    if name == "check_guardrails":
        from ..guardrails.guardrails import evaluate

        try:
            action = Action(tool_input["action"])
        except ValueError:
            return {"blocked": True, "blocked_reasons": [f"'{tool_input['action']}' is not a permitted action"]}
        result = evaluate(merchant_id, event, action,
                          int(tool_input.get("amount_paise", event["amount_paise"])), cfg=cfg)
        return result.as_payload()

    if name == "create_payment_link":
        if ctx.get("chosen") is not None:
            return {"blocked": True, "blocked_reasons": ["an action was already committed"]}
        from ..domain.decision_engine import ALLOWED_ACTIONS_BY_CAUSE
        from ..enums import Cause

        cause = Cause(event.get("cause") or "unclassified")
        action = Action.send_payment_update_link
        if action not in ALLOWED_ACTIONS_BY_CAUSE.get(cause, ()):
            return {"blocked": True,
                    "blocked_reasons": [f"'{action.value}' is not permitted for cause '{cause.value}'"]}
        from ..guardrails.guardrails import evaluate

        guard = evaluate(merchant_id, event, action, event["amount_paise"], cfg=cfg)
        if not guard.passed:
            return {"blocked": True, "blocked_reasons": guard.blocked_reasons}
        ctx["chosen"] = _build_decision(action, cause.value,
                                        f"Agent selected '{action.value}': {tool_input.get('reason', '')}",
                                        cfg)
        return {"committed": action.value,
                "note": "Execution will be performed by the shared execution service after final checks."}

    if name == "trigger_retry":
        if ctx.get("chosen") is not None:
            return {"blocked": True, "blocked_reasons": ["an action was already committed"]}
        variant = tool_input.get("variant", "smart_retry_24h")
        try:
            action = Action(variant)
        except ValueError:
            return {"blocked": True, "blocked_reasons": [f"unknown retry variant '{variant}'"]}
        if action not in (Action.immediate_retry, Action.retry_and_notify, Action.smart_retry_24h):
            return {"blocked": True, "blocked_reasons": [f"'{variant}' is not a retry action"]}
        from ..domain.decision_engine import ALLOWED_ACTIONS_BY_CAUSE
        from ..enums import Cause

        cause = Cause(event.get("cause") or "unclassified")
        if action not in ALLOWED_ACTIONS_BY_CAUSE.get(cause, ()):
            return {"blocked": True,
                    "blocked_reasons": [f"'{action.value}' is not permitted for cause '{cause.value}'"]}
        from ..guardrails.guardrails import evaluate

        guard = evaluate(merchant_id, event, action, event["amount_paise"], cfg=cfg)
        if not guard.passed:
            return {"blocked": True, "blocked_reasons": guard.blocked_reasons}
        ctx["chosen"] = _build_decision(action, cause.value,
                                        f"Agent selected '{action.value}': {tool_input.get('reason', '')}",
                                        cfg)
        return {"committed": action.value,
                "note": "Execution will be performed by the shared execution service after final checks."}

    if name == "escalate_to_human":
        reason = tool_input.get("reason", "")
        summary = tool_input.get("summary")
        approval_id = approvals_service.enqueue(
            merchant_id, event,
            {"action": Action.escalate_to_human.value, "mechanism": None,
             "cause": event.get("cause"), "reasoning": reason},
            reason=reason or "agent escalation",
        )
        if summary:
            db.execute("UPDATE pending_approvals SET ai_summary=? WHERE id=?",
                       (str(summary)[:2000], approval_id))
        ctx["chosen"] = _build_decision(Action.escalate_to_human,
                                        event.get("cause") or "unclassified",
                                        f"Agent escalated: {reason}", cfg)
        return {"escalated": True, "approval_id": approval_id}

    return {"error": f"unknown tool '{name}'"}
