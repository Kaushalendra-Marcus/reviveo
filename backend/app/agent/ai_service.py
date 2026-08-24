"""AI augmentation layer (doc C6) — wrapper that NEVER raises.

Live implementation lives in `services/ai_service.py` (AIResult dataclass,
provider-swappable `_get_client`, never-raises `call_claude`). This module
is the Part C reference path (`agent/ai_service.py` per implementation.txt
C11) and is now wired as a compatibility shim: it re-exports the live
`services/ai_service` API and also preserves the legacy `context: dict →
tuple[str, int] | None` signatures used by older callers (`pipeline/
executor.py` legacy) so those callers continue to work via this shim.

Every function returns `None` on any failure (including "no key configured"),
so the pipeline always has a deterministic fallback. Swapping to Bedrock/
Vertex touches only `services/ai_service._get_client()` — every signature
here stays identical.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import settings
from ..services import ai_service as _live

logger = logging.getLogger("reviveo.ai")

# Re-export live canonical symbols for new callers (Part C).
AIResult = _live.AIResult
call_claude = _live.call_claude
_get_client = _live.get_raw_client  # alias for legacy _client() name


def _client():
    """Legacy alias for `_get_client` — kept for `agent/*` callers that
    imported `_client` directly before the consolidation."""
    return _live.get_raw_client()


def _complete(model: str, system: str, user_content: str, *, max_tokens: int = 300):
    """Legacy helper — delegates to live `call_claude` and converts
    `AIResult` → `(text, latency)` tuple for backward compatibility."""
    result = _live.call_claude(system=system, user=user_content, model=model, max_tokens=max_tokens)
    if result.text is None:
        return None
    return result.text, result.latency_ms or 0


def generate_reasoning_text(context: dict) -> Optional[tuple[str, int]]:
    """Phrase the audit-trail explanation. Fallback: rule-based reasoning string.

    Legacy dict-context signature (agent/*) → delegates to live AIResult API
    and converts to tuple for compatibility with `pipeline/executor.py`.
    """
    # New callers should prefer `services.ai_service.generate_reasoning_text`
    # with explicit `cause/action/confidence/fallback` kwargs.
    # This shim preserves the old `context: dict` shape.
    if not context:
        return None
    cause = str(context.get("cause", context.get("error_code", "")))
    action = str(context.get("action", ""))
    confidence = float(context.get("confidence", 0.5))
    fallback = str(context.get("reasoning", context.get("fallback", "")))
    result = _live.generate_reasoning_text(cause=cause, action=action, confidence=confidence, fallback=fallback)
    if result.text is None:
        return None
    return result.text, result.latency_ms or 0


def draft_customer_message(context: dict) -> Optional[tuple[str, int]]:
    """Payment-link description / email copy. Fallback: static template.

    Legacy dict-context signature → delegates to live `draft_customer_message`
    and converts AIResult → tuple.
    """
    customer_name = str(context.get("customer_name", context.get("name", "Customer")))
    amount_paise = int(context.get("amount_paise", context.get("amount_rupees", 0) * 100) if "amount_paise" not in context and "amount_rupees" in context else context.get("amount_paise", 0))
    # If amount was passed as rupees float, handle both
    if isinstance(context.get("amount_rupees"), float) and "amount_paise" not in context:
        amount_paise = int(context["amount_rupees"] * 100)
    cause = str(context.get("cause", ""))
    action = str(context.get("action", "send_payment_update_link"))
    link_url = context.get("link_url")
    fallback = str(context.get("fallback", "Please complete your payment securely."))
    result = _live.draft_customer_message(
        customer_name=customer_name, amount_paise=amount_paise, cause=cause,
        action=action, link_url=link_url, fallback=fallback,
    )
    if result.text is None:
        return None
    return result.text, result.latency_ms or 0


def classify_unknown_cause(error_code: str, description: str) -> Optional[tuple[str, int]]:
    """Only invoked on Unclassified. Output is advisory: regardless of what this
    returns, the low-confidence auto-escalate rule still gates the action."""
    result = _live.classify_unknown_cause(error_code=error_code, error_description=description)
    if result.text is None:
        return None
    return result.text, result.latency_ms or 0


def summarize_for_approval(context: dict) -> Optional[tuple[str, int]]:
    """Populates pending_approvals.ai_summary for the ApprovalModal.

    Legacy dict-context signature → delegates to live `summarize_for_approval`.
    """
    # Live expects `event, decision, guardrail_reason, fallback` kwargs.
    # This shim accepts the old `context: dict` and adapts.
    event = context if "type" in context else {"type": context.get("type", ""), "cause": context.get("cause")}
    decision = {"action": context.get("action", ""), "confidence": context.get("confidence", 0.5)}
    guardrail_reason = context.get("guardrail_reason") or context.get("reason")
    fallback = str(context.get("fallback", context.get("summary", "Requires human review.")))
    result = _live.summarize_for_approval(event=event, decision=decision, guardrail_reason=guardrail_reason, fallback=fallback)
    if result.text is None:
        return None
    return result.text, result.latency_ms or 0
