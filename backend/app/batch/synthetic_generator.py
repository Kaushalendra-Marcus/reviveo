"""Synthetic event generator — produces a reproducible, realistic mix of
payment_failed / subscription_failed / subscription_halted events across the
seeded demo customers, for scale-testing the pipeline and for the batch
simulation used in measurement (doc §3.14: same distribution + deterministic
seed for baseline vs treatment).
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from .. import db

DATASET_VERSION = "synthetic-v1"

# Weighted so the resulting cause mix looks like a real dunning queue:
# insufficient funds and bank declines dominate, timeouts and abandoned
# checkouts are less common, unclassified codes are rare but present.
_ERROR_CODE_WEIGHTS: list[tuple[str, float]] = [
    ("insufficient_funds", 0.28),
    ("card_declined", 0.20),
    ("card_expired", 0.14),
    ("payment_timed_out", 0.12),
    ("payment_cancelled", 0.10),
    ("bank_downtime", 0.08),
    ("authentication_failed", 0.05),
    ("SOME_UNRECOGNIZED_GATEWAY_CODE", 0.03),  # deliberately unclassified
]

_EVENT_TYPE_WEIGHTS: list[tuple[str, float]] = [
    ("payment_failed", 0.70),
    ("subscription_failed", 0.20),
    ("subscription_halted", 0.10),
]


def _weighted_choice(rng: random.Random, weights: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in weights)
    r = rng.uniform(0, total)
    upto = 0.0
    for value, w in weights:
        upto += w
        if r <= upto:
            return value
    return weights[-1][0]


def generate_events(*, merchant_id: str, n: int, random_seed: int) -> list[dict]:
    """Pure function of (merchant_id, n, random_seed) — same inputs always
    produce the same event list, which is what makes baseline vs treatment
    comparisons and repeated demo runs reproducible (doc §3.14)."""
    rng = random.Random(random_seed)
    customers = db.list_customers(merchant_id, limit=1000, offset=0)
    if not customers:
        raise ValueError(f"No seeded customers found for merchant '{merchant_id}' — run seed first.")

    events: list[dict] = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        customer = rng.choice(customers)
        subscription = db.get_subscription(f"sub_{customer['id']}")
        etype = _weighted_choice(rng, _EVENT_TYPE_WEIGHTS)
        error_code = _weighted_choice(rng, _ERROR_CODE_WEIGHTS)
        amount = subscription["amount_paise"] if subscription else rng.choice([9_900, 49_900, 99_900, 249_900])
        # Spread creation times across the last week so timeseries charts
        # have something to show. Mostly stays inside the default 7-day
        # recovery window (realistic — a daily failed-payment queue isn't
        # dominated by year-old fossils); a small tail intentionally exceeds
        # it so expiry logic still gets exercised.
        created_at = (now - timedelta(days=rng.uniform(0, 6), hours=rng.uniform(0, 23))).isoformat()

        events.append({
            "event_id": f"evt_synth_{uuid.uuid4().hex[:12]}",
            "merchant_id": merchant_id,
            "customer_id": customer["id"],
            "subscription_id": subscription["id"] if (subscription and etype != "payment_failed") else None,
            "invoice_id": None,
            "type": etype,
            "error_code": error_code,
            "amount_paise": amount,
            "status": "detected",
            "origin": "synthetic",
            "created_at": created_at,
        })
    return events
