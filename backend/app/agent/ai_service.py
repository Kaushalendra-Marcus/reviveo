"""AI augmentation layer (doc C6) — a wrapper that NEVER raises.

AUDIT NOTE (2026-08-24): this module is NOT imported by the live FastAPI
app (main.py / api/routes.py / webhooks/webhook.py / pipeline/pipeline.py /
pipeline/scheduler.py / services/agent_service.py / services/execution_service.py
never import it). Its only callers are `services/approvals.py` and
`pipeline/executor.py`, which are themselves unreachable dead code (see
their module docstrings) — verified by reading every import in
backend/app/**/*.py. The live equivalent, actually wired into
`pipeline.process_event`, is `services/ai_service.py` (different, richer
return type: `AIResult`, not a bare `tuple | None`). Do not confuse the
two. See AUDIT_REPORT.md §"Agent double-stack" and TODO.md for the
recommended cleanup (delete this whole legacy chain once independently
re-verified with `grep -rn` + a clean `pytest` run).

Every function returns `None` on any failure (including "no key configured"),
so the pipeline always has a deterministic fallback available. Swapping to
Bedrock/Vertex touches only `_client()` — every signature stays identical.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..config import settings

logger = logging.getLogger("reviveo.ai")


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _complete(model: str, system: str, user_content: str, *, max_tokens: int = 300):
    if not settings.ai_configured:
        return None
    started = time.monotonic()
    try:
        resp = (
            _client()
            .messages.create(
                model=model,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=max_tokens,
            )
        )
        text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        latency_ms = int((time.monotonic() - started) * 1000)
        return (text.strip() or None), latency_ms
    except Exception as exc:  # noqa: BLE001 — never raise into the pipeline
        logger.warning("AI call failed (deterministic fallback will fire): %s", exc)
        return None


def generate_reasoning_text(context: dict) -> Optional[tuple[str, int]]:
    """Phrase the audit-trail explanation. Fallback: rule-based reasoning string."""
    return _complete(
        settings.ai_model_fast,
        "You write one-sentence audit-trail explanations for a payments recovery "
        "system. Be factual, reference the given cause/action/amounts, no filler.",
        f"Event: {context}",
    )


def draft_customer_message(context: dict) -> Optional[tuple[str, int]]:
    """Payment-link description / email copy. Fallback: static template."""
    return _complete(
        settings.ai_model_fast,
        "Draft a short, polite payment-recovery message for a customer. Include the "
        "amount and a clear call to action. No markdown, under 60 words.",
        f"Context: {context}",
    )


def classify_unknown_cause(error_code: str, description: str) -> Optional[tuple[str, int]]:
    """Only invoked on Unclassified. Output is advisory: regardless of what this
    returns, the low-confidence auto-escalate rule still gates the action."""
    return _complete(
        settings.ai_model_fast,
        "Classify the payment failure into exactly one of: card_expired, "
        "insufficient_funds, payment_timeout, bank_declined, checkout_abandoned. "
        "Reply with the label only.",
        f"error_code={error_code}\ndescription={description}",
        max_tokens=10,
    )


def summarize_for_approval(context: dict) -> Optional[tuple[str, int]]:
    """Populates pending_approvals.ai_summary for the ApprovalModal."""
    return _complete(
        settings.ai_model_summary,
        "Summarize for a human reviewer deciding whether to approve a recovery "
        "action. 3 sentences max: cause, proposed action + amount, risk.",
        f"Case: {context}",
    )
