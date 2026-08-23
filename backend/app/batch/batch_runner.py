"""Synthetic batch + simulation (doc §3.14).

Deterministic (seeded) event generation so runs are reproducible; seed,
dataset/agent/policy versions are stored with every simulation run. Baseline
vs treatment is always labelled "modeled incremental lift — not a measured
causal effect" because the demo has no randomized control group.
"""
from __future__ import annotations

import random
import uuid
from collections import Counter

from .. import db
from ..config import settings
from ..domain.decision_engine import POLICY_VERSION
from ..logging_config import get_logger
from ..pipeline import pipeline

logger = get_logger("reviveo.batch")

DATASET_VERSION = "synthetic-1.0"
AGENT_VERSION = f"deterministic-1.0+{settings.ai_model_fast}"

_TYPE_WEIGHTS = [
    ("payment_failed", 0.50),
    ("subscription_failed", 0.25),
    ("subscription_halted", 0.15),
    ("abandoned_checkout", 0.10),
]

_ERROR_POOLS: dict[str, list[str]] = {
    "payment_failed": ["insufficient_funds", "payment_timed_out", "bank_downtime",
                       "card_declined", "card_expired", "gateway_technical_error"],
    "subscription_failed": ["insufficient_funds", "card_expired", "payment_timed_out"],
    "subscription_halted": ["card_expired", "card_declined", "insufficient_funds"],
    "abandoned_checkout": ["payment_cancelled"],
}
# ~6% unclassifiable noise so the escalation path gets exercised honestly.
_UNCLASSIFIED = "gateway_internal_error_xyz"

_STATE_BY_TYPE = {"subscription_failed": "pending", "subscription_halted": "halted"}


def generate_events(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    customers = db.list_customers(settings.default_merchant_id, max(n, 1), 0)
    if not customers:
        raise RuntimeError("No customers seeded — cannot generate a batch.")
    events = []
    for _ in range(n):
        customer = rng.choice(customers)
        roll, acc = rng.random(), 0.0
        event_type = _TYPE_WEIGHTS[-1][0]
        for t, w in _TYPE_WEIGHTS:
            acc += w
            if roll <= acc:
                event_type = t
                break
        error_code = (_UNCLASSIFIED if rng.random() < 0.06
                      else rng.choice(_ERROR_POOLS[event_type]))
        sub = db.get_subscription(f"sub_{customer['id']}")
        events.append({
            "merchant_id": settings.default_merchant_id,
            "type": event_type,
            "customer_id": customer["id"],
            "subscription_id": f"sub_{customer['id']}",
            "error_code": error_code,
            "amount_paise": sub["amount_paise"] if sub else 99900,
            "origin": "synthetic",
        })
    return events


def run_batch(*, n_events: int = 25, dry_run: bool = True, use_ai: bool = False,
              seed: int | None = None, record: bool = False) -> dict:
    """Process n synthetic events through the real pipeline."""
    seed = seed if seed is not None else 42
    events = generate_events(n_events, seed)

    statuses: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    recovered_paise = 0
    recovered_count = 0
    approvals_pending = 0

    for spec in events:
        ev = pipeline.ingest_event(spec)
        result = pipeline.process_event(ev["event_id"], use_ai=use_ai)
        refreshed = db.get_event(ev["event_id"])
        statuses[refreshed["status"]] += 1
        decision = db.get_latest_decision(ev["event_id"])
        if decision:
            actions[decision["action"]] += 1
        causes[refreshed["cause"] or "unclassified"] += 1
        if refreshed["status"] == "recovered":
            row = db.query_one(
                "SELECT COALESCE(SUM(amount_paise),0) v FROM recovered_payments "
                "WHERE event_id=? AND within_window=1",
                (ev["event_id"],),
            )
            recovered_count += 1 if row["v"] else 0  # type: ignore[index]
            recovered_paise += row["v"]  # type: ignore[index]
        if refreshed["status"] == "approval_pending":
            approvals_pending += 1

    at_risk = sum(e["amount_paise"] for e in events)
    summary = {
        "n_events": len(events),
        "seed": seed,
        "use_ai": use_ai,
        "dry_run": dry_run,
        "revenue_at_risk_paise": at_risk,
        "recovered_paise": recovered_paise,
        "recovered_count": recovered_count,
        "approval_pending": approvals_pending,
        "statuses": dict(statuses),
        "actions": dict(actions),
        "causes": dict(causes),
        "recovery_rate_pct": round(recovered_paise / at_risk * 100, 1) if at_risk else 0.0,
        "label": "modeled result on synthetic data",
    }
    if record:
        db.insert_simulation_run({
            "simulation_run_id": f"sim_{uuid.uuid4().hex[:10]}",
            "merchant_id": settings.default_merchant_id,
            "random_seed": seed,
            "dataset_version": DATASET_VERSION,
            "agent_version": AGENT_VERSION,
            "policy_version": POLICY_VERSION,
            "n_events": n_events,
            "use_ai": use_ai,
            "dry_run": dry_run,
            "baseline": None,
            "treatment": summary,
        })
    return summary


def run_simulation(*, n_events: int = 200, seed: int | None = None) -> dict:
    """Baseline (deterministic rules) vs treatment (agentic), same seed +
    distribution. Honest labelling per §3.14 — no causal claims.

    Note: without ANTHROPIC_API_KEY the treatment falls back to the same
    deterministic engine, so both arms legitimately match."""
    seed = seed if seed is not None else 7
    baseline = run_batch(n_events=n_events, dry_run=True, use_ai=False,
                         seed=seed, record=False)
    treatment = run_batch(n_events=n_events, dry_run=True, use_ai=True,
                          seed=seed, record=False)
    lift = round(treatment["recovery_rate_pct"] - baseline["recovery_rate_pct"], 2)

    run_id = f"sim_{uuid.uuid4().hex[:10]}"
    db.insert_simulation_run({
        "simulation_run_id": run_id,
        "merchant_id": settings.default_merchant_id,
        "random_seed": seed,
        "dataset_version": DATASET_VERSION,
        "agent_version": AGENT_VERSION,
        "policy_version": POLICY_VERSION,
        "n_events": n_events,
        "use_ai": True,
        "dry_run": True,
        "baseline": baseline,
        "treatment": treatment,
    })
    return {
        "simulation_run_id": run_id,
        "random_seed": seed,
        "baseline": baseline,
        "treatment": treatment,
        "modeled_incremental_lift_pct_points": lift,
        "label": "modeled incremental lift — not a measured causal effect",
        "ai_active_in_treatment": settings.ai_configured,
    }
