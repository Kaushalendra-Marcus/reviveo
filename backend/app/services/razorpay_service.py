"""Razorpay integration — every Razorpay-facing call lives here (doc A0
`execution.py`'s Razorpay calls, doc C2 "swappable" provider boundary).
Swapping SDKs, or going from test to production keys, only ever touches this
module.

Two execution modes run throughout the whole pipeline: `synthetic` (no
network calls — a deterministic fake response so the entire app runs with
zero secrets) and `live` (real Razorpay **test-mode** API calls, once
RUN_MODE=live and RAZORPAY_KEY_ID/SECRET are set). Which mode produced a
given attempt is always recorded on it (`execution_mode`), never hidden
(doc §3.14) — dry_run vs live_call is a fact about the run, not a detail to
paper over.

Reference: https://razorpay.com/docs/api/payments/payment-links/create-standard/
           https://razorpay.com/docs/webhooks/validate-test/
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import razorpay
from razorpay.errors import SignatureVerificationError

from ..config import settings
from ..logging_config import get_logger

logger = get_logger("reviveo.razorpay_service")

_client: Optional["razorpay.Client"] = None


def _get_client() -> "razorpay.Client":
    global _client
    if _client is None:
        _client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    return _client


@dataclass(frozen=True)
class PaymentLinkResult:
    razorpay_ref: str       # Payment Link id (plink_...)
    reference_id: str       # our own unique reference_id sent to Razorpay
    short_url: Optional[str]
    live: bool


def create_payment_link(
    *,
    amount_paise: int,
    customer_name: str,
    customer_email: Optional[str],
    customer_phone: Optional[str],
    description: str,
    event_id: str,
    recovery_attempt_id: str,
    attempt_number: int,
) -> PaymentLinkResult:
    """Creates a Razorpay Payment Link (doc §3.7). `reference_id` is the
    primary outbound correlation key, and `notes` carries the full chain
    (event_id, recovery_attempt_id, attempt_number) so the outcome webhook
    can always find its way back to the right event — never correlate by
    customer email, customer id, or amount alone.
    """
    reference_id = f"rvo_{recovery_attempt_id}"[:40]  # Razorpay's documented 40-char limit
    notes = {
        "event_id": event_id,
        "recovery_attempt_id": recovery_attempt_id,
        "attempt_number": str(attempt_number),
        "source": "reviveo",
    }

    if not (settings.is_live and settings.razorpay_configured):
        fake_id = f"plink_synthetic_{uuid.uuid4().hex[:14]}"
        logger.info("synthetic payment link created", extra={"context": {
            "recovery_attempt_id": recovery_attempt_id, "amount_paise": amount_paise,
        }})
        return PaymentLinkResult(
            razorpay_ref=fake_id, reference_id=reference_id,
            short_url=f"https://rzp.io/synthetic/{fake_id}", live=False,
        )

    client = _get_client()
    customer: dict = {"name": customer_name}
    if customer_email:
        customer["email"] = customer_email
    if customer_phone:
        customer["contact"] = customer_phone

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "description": description[:2048],
        "reference_id": reference_id,
        "notes": notes,
        "customer": customer,
        "notify": {"sms": bool(customer_phone), "email": bool(customer_email)},
        "reminder_enable": True,
    }
    link = client.payment_link.create(data=payload)
    logger.info("live payment link created", extra={"context": {
        "recovery_attempt_id": recovery_attempt_id, "razorpay_ref": link.get("id"),
    }})
    return PaymentLinkResult(
        razorpay_ref=link["id"], reference_id=reference_id,
        short_url=link.get("short_url"), live=True,
    )


def fetch_payment_link(razorpay_ref: str) -> Optional[dict]:
    """Fetches current Payment Link state — used by the scheduler when
    revalidating a scheduled action (doc §3.11). Synthetic refs are not
    fetchable and return None."""
    if razorpay_ref.startswith("plink_synthetic_") or not (settings.is_live and settings.razorpay_configured):
        return None
    try:
        return _get_client().payment_link.fetch(razorpay_ref)
    except Exception as exc:  # noqa: BLE001 — fetch failures degrade to "unknown", never crash
        logger.warning("payment link fetch failed", extra={"context": {"error": str(exc)}})
        return None


def verify_webhook_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """HMAC-SHA256 verification over the RAW request body (doc §3.6):
    verify signature -> validate payload -> deduplicate -> persist -> process
    -> mark. When no webhook secret is configured (synthetic/dev), signature
    checking is skipped and always succeeds; this path is never reachable
    once a real secret is set, since then this function is required to pass.
    """
    if not settings.razorpay_webhook_secret:
        return True
    if not signature:
        return False
    try:
        _get_client().utility.verify_webhook_signature(
            raw_body.decode("utf-8"), signature, settings.razorpay_webhook_secret,
        )
        return True
    except SignatureVerificationError:
        return False
    except Exception as exc:  # noqa: BLE001 — malformed body etc. must not crash the endpoint
        logger.warning("webhook signature verification error", extra={"context": {"error": str(exc)}})
        return False
