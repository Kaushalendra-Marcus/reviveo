"""Customer notification service (provider abstraction + AI message dispatch).

Channels: Email (Resend / Simulated) and SMS (Twilio / Simulated).
Responsibilities:
- Provider abstractions for transactional email + SMS (Resend / Twilio).
- Customer message generation via AI with deterministic fallback (one message
  body reused across channels; the SMS variant appends the payment link).
- Strict idempotency (one notification per recovery attempt + channel — the
  `notifications` table UNIQUE(recovery_attempt_id, channel) enforces it).
- Safe customer data handling (gracefully skip when contact is missing or a
  known test placeholder; placeholders are never stored as recipients).
- Audit trail recording and persistence in `notifications` table.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
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


def _recipient_domain(recipient: Optional[str]) -> str:
    """Domain-only recipient identifier for logs — enough to diagnose
    provider rejections (e.g. unverified test domains) without ever logging
    a full customer email address, API key, or auth header."""
    if isinstance(recipient, str) and "@" in recipient:
        return recipient.split("@")[-1].lower() or "unknown"
    return "unknown"


def _phone_suffix(recipient: Optional[str]) -> str:
    """Last-4-digits phone identifier for logs — enough to correlate with
    Twilio message logs without recording the full subscriber number."""
    digits = "".join(ch for ch in (recipient or "") if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else "unknown"


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
            logger.warning("resend email sending failed", extra={"context": {
                "code": exc.code, "error": err_text,
                "recipient_domain": _recipient_domain(to), "provider": "resend"}})
            return False, None, f"Resend API error ({exc.code}): {err_text}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("resend email network exception", extra={"context": {
                "error": str(exc), "recipient_domain": _recipient_domain(to),
                "provider": "resend"}})
            return False, None, f"Email sending exception: {exc}"


class SmsProvider:
    """Base abstract provider for transactional SMS sending."""
    def send_sms(self, *, to: str, body: str, from_number: str) -> tuple[bool, Optional[str], Optional[str]]:
        raise NotImplementedError


class TwilioSmsProvider(SmsProvider):
    """Twilio Programmable SMS provider (raw HTTPS, no SDK dependency).

    Trial accounts can only message verified recipient numbers — Twilio
    rejects the rest (error 21608), which surfaces here as failed, never
    sent. Auth uses HTTP Basic (SID:token); credentials are never logged.
    """
    def __init__(self, account_sid: str, auth_token: str):
        self.account_sid = account_sid
        self.auth_token = auth_token

    def send_sms(self, *, to: str, body: str, from_number: str) -> tuple[bool, Optional[str], Optional[str]]:
        url = (f"https://api.twilio.com/2010-04-01/Accounts/"
               f"{self.account_sid}/Messages.json")
        credentials = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Reviveo/1.0",
        }
        data = urllib.parse.urlencode(
            {"To": to, "From": from_number, "Body": body}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                message_sid = payload.get("sid")
                return True, message_sid, None
        except urllib.error.HTTPError as exc:
            err_text = exc.read().decode("utf-8") if exc.fp else str(exc)
            logger.warning("twilio sms sending failed", extra={"context": {
                "code": exc.code, "error": err_text,
                "recipient_suffix": _phone_suffix(to), "provider": "twilio"}})
            return False, None, f"Twilio API error ({exc.code}): {err_text}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("twilio sms network exception", extra={"context": {
                "error": str(exc), "recipient_suffix": _phone_suffix(to),
                "provider": "twilio"}})
            return False, None, f"SMS sending exception: {exc}"


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

    recipient = db.trusted_email((customer or {}).get("email"))

    # Final safety check: never send to a known placeholder/test identity.
    # Re-read the stored record (webhook-time data may be stale) and take
    # only a trusted address. A placeholder must never override — or be sent
    # in place of — a real customer email.
    if not recipient and event.get("customer_id"):
        fresh = db.get_customer(merchant_id, event["customer_id"])
        if fresh is not None:
            customer = fresh
            recipient = db.trusted_email(fresh.get("email"))
            if recipient:
                logger.info("notification recipient resolved from stored record", extra={"context": {
                    "event_id": event_id, "recovery_attempt_id": attempt_id,
                    "recipient_domain": _recipient_domain(recipient)}})

    # 2. Missing/trusted customer email check
    if not recipient:
        notification_id = f"notif_{uuid.uuid4().hex[:16]}"
        error_msg = "No trusted customer email available"
        db.insert_notification({
            "notification_id": notification_id,
            "merchant_id": merchant_id,
            "event_id": event_id,
            "recovery_attempt_id": attempt_id,
            "customer_id": event.get("customer_id") or (customer or {}).get("id"),
            "channel": "email",
            "recipient": "none",
            "subject": None,
            "body": "",
            "status": "skipped",
            "provider": None,
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
    provider: Optional[str] = None
    provider_message_id = None
    error_detail = None
    sent_at = None

    if settings.is_live and settings.notification_email_enabled and settings.notification_email_configured:
        provider = "resend"
        provider_obj = ResendEmailProvider(settings.resend_api_key)
        ok, resend_id, err = provider_obj.send_email(
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
            logger.warning("notification send failed", extra={"context": {
                "event_id": event_id, "recovery_attempt_id": attempt_id,
                "recipient_domain": _recipient_domain(recipient),
                "provider": "resend", "error": (err or "")[:300]}})
    else:
        status = "simulated"
        provider = "simulated"
        provider_message_id = f"sim_msg_{uuid.uuid4().hex[:12]}"
        sent_at = datetime.now(timezone.utc).isoformat()

    # 5. Persist record in notifications table
    db.insert_notification({
        "notification_id": notification_id,
        "merchant_id": merchant_id,
        "event_id": event_id,
        "recovery_attempt_id": attempt_id,
        "customer_id": event.get("customer_id") or (customer or {}).get("id"),
        "channel": "email",
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "status": status,
        "provider": provider,
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
        "notification_id": notification_id, "status": status,
        "recipient_domain": _recipient_domain(recipient if status != "skipped" else None),
        "provider_message_id": provider_message_id,
        "ai_generated": ai_result.used, "ai_model": ai_result.model,
        "ai_latency_ms": ai_result.latency_ms,
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


def send_sms_notification(
    *,
    merchant_id: str,
    event: dict,
    recovery_attempt: dict,
    customer: Optional[dict],
    short_url: Optional[str] = None,
) -> NotificationResult:
    """Dispatches a customer recovery SMS via Twilio (same architecture as
    email: idempotency → trusted-contact check → AI message + fallback →
    provider/simulated → persistence).

    Enforces:
    1. Idempotency: returns the existing row for this attempt+channel.
    2. Trusted phone only: missing or placeholder numbers persist 'skipped'
       with "No trusted customer phone available" — never sent anywhere.
    3. Same AI-drafted body as email (link guaranteed present), fallback
       template when AI is unavailable.
    4. Live Twilio send only when is_live + twilio_sms_enabled + fully
       configured; 'sent' solely on a Twilio SID, 'failed' with the provider
       error otherwise (incl. trial error 21608 for unverified recipients).
    """
    attempt_id = recovery_attempt["recovery_attempt_id"]
    event_id = event["event_id"]

    # 1. Idempotency check (channel='sms' keeps email/SMS rows independent).
    existing = db.get_notification_by_attempt(attempt_id, channel="sms")
    if existing:
        logger.info("sms notification already recorded for attempt — skipping duplicate", extra={"context": {
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

    recipient = db.trusted_phone((customer or {}).get("phone"))

    # Final safety check: re-read the stored record (webhook-time data may be
    # stale) and take only a trusted number. Placeholders never become SMS
    # recipients.
    if not recipient and event.get("customer_id"):
        fresh = db.get_customer(merchant_id, event["customer_id"])
        if fresh is not None:
            customer = fresh
            recipient = db.trusted_phone(fresh.get("phone"))

    # 2. Missing/untrusted phone check.
    if not recipient:
        notification_id = f"notif_{uuid.uuid4().hex[:16]}"
        error_msg = "No trusted customer phone available"
        db.insert_notification({
            "notification_id": notification_id,
            "merchant_id": merchant_id,
            "event_id": event_id,
            "recovery_attempt_id": attempt_id,
            "customer_id": event.get("customer_id") or (customer or {}).get("id"),
            "channel": "sms",
            "recipient": "none",
            "subject": None,
            "body": "",
            "status": "skipped",
            "provider": None,
            "provider_message_id": None,
            "error": error_msg,
            "ai_generated": False,
        })
        logger.info("sms notification skipped — no recipient", extra={"context": {"event_id": event_id}})
        return NotificationResult(
            notification_id=notification_id,
            status="skipped",
            recipient=None,
            subject=None,
            body=None,
            error=error_msg,
        )

    # 3. Message preparation — same AI draft as email so both channels agree.
    customer_name = (customer or {}).get("name") or "Customer"
    amount_paise = event.get("amount_paise", 0)
    rupees = amount_paise / 100
    cause = event.get("cause") or "payment_failed"
    link_url = short_url or (recovery_attempt.get("notes") or {}).get("short_url")

    fallback_body = (
        f"Hi {customer_name}, your payment of Rs.{rupees:,.2f} could not be "
        f"completed. Retry securely here: {link_url or 'your account portal'} "
        f"- Reviveo"
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
    if link_url and link_url not in body:
        body = f"{body}\n{link_url}"

    # 4. SMS sending execution (live Twilio vs simulated).
    notification_id = f"notif_{uuid.uuid4().hex[:16]}"
    status = "simulated"
    provider: Optional[str] = None
    provider_message_id = None
    error_detail = None
    sent_at = None

    if settings.is_live and settings.twilio_sms_enabled and settings.twilio_sms_configured:
        provider = "twilio"
        twilio = TwilioSmsProvider(settings.twilio_account_sid,
                                   settings.twilio_auth_token)
        ok, message_sid, err = twilio.send_sms(
            to=recipient,
            body=body,
            from_number=settings.twilio_phone_number,
        )
        if ok:
            status = "sent"
            provider_message_id = message_sid
            sent_at = datetime.now(timezone.utc).isoformat()
        else:
            status = "failed"
            error_detail = err
            logger.warning("sms notification send failed", extra={"context": {
                "event_id": event_id, "recovery_attempt_id": attempt_id,
                "recipient_suffix": _phone_suffix(recipient),
                "provider": "twilio", "error": (err or "")[:300]}})
    else:
        status = "simulated"
        provider = "simulated"
        provider_message_id = f"sim_msg_{uuid.uuid4().hex[:12]}"
        sent_at = datetime.now(timezone.utc).isoformat()

    # 5. Persist record in notifications table.
    db.insert_notification({
        "notification_id": notification_id,
        "merchant_id": merchant_id,
        "event_id": event_id,
        "recovery_attempt_id": attempt_id,
        "customer_id": event.get("customer_id") or (customer or {}).get("id"),
        "channel": "sms",
        "recipient": recipient,
        "subject": None,
        "body": body,
        "status": status,
        "provider": provider,
        "provider_message_id": provider_message_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sent_at": sent_at,
        "error": error_detail,
        "ai_generated": ai_result.used,
        "ai_model": ai_result.model,
        "ai_latency_ms": ai_result.latency_ms,
    })

    logger.info("customer sms notification processed", extra={"context": {
        "event_id": event_id, "recovery_attempt_id": attempt_id,
        "notification_id": notification_id, "status": status,
        "recipient_suffix": _phone_suffix(recipient),
        "provider_message_id": provider_message_id,
        "ai_generated": ai_result.used, "ai_model": ai_result.model,
        "ai_latency_ms": ai_result.latency_ms,
    }})

    return NotificationResult(
        notification_id=notification_id,
        status=status,
        recipient=recipient,
        subject=None,
        body=body,
        provider_message_id=provider_message_id,
        error=error_detail,
        ai_generated=ai_result.used,
        ai_model=ai_result.model,
        ai_latency_ms=ai_result.latency_ms,
    )
