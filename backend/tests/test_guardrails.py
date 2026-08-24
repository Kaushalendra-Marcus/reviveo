from datetime import datetime, timedelta, timezone

from app.domain import guardrails as gr
from app.enums import Action

MERCHANT = "test_merchant"

_CFG = {
    "recovery_window_days": 7,
    "high_confidence": 0.85,
    "low_confidence": 0.50,
    "max_retries": 3,
    "cooldown_hours": 24,
    "max_autonomous_recovery_amount_paise": 500_000,
    "daily_recovery_value_cap_paise": 5_000_000,
    "daily_contact_cap": 100,
}


def _now_iso(delta: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


def test_escalate_is_never_blocked(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.escalate_to_human,
        amount_paise=999_999_999, attempt_count=999, last_attempt_at=_now_iso(),
        event_created_at=_now_iso(timedelta(days=999)),
    )
    assert r.blocked is False


def test_passes_when_nothing_exceeded(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=0, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is False
    assert r.requires_approval is False


def test_recovery_window_expired_blocks(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=0, last_attempt_at=None,
        event_created_at=_now_iso(timedelta(days=8)),
    )
    assert r.blocked is True
    assert r.code == "recovery_window_expired"


def test_max_retries_exceeded_blocks(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=3, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is True
    assert r.code == "max_retries_exceeded"


def test_max_retries_clamped_to_system_ceiling(temp_db):
    loose_cfg = dict(_CFG, max_retries=100)  # merchant tried to configure looser than system ceiling
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=loose_cfg, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=3, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is True
    assert r.code == "max_retries_exceeded"


def test_cooldown_active_blocks_with_retry_after(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=0, last_attempt_at=_now_iso(timedelta(hours=1)),
        event_created_at=_now_iso(),
    )
    assert r.blocked is True
    assert r.code == "cooldown_active"
    assert r.retry_after is not None


def test_cooldown_passed_does_not_block(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=0, last_attempt_at=_now_iso(timedelta(hours=25)),
        event_created_at=_now_iso(),
    )
    assert r.blocked is False


def test_daily_contact_cap_blocks(temp_db):
    temp_db.incr_daily_counter(MERCHANT, contacts=100)
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=0, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is True
    assert r.code == "daily_contact_cap_reached"


def test_daily_contact_cap_ignores_non_contact_actions(temp_db):
    temp_db.incr_daily_counter(MERCHANT, contacts=100)
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.monitor_native_retry,
        amount_paise=10_000, attempt_count=0, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is False


def test_daily_recovery_value_cap_blocks(temp_db):
    temp_db.incr_daily_counter(MERCHANT, value_paise=4_995_000)
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=10_000, attempt_count=0, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is True
    assert r.code == "daily_recovery_value_cap_reached"


def test_amount_over_autonomous_ceiling_requires_approval_not_block(temp_db):
    r = gr.check_guardrails(
        merchant_id=MERCHANT, cfg=_CFG, action=Action.send_reminder,
        amount_paise=600_000, attempt_count=0, last_attempt_at=None,
        event_created_at=_now_iso(),
    )
    assert r.blocked is False
    assert r.requires_approval is True
    assert r.code == "amount_exceeds_autonomous_ceiling"
