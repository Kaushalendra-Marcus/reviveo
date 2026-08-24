"""Batch runner (doc A0/C8) — runs a reproducible synthetic batch through the
real pipeline, and computes a baseline-vs-treatment comparison for the
"modeled incremental lift" metric (doc §3.14).

Batch runs default to `use_ai=False` to avoid cost/latency at volume
(doc C8), mirroring the dry_run pattern already used for Payment Links; a
small subset can be run with `use_ai=True` before a demo to show real agent
tool-use traces and AI-generated reasoning.

Baseline and treatment always run against the exact same event distribution
and the same deterministic seed (doc §3.14) — per-event outcome draws are
derived from `(random_seed, event_id)`, so every customer who would have
paid organically in the baseline also pays in the treatment; the
intervention can only add recoveries on top, never remove ones that would
have happened anyway. This keeps the comparison monotonic and reproducible,
and it is always labeled a modeled estimate, never a measured causal effect.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from .. import db
from ..domain.cause_analysis import classify_cause
from ..domain.decision_engine import POLICY_VERSION
from ..pipeline import attribution, pipeline
from ..services.agent_service import AGENT_VERSION
from . import synthetic_generator

DATASET_VERSION = synthetic_generator.DATASET_VERSION

MODELED_LIFT_LABEL = (
    "Modeled incremental lift — not a measured causal effect (no randomized control group)."
)

# Probability a customer pays organically with NO recovery system acting at
# all (their own retry, their bank retrying, or simply trying again later).
# Illustrative, hand-set rates reflecting how "self-healing" each cause
# typically is — not fit to any real dataset.
_ORGANIC_RECOVERY_PROB: dict[str, float] = {
    "card_expired": 0.05,
    "insufficient_funds": 0.15,
    "payment_timeout": 0.30,
    "bank_declined": 0.10,
    "checkout_abandoned": 0.08,
    "unclassified": 0.05,
}

# Additional probability an active recovery mechanism adds on top of the
# organic rate. native_subscription_retry gets zero uplift — it's Razorpay's
# own retry engine, not something our system is doing.
_MECHANISM_UPLIFT: dict[str, float] = {
    "reminder_only": 0.15,
    "scheduled_recovery_payment": 0.25,
    "new_recovery_payment": 0.30,
    "payment_link": 0.30,
    "checkout": 0.35,
    "manual_charge": 0.35,
    "native_subscription_retry": 0.0,
}


def _per_event_draw(random_seed: int, event_id: str) -> float:
    return random.Random(f"{random_seed}:{event_id}").random()


def run_batch(
    *, merchant_id: str, n_events: int, dry_run: bool = True, use_ai: bool = False,
    random_seed: Optional[int] = None,
) -> dict:
    random_seed = 42 if random_seed is None else random_seed
    events = synthetic_generator.generate_events(merchant_id=merchant_id, n=n_events, random_seed=random_seed)

    baseline = _run_baseline(events, random_seed)
    treatment = _run_treatment(events, random_seed, use_ai=use_ai)

    simulation_run_id = f"sim_{uuid.uuid4().hex[:12]}"
    db.insert_simulation_run({
        "simulation_run_id": simulation_run_id, "merchant_id": merchant_id,
        "random_seed": random_seed, "dataset_version": DATASET_VERSION,
        "agent_version": AGENT_VERSION, "policy_version": POLICY_VERSION,
        "n_events": n_events, "use_ai": use_ai, "dry_run": dry_run,
        "baseline": baseline, "treatment": treatment,
    })
    return {
        "simulation_run_id": simulation_run_id, "n_events": n_events, "use_ai": use_ai,
        "dry_run": dry_run, "baseline": baseline, "treatment": treatment,
        "created_at": db.now_iso(), "label": MODELED_LIFT_LABEL,
    }


def _run_baseline(events: list[dict], random_seed: int) -> dict:
    """Pure computation — no DB writes. Represents "no recovery system at
    all"; must never be persisted as if it were real event activity."""
    recovered_paise = 0
    recovered_count = 0
    for event in events:
        cause = classify_cause(event.get("error_code")).value
        prob = _ORGANIC_RECOVERY_PROB.get(cause, 0.05)
        if _per_event_draw(random_seed, event["event_id"]) < prob:
            recovered_paise += event["amount_paise"]
            recovered_count += 1

    total_at_risk = sum(e["amount_paise"] for e in events)
    n = len(events) or 1
    return {
        "n_events": len(events), "total_at_risk_paise": total_at_risk,
        "recovered_paise": recovered_paise, "recovered_count": recovered_count,
        "recovery_rate": round(recovered_count / n, 4),
    }


def _run_treatment(events: list[dict], random_seed: int, *, use_ai: bool) -> dict:
    """Runs every event through the real pipeline — these ARE persisted
    (origin='synthetic', kept explicitly separate from live_test_mode data
    per doc §3.14) so the dashboard has realistic-scale data to show.

    Note: batch-simulated events share the same daily guardrail counters as
    real live activity (doc's guardrail_config is per-merchant, not
    per-origin) — acceptable for a single demo batch per day at the tuned
    default caps, but a production deployment running frequent large
    batches would want the daily caps scoped separately from simulation
    traffic. Out of scope for this MVP.

    Because a real 24-hour wait or a real webhook round-trip isn't practical
    inside a synchronous batch run, each attempt's eventual outcome is
    resolved immediately using its mechanism's modeled effectiveness rate —
    this is the same simulated-outcome approach used for every attempt here,
    scheduled or not, and is exactly what makes this "modeled", not measured.
    """
    recovered_paise = 0
    recovered_count = 0
    executed = 0
    scheduled = 0
    pending_approval = 0
    pending_approval_value_paise = 0
    expired = 0

    for event in events:
        db.insert_event(event)
        result = pipeline.process_event(db.get_event(event["event_id"]), use_ai=use_ai)
        status = result.get("status")
        if status == "approval_pending":
            pending_approval += 1
            pending_approval_value_paise += event["amount_paise"]
        elif status == "expired":
            expired += 1
        elif status == "scheduled":
            scheduled += 1
        elif status == "waiting_for_outcome":
            executed += 1

        attempts = db.list_attempts_for_event(event["event_id"])
        if not attempts:
            continue  # escalated straight to approval — nothing was executed to simulate an outcome for

        attempt = attempts[-1]
        cause = classify_cause(event.get("error_code")).value
        organic_prob = _ORGANIC_RECOVERY_PROB.get(cause, 0.05)
        uplift = _MECHANISM_UPLIFT.get(attempt["execution_mechanism"], 0.15)
        treatment_prob = min(0.95, organic_prob + uplift)

        if _per_event_draw(random_seed, event["event_id"]) < treatment_prob:
            outcome = attribution.attribute_payment(
                recovery_attempt_id=attempt["recovery_attempt_id"],
                razorpay_payment_id=f"pay_synthetic_{uuid.uuid4().hex[:10]}",
                amount_paise=attempt["amount_paise"], recovery_window_days=7,
            )
            if outcome.accepted:
                recovered_paise += attempt["amount_paise"]
                recovered_count += 1

    total_at_risk = sum(e["amount_paise"] for e in events)
    n = len(events) or 1
    return {
        "n_events": len(events), "total_at_risk_paise": total_at_risk,
        "recovered_paise": recovered_paise, "recovered_count": recovered_count,
        "recovery_rate": round(recovered_count / n, 4),
        "executed": executed, "scheduled": scheduled,
        "pending_approval": pending_approval,
        "pending_approval_value_paise": pending_approval_value_paise,
        "expired": expired,
    }
