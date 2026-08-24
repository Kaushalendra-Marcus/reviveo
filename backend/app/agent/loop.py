"""Native Claude tool-use orchestration loop (doc Part C).

AUDIT NOTE (2026-08-24): NOT wired into the live app — nothing imports
`run_agent` from this module (verified: `pipeline.py` calls
`services/agent_service.run_agent_for_event` instead, which is the live
agentic implementation). Kept for reference only. See AUDIT_REPORT.md and
TODO.md for the recommended cleanup.

No agent framework — the tool count is small and the loop short (C1). Every
step is bounded by runtime limits (§3.10) and every step's trace is returned
so the pipeline can write AI-usage fields into the audit trail (C7). Any
failure returns None → the deterministic pipeline takes over unchanged.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from ..config import settings

logger = logging.getLogger("reviveo.agent.loop")


def run_agent(event: dict, *, cfg: dict | None = None) -> Optional[dict]:
    """Returns {"decision": ..., "meta": ..., "trace": [...]} or None.

    None means "no usable agent result" — callers must fall back to the
    deterministic decision engine."""
    if not settings.ai_configured:
        return None

    import anthropic

    from .tools import TOOL_SCHEMAS, _SYSTEM_PROMPT, execute_tool

    cfg = cfg or {}
    started = time.monotonic()
    ctx: dict = {"chosen": None, "trace": []}
    meta: dict = {"ai_used": True, "ai_model": settings.ai_model_fast}

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        brief = json.dumps({
            "event_id": event["event_id"],
            "type": event["type"],
            "cause": event.get("cause"),
            "error_code": event.get("error_code"),
            "amount_paise": event["amount_paise"],
            "subscription_state": event.get("subscription_state_before"),
            "customer_id": event.get("customer_id"),
        })
        messages: list[dict] = [{"role": "user",
                                 "content": f"Failing payment event:\n{brief}\n\n"
                                            "Choose and commit to exactly one recovery action."}]

        while ctx["chosen"] is None:
            if ctx_steps(ctx) >= settings.max_agent_steps_per_event:
                meta["fallback_triggered"] = True
                meta["stop_reason"] = "max_agent_steps"
                break
            if time.monotonic() - started > settings.max_agent_wall_time_seconds:
                meta["fallback_triggered"] = True
                meta["stop_reason"] = "wall_time_limit"
                break

            resp = client.messages.create(
                model=settings.ai_model_fast,
                system=_SYSTEM_PROMPT,
                max_tokens=600,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not tool_uses:
                text = "\n".join(getattr(b, "text", "") for b in resp.content).strip()
                meta["stop_reason"] = "final_text"
                ctx["final_text"] = text
                break

            results = []
            for tu in tool_uses:
                if tool_calls(ctx) >= settings.max_tool_calls_per_event:
                    out = {"blocked": True, "blocked_reasons": ["tool-call limit reached"]}
                else:
                    out = execute_tool(tu.name, dict(tu.input or {}), event, cfg, ctx)
                bump_tool_calls(ctx)
                ctx["trace"].append({"tool": tu.name, "input": tu.input, "result": out})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(out),
                })
            messages.append({"role": "user", "content": results})
        else:
            meta["stop_reason"] = "committed"

    except Exception as exc:  # noqa: BLE001 — never raise into the pipeline
        logger.warning("agent loop failed; deterministic fallback will fire: %s", exc)
        return {
            "decision": None,
            "meta": {"ai_used": True, "ai_model": settings.ai_model_fast,
                     "ai_latency_ms": int((time.monotonic() - started) * 1000),
                     "fallback_triggered": True},
            "trace": ctx.get("trace", []),
        }

    meta["ai_latency_ms"] = int((time.monotonic() - started) * 1000)
    if ctx.get("chosen") is None:
        # Agent ran but never committed — deterministic engine decides instead.
        meta.setdefault("fallback_triggered", True)
        return {"decision": None, "meta": meta, "trace": ctx.get("trace", [])}
    return {"decision": ctx["chosen"], "meta": meta, "trace": ctx["trace"]}


def ctx_steps(ctx: dict) -> int:
    return ctx.setdefault("steps", 0)


def tool_calls(ctx: dict) -> int:
    return len(ctx.get("trace", []))


def bump_tool_calls(ctx: dict) -> None:
    ctx["steps"] = ctx_steps(ctx) + 1
