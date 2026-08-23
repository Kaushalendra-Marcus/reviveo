"""One test per guardrail check: blocks when exceeded, passes when not (A6)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.guardrails.guardrails import evaluate
from app.enums import Action


def make_event(**overrides) -> dict:
    ev = {
        "event_id": "evt_g1",
        "merchant_id": "codecraft",
        "customer_id": "cust_rahul",
        "type": "payment_failed",
        "amount_paise": 99900,
        "status": "action_selected",
        "created_at": db.now_iso(),
    }
    ev.update(overrides)
    db.insert_event({**ev, "origin": "synthetic"})
    return ev


def cfg():
    return db.get_guardrail_config("codecraft")


class TestGuardrails:
    def test_first_action_passes(self):
        ev = make_event()
        r = evaluate("codecraft", ev, Action.immediate_retry, 99900, cfg=cfg())
        assert r.passed and not r.requires_approval

    def test_max_retries_blocks(self):
        ev = make_event()
        for _ in range(cfg()["max_retries"]):
            db.insert_recovery_attempt({
                "recovery_attempt_id": f"ra_{db.next_attempt_number('evt_g1')}",
                "event_id": ev["event_id"], "merchant_id": "codecraft",
                "attempt_number": db.next_attempt_number(ev["event_id"]),
                "action": "immediate_retry", "execution_mechanism":
                    "new_recovery_payment", "amount_paise": 99900,
            })
        r = evaluate("codecraft", ev, Action.send_reminder, 99900, cfg=cfg())
        assert not r.passed
        assert any("max_retries" in b for b in r.blocked_reasons)

    def test_cooldown_blocks_second_quick_retry(self):
        ev = make_event()
        db.insert_recovery_attempt({
            "recovery_attempt_id": "ra_c1", "event_id": ev["event_id"],
            "merchant_id": "codecraft", "attempt_number": 1,
            "action": "immediate_retry", "execution_mechanism": "new_recovery_payment",
            "amount_paise": 99900,
        })
        r = evaluate("codecraft", ev, Action.retry_and_notify, 99900, cfg=cfg())
        assert not r.passed
        assert any("cooldown" in b for b in r.blocked_reasons)
        # after the cooldown it passes again
        future = datetime.now(timezone.utc) + timedelta(hours=cfg()["cooldown_hours"] + 1)
        r2 = evaluate("codecraft", ev, Action.retry_and_notify, 99900, cfg=cfg(), now=future)
        assert r2.passed

    def test_recovery_window_blocks_old_events(self):
        old = (datetime.now(timezone.utc) - timedelta(days=cfg()["recovery_window_days"] + 1)
               ).isoformat()
        ev = make_event(created_at=old)
        r = evaluate("codecraft", ev, Action.send_reminder, 99900, cfg=cfg())
        assert not r.passed
        assert any("window" in b for b in r.blocked_reasons)

    def test_amount_above_autonomous_limit_requires_approval_not_block(self):
        ev = make_event(amount_paise=10_000_000)  # ₹1,00,000 > default ₹5,000
        r = evaluate("codecraft", ev, Action.send_payment_update_link,
                     10_000_000, cfg=cfg())
        assert r.passed
        assert r.requires_approval is True
        assert any("autonomous" in w for w in r.warnings)

    def test_daily_value_cap_blocks(self):
        ev = make_event(amount_paise=60_000_000)  # above ₹5,00,000 daily cap
        r = evaluate("codecraft", ev, Action.smart_retry_24h, 60_000_000, cfg=cfg())
        assert not r.passed
        assert any("value cap" in b for b in r.blocked_reasons)

    def test_daily_contact_cap_blocks_contact_actions_only(self):
        db.incr_daily_counter("codecraft", contacts=cfg()["daily_contact_cap"])
        ev = make_event()
        r = evaluate("codecraft", ev, Action.send_reminder, 99900, cfg=cfg())
        assert not r.passed
        assert any("contact cap" in b for b in r.blocked_reasons)
        # non-contact retry still passes cooldown/window etc.
        r2 = evaluate("codecraft", ev, Action.smart_retry_24h, 99900, cfg=cfg())
        assert r2.passed

    def test_disabled_channel_blocks(self):
        restricted = {**cfg(), "allowed_channels": ["payment_link"]}
        ev = make_event()
        r = evaluate("codecraft", ev, Action.send_reminder, 99900, cfg=restricted)
        assert not r.passed
        assert any("'email'" in b for b in r.blocked_reasons)

    def test_escalation_always_passes(self):
        db.incr_daily_counter("codecraft", contacts=cfg()["daily_contact_cap"])
        for i in range(cfg()["max_retries"]):
            db.insert_recovery_attempt({
                "recovery_attempt_id": f"ra_e{i}", "event_id": "evt_x",
                "merchant_id": "codecraft", "attempt_number": i + 1,
                "action": "immediate_retry", "execution_mechanism": "new_recovery_payment",
                "amount_paise": 100,
            })
        ev = make_event(event_id="evt_x")
        r = evaluate("codecraft", ev, Action.escalate_to_human, 99900, cfg=cfg())
        assert r.passed
