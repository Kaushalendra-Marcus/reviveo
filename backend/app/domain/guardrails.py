"""Runtime and financial guardrails (doc §3.10-§3.13).

Guardrail logic lives here, inside plain enforced Python — never inside the
model's judgment (doc C4). Whether the caller is the deterministic pipeline
or an agent tool, every action passes through `check_guardrails()` before
anything is executed. If blocked, the caller gets `{blocked: True, ...}` back
and must obey it; nothing downstream re-checks or overrides this decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import db
from ..config import settings
from ..enums import Action

# Actions that reach out to the customer — count against the daily contact cap.
_CONTACT_ACTIONS = {
    Action.send_reminder, Action.retry_and_notify, Action.send_payment_update_link,
    Action.smart_retry_24h, Action.immediate_retry,
}


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    code: Optional[str]                 # machine-readable reason, e.g. "cooldown_active"
    reason: Optional[str]               # human-readable explanation for the audit trail
    requires_approval: bool = False
    retry_after: Optional[str] = None   # ISO datetime — set only for cooldown_active


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_guardrails(
    *,
    merchant_id: str,
    cfg: dict,
    action: Action,
    amount_paise: int,
    attempt_count: int,
    last_attempt_at: Optional[str],
    event_created_at: str,
    now: Optional[datetime] = None,
) -> GuardrailResult:
    """Enforces the recovery window, retry limits, cooldowns, daily caps, and
    the autonomous-execution amount ceiling (doc §3.10). This is the single
    enforcement point — every check here blocks or annotates the action, it
    never merely advises.
    """
    now = now or datetime.now(timezone.utc)

    if action == Action.escalate_to_human:
        # Escalation is always allowed — it's the safe outcome by definition.
        return GuardrailResult(blocked=False, code=None, reason=None)

    # Recovery window (doc §3.1/§3.14): once the event has aged out, stop
    # starting new attempts — the pipeline marks the event expired instead.
    window_days = min(cfg["recovery_window_days"], settings.max_recovery_lifetime_days)
    created = _parse_iso(event_created_at)
    if now - created > timedelta(days=window_days):
        return GuardrailResult(
            blocked=True, code="recovery_window_expired",
            reason=f"Event is older than the {window_days}-day recovery window.",
        )

    # Retry limit — merchant config is clamped to the system hard ceiling.
    effective_max_retries = min(cfg["max_retries"], settings.max_recovery_attempts)
    if attempt_count >= effective_max_retries:
        return GuardrailResult(
            blocked=True, code="max_retries_exceeded",
            reason=f"{attempt_count} attempt(s) already made; limit is {effective_max_retries}.",
        )

    # Cooldown — if the last attempt was too recent, this action should be
    # scheduled for when the cooldown lifts rather than fired again now.
    if last_attempt_at:
        cooldown_until = _parse_iso(last_attempt_at) + timedelta(hours=cfg["cooldown_hours"])
        if now < cooldown_until:
            return GuardrailResult(
                blocked=True, code="cooldown_active",
                reason=f"Cooldown active until {cooldown_until.isoformat()}.",
                retry_after=cooldown_until.isoformat(),
            )

    # Daily contact cap — only actions that reach the customer count.
    counter = db.get_daily_counter(merchant_id)
    if action in _CONTACT_ACTIONS and counter["contact_count"] >= cfg["daily_contact_cap"]:
        return GuardrailResult(
            blocked=True, code="daily_contact_cap_reached",
            reason=f"Daily contact cap of {cfg['daily_contact_cap']} reached.",
        )

    # Daily recovery-value cap — cumulative amount attempted today.
    if counter["recovery_value_paise"] + amount_paise > cfg["daily_recovery_value_cap_paise"]:
        return GuardrailResult(
            blocked=True, code="daily_recovery_value_cap_reached",
            reason="Daily recovery value cap would be exceeded by this attempt.",
        )

    # Max autonomous recovery amount — doesn't block, but forces a human to
    # sign off before this specific attempt executes (doc §3.10).
    if amount_paise > cfg["max_autonomous_recovery_amount_paise"]:
        return GuardrailResult(
            blocked=False, code="amount_exceeds_autonomous_ceiling",
            reason=f"Amount {amount_paise} paise exceeds the autonomous execution ceiling of "
                   f"{cfg['max_autonomous_recovery_amount_paise']} paise.",
            requires_approval=True,
        )

    return GuardrailResult(blocked=False, code=None, reason=None)
