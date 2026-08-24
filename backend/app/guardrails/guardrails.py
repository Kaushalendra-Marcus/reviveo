"""Deterministic guardrails — the enforcement boundary (doc §3.10, C4).

AUDIT NOTE (2026-08-24): this module (`app/guardrails/guardrails.py`,
`evaluate()`) is a SEPARATE, DUPLICATE implementation from the one actually
enforced on every live request path: `app/domain/guardrails.py`
(`check_guardrails()`), imported by `pipeline.py`, `services/agent_service.py`,
and `api/routes.py`'s `approve_approval`. The two have diverged (different
check ordering, different cooldown scoping — this version applies cooldown
to ANY action with a prior attempt timestamp, `domain/guardrails.py` scopes
it to retry-style actions only). This module is only reachable from
`agent/tools.py` and `pipeline/executor.py`, both themselves dead code (see
their docstrings). Do not add new callers of this module — use
`app/domain/guardrails.check_guardrails` instead. See AUDIT_REPORT.md and
TODO.md for the recommended cleanup (delete this module once independently
re-verified with `grep -rn` + a clean `pytest` run).

The agent may propose, but these checks decide. Every check reads live state
(attempts, counters, config) from the DB; nothing here trusts caller-supplied
"current values". `escalate_to_human` always passes: escalation is never a
financially dangerous action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    action = Action(action)
    cfg = cfg or db.get_guardrail_config(merchant_id)
    if cfg is None:
        raise ValueError(f"No guardrail config for merchant '{merchant_id}'")
    now = now or datetime.now(timezone.utc)

    blocked: list[str] = []
    warnings: list[str] = []
    requires_approval = False

    # Escalation is always permitted (doc §3.9 risk tier 'safe').
    if action is Action.escalate_to_human:
        return GuardrailResult(passed=True)

    attempts_used = db.count_attempts(event["event_id"])
    if attempts_used >= cfg["max_retries"]:
        blocked.append(f"max_retries ({cfg['max_retries']}) already used")

    created = _parse_ts(event["created_at"])
    lifetime_end = created + timedelta(days=cfg["recovery_window_days"])
    if now > lifetime_end:
        blocked.append(
            f"outside recovery window ({cfg['recovery_window_days']}d since event)"
        )

    if action in RETRY_ACTIONS:
        last = db.last_attempt_time(event["event_id"], exclude=exclude_attempt_id)
        if last:
            elapsed = now - _parse_ts(last)
            if elapsed < timedelta(hours=cfg["cooldown_hours"]):
                blocked.append(
                    f"cooldown active ({cfg['cooldown_hours']}h between retries; "
                    f"last attempt {elapsed.total_seconds() / 3600:.1f}h ago)"
                )

    if amount_paise > cfg["max_autonomous_recovery_amount_paise"]:
        requires_approval = True
        warnings.append(
            f"amount ₹{amount_paise / 100:.0f} exceeds autonomous limit "
            f"₹{cfg['max_autonomous_recovery_amount_paise'] / 100:.0f} — approval required"
        )

    counter = db.get_daily_counter(merchant_id)
    if counter["recovery_value_paise"] + amount_paise > cfg["daily_recovery_value_cap_paise"]:
        blocked.append("daily recovery value cap reached")

    if action in CONTACT_ACTIONS:
        if counter["contact_count"] >= cfg["daily_contact_cap"]:
            blocked.append("daily customer-contact cap reached")
        channel = CHANNEL_FOR_ACTION.get(action)
        if channel and channel not in cfg["allowed_channels"]:
            blocked.append(f"channel '{channel}' not enabled for this merchant")

    # Runtime agent limits are enforced by the agent loop (settings), surfaced
    # here only as context so one payload tells the whole safety story.
    warnings.append(
        f"runtime limits: steps<={settings.max_agent_steps_per_event}, "
        f"tools<={settings.max_tool_calls_per_event}, "
        f"wall<={settings.max_agent_wall_time_seconds}s"
    )

    return GuardrailResult(
        passed=not blocked,
        blocked_reasons=blocked,
        warnings=warnings,
        requires_approval=requires_approval,
    )
