"""Data access layer — the ONLY module that talks to the database.

All SQL lives here (doc §0). Everything is raw parameterized SQL against SQLite;
swapping to Postgres later touches only `_connect()` and a few dialect details,
never the callers. Money is stored in paise (INTEGER).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_local = threading.local()


def _connect() -> sqlite3.Connection:
    """One connection per thread. Swap this for a Postgres pool later."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.database_url, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


# ── low-level helpers ────────────────────────────────────────────────────────
def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = _connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    cur = _connect().execute(sql, tuple(params))
    return _row_to_dict(cur.fetchone())


def query_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    cur = _connect().execute(sql, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def init_db() -> None:
    """Create tables if absent. Idempotent."""
    conn = _connect()
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.commit()


# ── merchants ────────────────────────────────────────────────────────────────
def ensure_merchant(merchant_id: str, name: str) -> None:
    execute(
        "INSERT OR IGNORE INTO merchants (merchant_id, name, created_at) VALUES (?,?,?)",
        (merchant_id, name, now_iso()),
    )


# ── guardrail config ──────────────────────────────────────────────────────────
def get_guardrail_config(merchant_id: str) -> Optional[dict]:
    row = query_one(
        "SELECT * FROM guardrail_config WHERE merchant_id=?", (merchant_id,)
    )
    if row:
        row["allowed_channels"] = json.loads(row.pop("allowed_channels_json"))
    return row


def upsert_guardrail_config(merchant_id: str, cfg: dict) -> dict:
    channels = json.dumps(cfg.get("allowed_channels", ["email", "payment_link"]))
    execute(
        """INSERT INTO guardrail_config
            (merchant_id, environment, recovery_window_days, high_confidence,
             low_confidence, max_retries, cooldown_hours,
             max_autonomous_recovery_amount_paise, daily_recovery_value_cap_paise,
             daily_contact_cap, allowed_channels_json, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(merchant_id) DO UPDATE SET
             environment=excluded.environment,
             recovery_window_days=excluded.recovery_window_days,
             high_confidence=excluded.high_confidence,
             low_confidence=excluded.low_confidence,
             max_retries=excluded.max_retries,
             cooldown_hours=excluded.cooldown_hours,
             max_autonomous_recovery_amount_paise=excluded.max_autonomous_recovery_amount_paise,
             daily_recovery_value_cap_paise=excluded.daily_recovery_value_cap_paise,
             daily_contact_cap=excluded.daily_contact_cap,
             allowed_channels_json=excluded.allowed_channels_json,
             updated_at=excluded.updated_at""",
        (
            merchant_id, cfg["environment"], cfg["recovery_window_days"],
            cfg["high_confidence"], cfg["low_confidence"], cfg["max_retries"],
            cfg["cooldown_hours"], cfg["max_autonomous_recovery_amount_paise"],
            cfg["daily_recovery_value_cap_paise"], cfg["daily_contact_cap"],
            channels, now_iso(),
        ),
    )
    return get_guardrail_config(merchant_id)  # type: ignore[return-value]


# ── daily counters (reset by date key) ────────────────────────────────────────
def get_daily_counter(merchant_id: str, day: Optional[str] = None) -> dict:
    day = day or today_utc()
    row = query_one(
        "SELECT * FROM daily_counters WHERE merchant_id=? AND day=?",
        (merchant_id, day),
    )
    return row or {"merchant_id": merchant_id, "day": day,
                   "recovery_value_paise": 0, "contact_count": 0}


def incr_daily_counter(merchant_id: str, *, value_paise: int = 0,
                       contacts: int = 0, day: Optional[str] = None) -> None:
    day = day or today_utc()
    execute(
        """INSERT INTO daily_counters (merchant_id, day, recovery_value_paise, contact_count)
           VALUES (?,?,?,?)
           ON CONFLICT(merchant_id, day) DO UPDATE SET
             recovery_value_paise = recovery_value_paise + excluded.recovery_value_paise,
             contact_count = contact_count + excluded.contact_count""",
        (merchant_id, day, value_paise, contacts),
    )


# ── customers ─────────────────────────────────────────────────────────────────
def insert_customer(c: dict) -> None:
    execute(
        """INSERT OR REPLACE INTO customers
           (id, merchant_id, name, email, phone, total_recovered_paise,
            failed_payment_count, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (c["id"], c["merchant_id"], c["name"], c.get("email"), c.get("phone"),
         c.get("total_recovered_paise", 0), c.get("failed_payment_count", 0),
         c.get("created_at", now_iso())),
    )


def get_customer(merchant_id: str, customer_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM customers WHERE merchant_id=? AND id=?",
        (merchant_id, customer_id),
    )


def list_customers(merchant_id: str, limit: int, offset: int) -> list[dict]:
    return query_all(
        "SELECT * FROM customers WHERE merchant_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (merchant_id, limit, offset),
    )


def count_customers(merchant_id: str) -> int:
    return query_one("SELECT COUNT(*) n FROM customers WHERE merchant_id=?",
                     (merchant_id,))["n"]  # type: ignore[index]


def add_customer_recovered(merchant_id: str, customer_id: str, amount_paise: int) -> None:
    execute(
        "UPDATE customers SET total_recovered_paise = total_recovered_paise + ? "
        "WHERE merchant_id=? AND id=?",
        (amount_paise, merchant_id, customer_id),
    )


def incr_customer_failed_count(merchant_id: str, customer_id: str) -> None:
    execute(
        "UPDATE customers SET failed_payment_count = failed_payment_count + 1 "
        "WHERE merchant_id=? AND id=?",
        (merchant_id, customer_id),
    )


# ── subscriptions ─────────────────────────────────────────────────────────────
def insert_subscription(s: dict) -> None:
    execute(
        """INSERT OR REPLACE INTO subscriptions
           (id, merchant_id, customer_id, plan_name, amount_paise, state, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (s["id"], s["merchant_id"], s["customer_id"], s.get("plan_name"),
         s["amount_paise"], s.get("state", "active"), s.get("created_at", now_iso())),
    )


def get_subscription(sub_id: str) -> Optional[dict]:
    return query_one("SELECT * FROM subscriptions WHERE id=?", (sub_id,))


def update_subscription_state(sub_id: str, state: str) -> None:
    execute("UPDATE subscriptions SET state=? WHERE id=?", (state, sub_id))


# ── events ────────────────────────────────────────────────────────────────────
def insert_event(e: dict) -> None:
    execute(
        """INSERT INTO events
           (event_id, merchant_id, customer_id, subscription_id, invoice_id, type,
            cause, error_code, amount_paise, status, subscription_state_before,
            subscription_state_after, payment_recovered, subscription_restored,
            origin, razorpay_payment_id, decision_expires_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (e["event_id"], e["merchant_id"], e.get("customer_id"),
         e.get("subscription_id"), e.get("invoice_id"), e["type"], e.get("cause"),
         e.get("error_code"), e.get("amount_paise", 0), e["status"],
         e.get("subscription_state_before"), e.get("subscription_state_after"),
         int(e.get("payment_recovered", 0)), int(e.get("subscription_restored", 0)),
         e.get("origin", "synthetic"), e.get("razorpay_payment_id"),
         e.get("decision_expires_at"), e.get("created_at", now_iso()), now_iso()),
    )


def get_event(event_id: str) -> Optional[dict]:
    return query_one("SELECT * FROM events WHERE event_id=?", (event_id,))


def update_event(event_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k}=?" for k in fields)
    execute(f"UPDATE events SET {cols} WHERE event_id=?",
            (*fields.values(), event_id))


def list_events(merchant_id: str, *, status: Optional[str] = None,
                cause: Optional[str] = None, limit: int = 20,
                offset: int = 0) -> list[dict]:
    where = ["merchant_id=?"]
    params: list[Any] = [merchant_id]
    if status:
        where.append("status=?"); params.append(status)
    if cause:
        where.append("cause=?"); params.append(cause)
    clause = " AND ".join(where)
    return query_all(
        f"SELECT * FROM events WHERE {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )


def count_events(merchant_id: str, *, status: Optional[str] = None,
                 cause: Optional[str] = None) -> int:
    where = ["merchant_id=?"]
    params: list[Any] = [merchant_id]
    if status:
        where.append("status=?"); params.append(status)
    if cause:
        where.append("cause=?"); params.append(cause)
    clause = " AND ".join(where)
    return query_one(f"SELECT COUNT(*) n FROM events WHERE {clause}",
                     params)["n"]  # type: ignore[index]


# ── decisions ─────────────────────────────────────────────────────────────────
def insert_decision(d: dict) -> int:
    cur = execute(
        """INSERT INTO decisions
           (event_id, merchant_id, action, execution_mechanism, confidence,
            risk_tier, requires_approval, reasoning, ai_used, policy_version,
            decision_expires_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d["event_id"], d["merchant_id"], d["action"], d.get("execution_mechanism"),
         d["confidence"], d["risk_tier"], int(d.get("requires_approval", 0)),
         d.get("reasoning"), int(d.get("ai_used", 0)), d.get("policy_version"),
         d.get("decision_expires_at"), now_iso()),
    )
    return cur.lastrowid


def get_latest_decision(event_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM decisions WHERE event_id=? ORDER BY id DESC LIMIT 1",
        (event_id,),
    )


# ── recovery attempts ─────────────────────────────────────────────────────────
def next_attempt_number(event_id: str) -> int:
    row = query_one(
        "SELECT COALESCE(MAX(attempt_number),0) m FROM recovery_attempts WHERE event_id=?",
        (event_id,),
    )
    return int(row["m"]) + 1  # type: ignore[index]


def count_attempts(event_id: str) -> int:
    return query_one(
        "SELECT COUNT(*) n FROM recovery_attempts WHERE event_id=?", (event_id,)
    )["n"]  # type: ignore[index]


def insert_recovery_attempt(a: dict) -> None:
    execute(
        """INSERT INTO recovery_attempts
           (recovery_attempt_id, event_id, merchant_id, attempt_number, action,
            execution_mechanism, amount_paise, status, execution_mode, razorpay_ref,
            reference_id, notes_json, scheduled_for, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["recovery_attempt_id"], a["event_id"], a["merchant_id"],
         a["attempt_number"], a["action"], a["execution_mechanism"],
         a["amount_paise"], a.get("status", "pending"),
         a.get("execution_mode", "dry_run"), a.get("razorpay_ref"),
         a.get("reference_id"), json.dumps(a.get("notes", {})),
         a.get("scheduled_for"), now_iso()),
    )


def get_recovery_attempt(recovery_attempt_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM recovery_attempts WHERE recovery_attempt_id=?",
        (recovery_attempt_id,),
    )


def get_attempt_by_reference(reference_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM recovery_attempts WHERE reference_id=?", (reference_id,)
    )


def list_attempts_for_event(event_id: str) -> list[dict]:
    return query_all(
        "SELECT * FROM recovery_attempts WHERE event_id=? ORDER BY attempt_number",
        (event_id,),
    )


def update_recovery_attempt(recovery_attempt_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    execute(f"UPDATE recovery_attempts SET {cols} WHERE recovery_attempt_id=?",
            (*fields.values(), recovery_attempt_id))


def last_attempt_time(event_id: str, *, exclude: Optional[str] = None) -> Optional[str]:
    if exclude:
        row = query_one(
            "SELECT MAX(created_at) t FROM recovery_attempts "
            "WHERE event_id=? AND recovery_attempt_id != ?",
            (event_id, exclude),
        )
    else:
        row = query_one(
            "SELECT MAX(created_at) t FROM recovery_attempts WHERE event_id=?",
            (event_id,),
        )
    return row["t"] if row else None  # type: ignore[index]


# ── recovered payments (idempotent by razorpay payment id) ────────────────────
def insert_recovered_payment(p: dict) -> bool:
    """Returns True if newly inserted, False if the payment id already existed."""
    try:
        execute(
            """INSERT INTO recovered_payments
               (event_id, merchant_id, recovery_attempt_id,
                recovered_razorpay_payment_id, amount_paise, within_window, recovered_at)
               VALUES (?,?,?,?,?,?,?)""",
            (p["event_id"], p["merchant_id"], p["recovery_attempt_id"],
             p["recovered_razorpay_payment_id"], p["amount_paise"],
             int(p["within_window"]), now_iso()),
        )
        return True
    except sqlite3.IntegrityError:
        return False


# ── pending approvals ─────────────────────────────────────────────────────────
def insert_approval(a: dict) -> int:
    cur = execute(
        """INSERT INTO pending_approvals
           (merchant_id, event_id, recovery_attempt_id, proposed_action,
            execution_mechanism, amount_paise, reason, ai_summary, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (a["merchant_id"], a["event_id"], a.get("recovery_attempt_id"),
         a["proposed_action"], a.get("execution_mechanism"), a["amount_paise"],
         a.get("reason"), a.get("ai_summary"), a.get("status", "pending"), now_iso()),
    )
    return cur.lastrowid


def get_approval(approval_id: int) -> Optional[dict]:
    return query_one("SELECT * FROM pending_approvals WHERE id=?", (approval_id,))


def list_pending_approvals(merchant_id: str) -> list[dict]:
    return query_all(
        "SELECT * FROM pending_approvals WHERE merchant_id=? AND status='pending' "
        "ORDER BY created_at",
        (merchant_id,),
    )


def set_approval_status(approval_id: int, from_status: str, to_status: str,
                        resolved_by: Optional[str] = None) -> bool:
    """Atomic state transition (doc §3.12). Returns True iff exactly one row moved,
    so double-clicks / concurrent reviewers cannot trigger duplicate execution."""
    resolved = now_iso() if to_status in ("approved", "denied", "expired",
                                          "executed", "execution_failed") else None
    cur = execute(
        "UPDATE pending_approvals SET status=?, resolved_at=COALESCE(?, resolved_at), "
        "resolved_by=COALESCE(?, resolved_by) WHERE id=? AND status=?",
        (to_status, resolved, resolved_by, approval_id, from_status),
    )
    return cur.rowcount == 1


# ── audit log ─────────────────────────────────────────────────────────────────
def insert_audit(a: dict) -> None:
    execute(
        """INSERT INTO audit_log
           (event_id, merchant_id, stage, message, payload_json, ai_used, ai_model,
            ai_latency_ms, fallback_triggered, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (a["event_id"], a["merchant_id"], a["stage"], a.get("message"),
         json.dumps(a.get("payload", {}), default=str), int(a.get("ai_used", 0)),
         a.get("ai_model"), a.get("ai_latency_ms"),
         int(a.get("fallback_triggered", 0)), now_iso()),
    )


def list_audit_for_event(event_id: str) -> list[dict]:
    rows = query_all(
        "SELECT * FROM audit_log WHERE event_id=? ORDER BY id", (event_id,)
    )
    for r in rows:
        r["payload"] = json.loads(r.pop("payload_json") or "{}")
    return rows


def list_all_audit(merchant_id: str, limit: int, offset: int) -> list[dict]:
    rows = query_all(
        "SELECT * FROM audit_log WHERE merchant_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
        (merchant_id, limit, offset),
    )
    for r in rows:
        r["payload"] = json.loads(r.pop("payload_json") or "{}")
    return rows


# ── webhook events (idempotency, doc §3.6) ────────────────────────────────────
def try_insert_webhook(merchant_id: str, razorpay_event_id: str,
                       event_name: str, raw_payload: str) -> bool:
    """Insert-if-new. Returns False if this event id was already received
    (dedup by unique x-razorpay-event-id)."""
    try:
        execute(
            """INSERT INTO webhook_events
               (merchant_id, razorpay_event_id, event_name, raw_payload, status,
                attempt_count, received_at)
               VALUES (?,?,?,?, 'received', 1, ?)""",
            (merchant_id, razorpay_event_id, event_name, raw_payload, now_iso()),
        )
        return True
    except sqlite3.IntegrityError:
        execute(
            "UPDATE webhook_events SET attempt_count = attempt_count + 1 "
            "WHERE merchant_id=? AND razorpay_event_id=?",
            (merchant_id, razorpay_event_id),
        )
        return False


def mark_webhook(merchant_id: str, razorpay_event_id: str, status: str,
                 error: Optional[str] = None) -> None:
    execute(
        "UPDATE webhook_events SET status=?, error_message=?, processed_at=? "
        "WHERE merchant_id=? AND razorpay_event_id=?",
        (status, error, now_iso(), merchant_id, razorpay_event_id),
    )


# ── scheduled actions due for revalidation (doc §3.11) ────────────────────────
def due_scheduled_attempts(merchant_id: str, now: Optional[str] = None) -> list[dict]:
    now = now or now_iso()
    return query_all(
        "SELECT * FROM recovery_attempts WHERE merchant_id=? AND status='scheduled' "
        "AND scheduled_for IS NOT NULL AND scheduled_for <= ?",
        (merchant_id, now),
    )


# ── simulation runs ───────────────────────────────────────────────────────────
def insert_simulation_run(r: dict) -> None:
    execute(
        """INSERT INTO simulation_runs
           (simulation_run_id, merchant_id, random_seed, dataset_version,
            agent_version, policy_version, n_events, use_ai, dry_run,
            baseline_json, treatment_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (r["simulation_run_id"], r["merchant_id"], r["random_seed"],
         r["dataset_version"], r["agent_version"], r["policy_version"],
         r["n_events"], int(r.get("use_ai", 0)), int(r.get("dry_run", 1)),
         json.dumps(r.get("baseline")), json.dumps(r.get("treatment")), now_iso()),
    )


def get_last_simulation(merchant_id: str) -> Optional[dict]:
    row = query_one(
        "SELECT * FROM simulation_runs WHERE merchant_id=? ORDER BY created_at DESC LIMIT 1",
        (merchant_id,),
    )
    if row:
        row["baseline"] = json.loads(row.pop("baseline_json") or "null")
        row["treatment"] = json.loads(row.pop("treatment_json") or "null")
    return row


def list_simulations(merchant_id: str, limit: int = 20) -> list[dict]:
    rows = query_all(
        "SELECT * FROM simulation_runs WHERE merchant_id=? ORDER BY created_at DESC LIMIT ?",
        (merchant_id, limit),
    )
    for row in rows:
        row["baseline"] = json.loads(row.pop("baseline_json") or "null")
        row["treatment"] = json.loads(row.pop("treatment_json") or "null")
    return rows


# ── reporting / aggregation ───────────────────────────────────────────────────
def summary_metrics(merchant_id: str, since: str) -> dict:
    at_risk = query_one(
        "SELECT COALESCE(SUM(amount_paise),0) v, COUNT(*) n FROM events "
        "WHERE merchant_id=? AND created_at>=?",
        (merchant_id, since),
    )
    recovered = query_one(
        "SELECT COALESCE(SUM(amount_paise),0) v, COUNT(*) n FROM recovered_payments "
        "WHERE merchant_id=? AND recovered_at>=?",
        (merchant_id, since),
    )
    actions = query_one(
        "SELECT COUNT(*) n FROM recovery_attempts WHERE merchant_id=? AND created_at>=?",
        (merchant_id, since),
    )
    executed_ok = query_one(
        "SELECT COUNT(*) n FROM recovery_attempts WHERE merchant_id=? AND created_at>=? "
        "AND status IN ('recovered','awaiting_outcome')",
        (merchant_id, since),
    )
    return {
        "revenue_at_risk_paise": at_risk["v"],       # type: ignore[index]
        "events_processed": at_risk["n"],            # type: ignore[index]
        "recovered_paise": recovered["v"],           # type: ignore[index]
        "recovered_count": recovered["n"],           # type: ignore[index]
        "actions_executed": actions["n"],            # type: ignore[index]
        "actions_succeeded": executed_ok["n"],       # type: ignore[index]
    }


def timeseries_recovered(merchant_id: str, since: str) -> list[dict]:
    return query_all(
        "SELECT substr(recovered_at,1,10) day, COALESCE(SUM(amount_paise),0) amount_paise, "
        "COUNT(*) count FROM recovered_payments WHERE merchant_id=? AND recovered_at>=? "
        "GROUP BY day ORDER BY day",
        (merchant_id, since),
    )


def timeseries_at_risk(merchant_id: str, since: str) -> list[dict]:
    return query_all(
        "SELECT substr(created_at,1,10) day, COALESCE(SUM(amount_paise),0) amount_paise, "
        "COUNT(*) count FROM events WHERE merchant_id=? AND created_at>=? "
        "GROUP BY day ORDER BY day",
        (merchant_id, since),
    )


def strategy_breakdown(merchant_id: str, since: str) -> list[dict]:
    return query_all(
        """SELECT ra.execution_mechanism mechanism,
                  COUNT(*) attempts,
                  COALESCE(SUM(rp.amount_paise),0) recovered_paise,
                  COUNT(rp.id) recovered_count
           FROM recovery_attempts ra
           LEFT JOIN recovered_payments rp ON rp.recovery_attempt_id = ra.recovery_attempt_id
           WHERE ra.merchant_id=? AND ra.created_at>=?
           GROUP BY ra.execution_mechanism ORDER BY attempts DESC""",
        (merchant_id, since),
    )


def reset_all() -> None:
    """Drop and recreate every table (used by tests and reseed)."""
    conn = _connect()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    init_db()
