"""Idempotent seed data: the default demo merchant, guardrail config, and a set
of synthetic customers/subscriptions (doc demo: CodeCraft, customer Rahul, etc.).
Runs on startup; safe to call repeatedly.
"""
from __future__ import annotations

from . import db
from .config import settings

_DEMO_CUSTOMERS = [
    ("cust_rahul", "Rahul Sharma", "rahul@example.com", "+919000000001", 249900),
    ("cust_priya", "Priya Nair", "priya@example.com", "+919000000002", 99900),
    ("cust_amit", "Amit Verma", "amit@example.com", "+919000000003", 249900),
    ("cust_sara", "Sara Khan", "sara@example.com", "+919000000004", 99900),
    ("cust_dev", "Dev Patel", "dev@example.com", "+919000000005", 499900),
    ("cust_neha", "Neha Gupta", "neha@example.com", "+919000000006", 99900),
]

_DEFAULT_GUARDRAILS = {
    "environment": "test",
    "recovery_window_days": 7,
    "high_confidence": 0.85,
    "low_confidence": 0.50,
    "max_retries": 3,
    "cooldown_hours": 24,
    "max_autonomous_recovery_amount_paise": 500000,   # ₹5,000
    "daily_recovery_value_cap_paise": 5000000,        # ₹50,000
    "daily_contact_cap": 100,
    "allowed_channels": ["email", "payment_link"],
}


def ensure_seed() -> None:
    mid = settings.default_merchant_id
    db.ensure_merchant(mid, "CodeCraft")
    if db.get_guardrail_config(mid) is None:
        db.upsert_guardrail_config(mid, dict(_DEFAULT_GUARDRAILS))
    if db.count_customers(mid) == 0:
        for cid, name, email, phone, amt in _DEMO_CUSTOMERS:
            db.insert_customer({"id": cid, "merchant_id": mid, "name": name,
                                "email": email, "phone": phone})
            db.insert_subscription({"id": f"sub_{cid}", "merchant_id": mid,
                                    "customer_id": cid, "plan_name": "Pro Monthly",
                                    "amount_paise": amt, "state": "active"})
