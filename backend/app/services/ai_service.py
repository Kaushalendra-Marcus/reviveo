"""AI-augmentation layer (doc C6). `call_claude()` and everything built on it
NEVER raises — every function here returns a best-effort result and falls
back to a deterministic default on any failure (missing key, network error,
API error, timeout, empty response), so the pipeline always has something
correct to work with. Every call reports ai_used/ai_model/ai_latency_ms/
fallback_triggered so AI usage itself is auditable (doc C7) — including the
case where a call failed and the fallback fired, which is worth being able
to show honestly.

This module is swappable to AWS Bedrock or Google Vertex AI by changing only
the client construction in `_get_client()` (doc C2); every function's
signature and behavior stays identical.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from ..config import settings
from ..logging_config import get_logger

logger = get_logger("reviveo.ai_service")

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def get_raw_client():
    """Public accessor for the agentic tool-use loop (`agent_service.py`),
    which needs the raw SDK client for multi-turn tool_use conversations
    that don't fit `call_claude()`'s single-completion shape. Keeping
    construction in this one function is what keeps the provider swap
    (doc C2 — Bedrock/Vertex) a one-place change."""
    return _get_client()


@dataclass(frozen=True)
class AIResult:
    text: Optional[str]
    used: bool
    model: Optional[str]
    latency_ms: Optional[int]
    fallback_triggered: bool


def call_claude(*, system: str, user: str, model: str, max_tokens: int = 300) -> AIResult:
    """The single call-site for the Claude API. Never raises."""
    if not (settings.is_live and settings.ai_configured):
        return AIResult(text=None, used=False, model=None, latency_ms=None, fallback_triggered=True)

    start = time.monotonic()
    try:
        client = _get_client()
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        text = "\n".join(t for t in text_parts if t).strip() or None
        if text is None:
            return AIResult(text=None, used=True, model=model, latency_ms=latency_ms, fallback_triggered=True)
        return AIResult(text=text, used=True, model=model, latency_ms=latency_ms, fallback_triggered=False)
    except Exception as exc:  # noqa: BLE001 — deliberate: this wrapper must never raise
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning("claude call failed — falling back", extra={"context": {"error": str(exc)}})
        return AIResult(text=None, used=False, model=model, latency_ms=latency_ms, fallback_triggered=True)


def _with_fallback(result: AIResult, fallback: str) -> AIResult:
    if result.text is not None:
        return result
    return AIResult(text=fallback, used=result.used, model=result.model,
                     latency_ms=result.latency_ms, fallback_triggered=True)


def generate_reasoning_text(*, cause: str, action: str, confidence: float, fallback: str) -> AIResult:
    """Phrases the audit-trail explanation; falls back to the rule-based
    reasoning string on any failure."""
    result = call_claude(
        system=(
            "You are Reviveo, an AI revenue-recovery agent. Explain a recovery "
            "decision in one plain sentence for a merchant's audit log. Be factual "
            "and concise — do not invent numbers or customer details beyond what "
            "is given."
        ),
        user=f"Cause: {cause}. Chosen action: {action}. Confidence: {confidence:.2f}. "
             f"Write one sentence explaining this decision.",
        model=settings.ai_model_fast,
    )
    return _with_fallback(result, fallback)


def draft_customer_message(
    *, customer_name: str, amount_paise: int, cause: str, action: str,
    link_url: Optional[str], fallback: str,
) -> AIResult:
    """Payment-link description / reminder copy; falls back to a static
    template on failure."""
    rupees = amount_paise / 100
    prompt = (
        f"Write a short, friendly payment-recovery message to {customer_name} for a "
        f"failed payment of Rs. {rupees:,.2f}. Reason: {cause}. "
        + (f"Include this payment link: {link_url}. " if link_url else "")
        + "Keep it under 60 words, no subject line, no sign-off placeholders."
    )
    result = call_claude(
        system=(
            "You are drafting a short customer-facing payment-recovery message for "
            "Reviveo. Be warm, brief, and factual. Never invent amounts, dates, or "
            "links beyond what is given in the prompt."
        ),
        user=prompt, model=settings.ai_model_fast,
    )
    return _with_fallback(result, fallback)


def classify_unknown_cause(*, error_code: Optional[str], error_description: Optional[str]) -> AIResult:
    """Only invoked when `classify_cause()` falls through to `unclassified`.
    This NEVER bypasses the confidence policy — the low-confidence
    auto-escalate rule still applies regardless of what this returns
    (doc C6); it only enriches the audit trail with a best-effort label.
    """
    result = call_claude(
        system=(
            "You classify a Razorpay payment failure into exactly one label: "
            "card_expired, insufficient_funds, payment_timeout, bank_declined, "
            "checkout_abandoned, or unclassified. Reply with only the label, "
            "nothing else."
        ),
        user=f"error_code={error_code!r} error_description={error_description!r}",
        model=settings.ai_model_fast, max_tokens=20,
    )
    return result


def summarize_for_approval(
    *, event: dict, decision: dict, guardrail_reason: Optional[str], fallback: str,
) -> AIResult:
    """Populates `pending_approvals.ai_summary`. Uses the larger model — this
    is low-volume, human-facing text (doc C2)."""
    prompt = (
        f"Summarize this pending recovery approval for a merchant in at most 2 "
        f"sentences. Event type: {event.get('type')}. Cause: {event.get('cause')}. "
        f"Amount (paise): {event.get('amount_paise')}. Proposed action: "
        f"{decision.get('action')}. Confidence: {decision.get('confidence')}. "
        + (f"Guardrail note: {guardrail_reason}. " if guardrail_reason else "")
        + "Be factual, do not invent details not given above."
    )
    result = call_claude(
        system=(
            "You summarize a pending payment-recovery approval for a merchant "
            "reviewing it in a dashboard. Be concise, factual, and neutral."
        ),
        user=prompt, model=settings.ai_model_summary,
    )
    return _with_fallback(result, fallback)
