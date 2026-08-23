"""In-process scheduler (doc §3.11 + §0 — no message queue/workers).

A periodic asyncio loop in the same process re-enters the same guarded
execution path for: due scheduled actions, stale approvals, and attempts
whose recovery window elapsed with no outcome.
"""
from __future__ import annotations

import asyncio

from .. import db
from ..config import settings
from ..logging_config import get_logger
from ..pipeline import attribution, executor
from ..services import approvals as approvals_service

logger = get_logger("reviveo.scheduler")


def tick() -> dict:
    """One scheduler pass — also callable directly from tests."""
    merchant_ids = [
        r["merchant_id"] for r in db.query_all(
            "SELECT DISTINCT merchant_id FROM recovery_attempts"
        )
    ] or [settings.default_merchant_id]

    executed = skipped = expired_attempts = 0
    for mid in merchant_ids:
        for attempt in db.due_scheduled_attempts(mid):
            result = executor.resume_scheduled_attempt(attempt)
            if result.get("executed"):
                executed += 1
            else:
                skipped += 1
        expired_attempts += attribution.expire_stale_attempts(mid)

    expired_approvals = approvals_service.expire_stale()
    if executed or skipped or expired_attempts or expired_approvals:
        logger.info("scheduler tick",
                    extra={"context": {"scheduled_executed": executed,
                                       "scheduled_skipped": skipped,
                                       "attempts_expired": expired_attempts,
                                       "approvals_expired": expired_approvals}})
    return {"scheduled_executed": executed, "scheduled_skipped": skipped,
            "attempts_expired": expired_attempts,
            "approvals_expired": expired_approvals}


async def run_scheduler_loop() -> None:
    logger.info("scheduler loop started",
                extra={"context": {"interval_s": settings.scheduler_poll_interval_seconds}})
    while True:
        try:
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the loop must survive anything
            logger.error("scheduler tick failed: %s", exc)
        await asyncio.sleep(settings.scheduler_poll_interval_seconds)
