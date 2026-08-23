"""Event state machine (doc §3.5).

The event row is the dashboard source of truth. Statuses only move forward;
terminal states can advance to `closed` but nothing else, and late/stale
webhooks can never regress status via lower rank.
"""
from __future__ import annotations

from .. import db
from ..enums import EventStatus, STATUS_RANK, TERMINAL_STATUSES
from ..logging_config import get_logger

logger = get_logger("reviveo.state_machine")


def transition(event_id: str, new_status: EventStatus) -> bool:
    ev = db.get_event(event_id)
    if ev is None:
        raise KeyError(f"Unknown event '{event_id}'")
    current = EventStatus(ev["status"])
    if current is new_status:
        return True

    if current in TERMINAL_STATUSES:
        if current is EventStatus.closed or new_status is not EventStatus.closed:
            logger.warning(
                "refused terminal regression %s -> %s (event %s)",
                current.value, new_status.value, event_id,
            )
            return False
        # recovered/expired/escalated/failed -> closed is a forward move.
    elif STATUS_RANK[new_status] < STATUS_RANK[current]:
        logger.warning(
            "refused stale transition %s -> %s (event %s)",
            current.value, new_status.value, event_id,
        )
        return False

    db.update_event(event_id, status=new_status.value)
    return True


def is_terminal(event: dict) -> bool:
    return EventStatus(event["status"]) in TERMINAL_STATUSES
