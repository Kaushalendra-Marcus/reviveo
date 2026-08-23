"""Razorpay execution service — synthetic + live behind one interface.

Every money-moving call funnels through here (doc §3.8). `dry_run` mode never
touches Razorpay and returns deterministic synthetic references; `live_call`
uses the test-mode SDK. Webhook signature verification follows the documented
HMAC-SHA256 scheme.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Optional

from ..config import settings
from ..enums import ExecutionMode

logger = logging.getLogger("reviveo.razorpay")


@dataclass(frozen=True)
class ExecutionOutcome:
    ok: bool
    mode: ExecutionMode
    razorpay_ref: Optional[str] = None
    error: Optional[str] = None


def synthetic_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _client():
    import razorpay  # imported lazily so synthetic mode needs no SDK secrets

    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_payment_link(
    *,
    amount_paise: int,
    customer_email: str,
    customer_name: str,
    description: str,
    reference_id: str,
    notes: dict,
    execution_mode: ExecutionMode,
) -> ExecutionOutcome:
    """Payment Link carrying reference_id + notes correlation keys (doc §3.7)."""
    if execution_mode is ExecutionMode.dry_run or not (
        settings.is_live and settings.razorpay_configured
    ):
        return ExecutionOutcome(
            ok=True,
            mode=ExecutionMode.dry_run,
            razorpay_ref=synthetic_id("plink_dry", reference_id),
        )
    try:
        link = _client().payment_link.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "accept_partial": False,
                "reference_id": reference_id,
                "description": description[:255],
                "customer": {"name": customer_name, "email": customer_email},
                "notify": {"sms": False, "email": False},
                "notes": notes,
            }
        )
        return ExecutionOutcome(ok=True, mode=ExecutionMode.live_call, razorpay_ref=link["id"])
    except Exception as exc:  # noqa: BLE001 — any SDK failure becomes an outcome
        logger.error("payment_link.create failed: %s", exc)
        return ExecutionOutcome(ok=False, mode=ExecutionMode.live_call, error=str(exc))


def manual_charge(*, execution_mode: ExecutionMode, reference_id: str) -> ExecutionOutcome:
    """Supported-manual-charge path for halted subscriptions (doc §3.3).

    Honest scope note: the live implementation requires merchant-specific
    invoice configuration, so live mode reports it as unsupported rather than
    pretending a generic same-card retry works."""
    if execution_mode is ExecutionMode.dry_run or not settings.is_live:
        return ExecutionOutcome(
            ok=True,
            mode=ExecutionMode.dry_run,
            razorpay_ref=synthetic_id("ch_dry", reference_id),
        )
    return ExecutionOutcome(
        ok=False,
        mode=ExecutionMode.live_call,
        error="manual_charge not configured for this merchant's live account",
    )


def monitor_native(subscription_id: Optional[str]) -> ExecutionOutcome:
    """Record-only path: Razorpay's native retry engine keeps running (§3.3)."""
    ref = subscription_id or "unknown_subscription"
    return ExecutionOutcome(ok=True, mode=ExecutionMode.dry_run, razorpay_ref=ref)


def send_reminder(customer_email: Optional[str]) -> ExecutionOutcome:
    """Reminder-only contact. Actual delivery (email provider) is out of MVP
    scope; the contact is counted and audited either way."""
    return ExecutionOutcome(ok=True, mode=ExecutionMode.dry_run)


def verify_webhook_signature(body: bytes, signature: Optional[str]) -> bool:
    """Documented HMAC-SHA256 verification of X-Razorpay-Signature.

    With no webhook secret configured (synthetic demo mode) verification
    passes through explicitly rather than silently.
    """
    if not settings.razorpay_webhook_secret:
        return not settings.is_live
    if not signature:
        return False
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
