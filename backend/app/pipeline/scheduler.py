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
    come. Returns how many were processed. Plain synchronous function so it
    can also be triggered directly (tests, or a manual 'run scheduler now'
    action) without needing the asyncio loop.
    """
    merchant_id = merchant_id or settings.default_merchant_id
    due = db.due_scheduled_attempts(merchant_id)
    for attempt in due:
        pipeline.revalidate_and_execute_scheduled(attempt)
    return len(due)
