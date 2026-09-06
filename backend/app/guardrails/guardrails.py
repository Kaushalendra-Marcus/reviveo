"""Compatibility wrapper around `domain.guardrails.check_guardrails`.

`domain/guardrails.py` is the single source of truth for enforcement; this
module just translates its result shape into the older
`GuardrailResult(passed/blocked_reasons)` interface that `agent/tools.py`
still expects. New code should import `domain.guardrails.check_guardrails`
directly instead of this wrapper.

Every check reads live state (attempts, counters, config) from the DB —
nothing here trusts caller-supplied "current values".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .. import db
from ..config import settings
from ..enums import Action

# Actions that reach out to the customer (subject to contact caps/channels).
CONTACT_ACTIONS = {
    Action.send_reminder,
    Action.retry_and_notify,
    Action.send_payment_update_link,
}
# Retry-style actions subject to cooldown between attempts.
RETRY_ACTIONS = {Action.immediate_retry, Action.retry_and_notify, Action.smart_retry_24h}
CHANNEL_FOR_ACTION = {
    Action.send_reminder: "email",
    Action.retry_and_notify: "email",
    Action.send_payment_update_link: "payment_link",
    Action.smart_retry_24h: "payment_link",
}


@dataclass(frozen=True)
class GuardrailResult:
    passed: bool
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_approval: bool = False

    def as_payload(self) -> dict:
        return {
            "passed": self.passed,
            "blocked_reasons": self.blocked_reasons,
            "warnings": self.warnings,
            "requires_approval": self.requires_approval,
        }


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def evaluate(
    merchant_id: str,
    event: dict,
    action: Action | str,
    amount_paise: int,
    *,
    cfg: Optional[dict] = None,
    now: Optional[datetime] = None,
    exclude_attempt_id: Optional[str] = None,
) -> GuardrailResult:
    """Legacy-shaped wrapper around `domain.guardrails.check_guardrails`,
    kept so `agent/tools.py` and any external callers built against the old
    interface keep working."""
    from ..domain.guardrails import check_guardrails as _live_check

    action = Action(action)
    cfg = cfg or db.get_guardrail_config(merchant_id)
    if cfg is None:
        raise ValueError(f"No guardrail config for merchant '{merchant_id}'")
    now = now or datetime.now(timezone.utc)

    live = _live_check(
        merchant_id=merchant_id, cfg=cfg, action=action,
        amount_paise=amount_paise, attempt_count=db.count_attempts(event["event_id"]),
        last_attempt_at=db.last_attempt_time(event["event_id"], exclude=exclude_attempt_id),
        event_created_at=event["created_at"], now=now,
    )

    blocked: list[str] = []
    warnings: list[str] = []
    if live.blocked:
        blocked.append(live.reason or live.code or "blocked by guardrails")
    if live.code == "cooldown_active" and live.retry_after:
        # Preserve the older, more detailed cooldown message format.
        try:
            elapsed = now - _parse_ts(db.last_attempt_time(event["event_id"], exclude=exclude_attempt_id) or event["created_at"])
            blocked = [f"cooldown active ({cfg['cooldown_hours']}h between retries; last attempt {elapsed.total_seconds() / 3600:.1f}h ago)"]
        except Exception:
            pass
    if live.requires_approval:
        warnings.append(
            f"amount ₹{amount_paise / 100:.0f} exceeds autonomous limit "
            f"₹{cfg['max_autonomous_recovery_amount_paise'] / 100:.0f} — approval required"
        )
    if live.code in ("daily_contact_cap_reached", "daily_recovery_value_cap_reached") and not blocked:
        blocked.append(live.reason or live.code)

    warnings.append(
        f"runtime limits: steps<={settings.max_agent_steps_per_event}, "
        f"tools<={settings.max_tool_calls_per_event}, "
        f"wall<={settings.max_agent_wall_time_seconds}s"
    )

    return GuardrailResult(
        passed=not live.blocked,
        blocked_reasons=blocked,
        warnings=warnings,
        requires_approval=live.requires_approval or False,
    )
