"""Customer notification service (Email provider abstraction + AI message dispatch).

Responsibilities:
- Provider abstraction for transactional emails (Resend / Simulated).
- Customer message generation via AI with deterministic fallback.
- Strict idempotency (one notification per recovery attempt + channel).
- Safe customer data handling (gracefully skip if email missing).
- Audit trail recording and persistence in `notifications` table.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .. import db
from ..config import settings
from ..enums import AuditStage
from ..logging_config import get_logger
from . import ai_service

logger = get_logger("reviveo.notification_service")


@dataclass(frozen=True)
class NotificationResult:
    notification_id: str
    status: str  # 'sent' | 'simulated' | 'failed' | 'skipped'
    recipient: Optional[str]
    subject: Optional[str]
    body: Optional[str]
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    ai_generated: bool = False
    ai_model: Optional[str] = None
    ai_latency_ms: Optional[int] = None


class EmailProvider:
    """Base abstract provider for transactional email sending."""
    def send_email(self, *, to: str, subject: str, text_body: str, html_body: str, from_email: str) -> tuple[bool, Optional[str], Optional[str]]:
        raise NotImplementedError


class ResendEmailProvider(EmailProvider):
    """Resend transactional email provider implementation."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    def send_email(self, *, to: str, subject: str, text_body: str, html_body: str, from_email: str) -> tuple[bool, Optional[str], Optional[str]]:
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Reviveo/1.0",
        }
        payload = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                message_id = body.get("id")
                return True, message_id, None
        except urllib.error.HTTPError as exc:
            err_text = exc.read().decode("utf-8") if exc.fp else str(exc)
            logger.warning("resend email sending failed", extra={"context": {"code": exc.code, "error": err_text}})
            return False, None, f"Resend API error ({exc.code}): {err_text}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("resend email network exception", extra={"context": {"error": str(exc)}})
            return False, None, f"Email sending exception: {exc}"


def send_customer_notification(
    *,
    merchant_id: str,
    event: dict,
    recovery_attempt: dict,
    customer: Optional[dict],
    short_url: Optional[str] = None,
) -> NotificationResult:
    """Dispatches a customer recovery notification via Email.

    Enforces:
    1. Idempotency: Returns existing notification if already sent for this attempt.
    2. Graceful missing email handling: Records 'skipped' if email is missing.
    3. AI message drafting with safe deterministic fallback.
    4. Provider sending (Resend in live/configured mode, simulated otherwise).
    5. DB persistence and audit trail logging.
    """
    attempt_id = recovery_attempt["recovery_attempt_id"]
    event_id = event["event_id"]

    # 1. Idempotency check
    existing = db.get_notification_by_attempt(attempt_id, channel="email")
    if existing:
        logger.info("notification already recorded for attempt — skipping duplicate", extra={"context": {
            "recovery_attempt_id": attempt_id, "notification_id": existing["notification_id"]
        }})
        return NotificationResult(
            notification_id=existing["notification_id"],
            status=existing["status"],
            recipient=existing["recipient"],
            subject=existing["subject"],
            body=existing["body"],
            provider_message_id=existing.get("provider_message_id"),
            error=existing.get("error"),
            ai_generated=bool(existing.get("ai_generated")),
            ai_model=existing.get("ai_model"),
            ai_latency_ms=existing.get("ai_latency_ms"),
        )

    recipient = (customer or {}).get("email")

    # 2. Missing customer email check
    if not recipient:
        notification_id = f"notif_{uuid.uuid4().hex[:16]}"
        error_msg = "No customer email address on file"
        db.insert_notification({
            "notification_id": notification_id,
            "merchant_id": merchant_id,
            "event_id": event_id,
            "recovery_attempt_id": attempt_id,
            "channel": "email",
            "recipient": "none",
            "subject": None,
            "body": "",
            "status": "skipped",
            "provider_message_id": None,
            "error": error_msg,
            "ai_generated": False,
        })
        logger.info("email notification skipped — no recipient", extra={"context": {"event_id": event_id}})
        return NotificationResult(
            notification_id=notification_id,
            status="skipped",
            recipient=None,
            subject=None,
            body=None,
            error=error_msg,
        )

    # 3. Message preparation & AI generation
    customer_name = (customer or {}).get("name") or "Customer"
    amount_paise = event.get("amount_paise", 0)
    rupees = amount_paise / 100
    cause = event.get("cause") or "payment_failed"
    link_url = short_url or (recovery_attempt.get("notes") or {}).get("short_url")

    subject = f"Complete your payment of ₹{rupees:,.2f}"
    fallback_body = (
        f"Hi {customer_name},\n\n"
        f"Your payment of ₹{rupees:,.2f} could not be completed.\n\n"
        f"You can securely retry your payment using the link below:\n"
        f"{link_url or 'Please check your account portal.'}\n\n"
        f"Thank you,\nReviveo Team"
    )

    ai_result = ai_service.draft_customer_message(
        customer_name=customer_name,
        amount_paise=amount_paise,
        cause=cause,
        action=recovery_attempt.get("action", ""),
        link_url=link_url,
        fallback=fallback_body,
    )
    body = ai_result.text or fallback_body

    # Format HTML email body
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; rounded-radius: 8px;">
      <h2 style="color: #0f172a;">Complete your payment</h2>
      <p style="color: #334155; font-size: 15px; line-height: 1.6;">{body.replace('\n', '<br>')}</p>
      {f'<div style="margin-top: 25px;"><a href="{link_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Retry Payment &rarr;</a></div>' if link_url else ''}
      <hr style="margin-top: 30px; border: none; border-top: 1px solid #f1f5f9;" />
      <p style="color: #94a3b8; font-size: 12px;">This is an automated recovery message from Reviveo.</p>
    </div>
    """

    # 4. Email sending execution (Live Resend vs Simulated)
    notification_id = f"notif_{uuid.uuid4().hex[:16]}"
    status = "simulated"
    provider_message_id = None
    error_detail = None
    sent_at = None

    if settings.is_live and settings.notification_email_enabled and settings.notification_email_configured:
        provider = ResendEmailProvider(settings.resend_api_key)
        ok, resend_id, err = provider.send_email(
            to=recipient,
            subject=subject,
            text_body=body,
            html_body=html_body,
            from_email=settings.notification_from_email,
        )
        if ok:
            status = "sent"
            provider_message_id = resend_id
            sent_at = datetime.now(timezone.utc).isoformat()
        else:
            status = "failed"
            error_detail = err
    else:
        status = "simulated"
        provider_message_id = f"sim_msg_{uuid.uuid4().hex[:12]}"
        sent_at = datetime.now(timezone.utc).isoformat()

    # 5. Persist record in notifications table
    db.insert_notification({
        "notification_id": notification_id,
        "merchant_id": merchant_id,
        "event_id": event_id,
        "recovery_attempt_id": attempt_id,
        "channel": "email",
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "status": status,
        "provider_message_id": provider_message_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sent_at": sent_at,
        "error": error_detail,
        "ai_generated": ai_result.used,
        "ai_model": ai_result.model,
        "ai_latency_ms": ai_result.latency_ms,
    })

    logger.info("customer notification processed", extra={"context": {
        "event_id": event_id, "recovery_attempt_id": attempt_id,
        "status": status, "recipient": recipient,
    }})

    return NotificationResult(
        notification_id=notification_id,
        status=status,
        recipient=recipient,
        subject=subject,
        body=body,
        provider_message_id=provider_message_id,
        error=error_detail,
        ai_generated=ai_result.used,
        ai_model=ai_result.model,
        ai_latency_ms=ai_result.latency_ms,
    )
