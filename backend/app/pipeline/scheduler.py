"""In-process scheduler for scheduled-action revalidation (doc §3.11). No
message queue or worker process is used (doc §0) — a periodic asyncio loop
inside the same FastAPI process re-enters the exact same guarded execution
path as everything else, on the schedule set by
`SCHEDULER_POLL_INTERVAL_SECONDS`.
"""
from __future__ import annotations

import asyncio

from .. import db
from ..config import settings
from ..logging_config import get_logger
from . import pipeline

logger = get_logger("reviveo.scheduler")


async def run_scheduler_loop() -> None:
    logger.info("scheduler started", extra={"context": {
        "interval_seconds": settings.scheduler_poll_interval_seconds,
    }})
    while True:
        try:
            n = process_due_scheduled_attempts()
            if n:
                logger.info("scheduler processed due attempts", extra={"context": {"count": n}})
        except Exception as exc:  # noqa: BLE001 — a single bad iteration must not kill the loop
            logger.error("scheduler iteration failed", extra={"context": {"error": str(exc)}})
        await asyncio.sleep(settings.scheduler_poll_interval_seconds)


def process_due_scheduled_attempts(merchant_id: str | None = None) -> int:
    """Revalidates and (re-)executes every scheduled attempt whose time has
    come, plus expires stale waiting events and stale approvals (AUDIT_REPORT
    "Scheduler persistence gap"). Returns how many scheduled attempts were
    processed. Plain synchronous function so it can also be triggered directly
    (tests, or a manual 'run scheduler now' action) without needing the loop.
    """
    merchant_id = merchant_id or settings.default_merchant_id
    due = db.due_scheduled_attempts(merchant_id)
    for attempt in due:
        pipeline.revalidate_and_execute_scheduled(attempt)

    # Stale waiting_for_outcome sweep: if no outcome webhook arrives within
    # the recovery window, finally resolve to expired so the dashboard doesn't
    # show indefinitely pending rows.
    from datetime import datetime, timedelta, timezone
    from ..services import approvals as approvals_service

    cfg = db.get_guardrail_config(merchant_id)
    if cfg:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cfg["recovery_window_days"])).isoformat()
        for ev in db.stale_waiting_events(merchant_id, cutoff):
            db.update_event(ev["event_id"], status="expired")
            db.update_recovery_attempt(
                db.list_attempts_for_event(ev["event_id"])[-1]["recovery_attempt_id"]
                if db.list_attempts_for_event(ev["event_id"]) else "",
                status="expired",
            ) if db.list_attempts_for_event(ev["event_id"]) else None
            db.insert_audit({
                "event_id": ev["event_id"], "merchant_id": merchant_id,
                "stage": "outcome", "message": "Expired via scheduler sweep (no outcome within window)",
                "payload": {"expired_by": "scheduler"},
            })
    try:
        approvals_service.expire_stale()
    except Exception:
        pass
    return len(due)
