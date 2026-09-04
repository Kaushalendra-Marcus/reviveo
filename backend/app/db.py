"""Data access layer — the ONLY module that talks to the database.

All SQL lives here (doc §0). Everything is raw parameterized SQL against SQLite;
swapping to Postgres later touches only `_connect()` and a few dialect details,
never the callers. Money is stored in paise (INTEGER).
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger("reviveo.customers")

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
    _migrate_existing_dbs()


def _migrate_existing_dbs() -> None:
    """Idempotent in-place upgrades for databases created before the current
    schema (CREATE TABLE IF NOT EXISTS never alters an existing table, so new
    nullable columns/indexes need explicit handling). Safe to run on every
    startup: each step checks before touching anything and never rewrites or
    deletes existing rows."""
    cols = {r["name"] for r in _connect().execute("PRAGMA table_info(customers)").fetchall()}
    if "razorpay_customer_id" not in cols:
        execute("ALTER TABLE customers ADD COLUMN razorpay_customer_id TEXT")
    execute("CREATE INDEX IF NOT EXISTS idx_customers_email ON customers (merchant_id, email)")
    execute("CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (merchant_id, phone)")
    execute("CREATE INDEX IF NOT EXISTS idx_customers_rzp ON customers (merchant_id, razorpay_customer_id)")
    # Identity-chain columns (§8/§10/§16): nullable ADD COLUMNs never touch
    # existing rows; indexes are created here (never in schema.sql) so the
    # startup executescript cannot fail on pre-existing tables.
    attempt_cols = {r["name"] for r in _connect().execute("PRAGMA table_info(recovery_attempts)").fetchall()}
    if "customer_id" not in attempt_cols:
        execute("ALTER TABLE recovery_attempts ADD COLUMN customer_id TEXT")
    execute("CREATE INDEX IF NOT EXISTS idx_attempts_customer ON recovery_attempts (merchant_id, customer_id)")
    notif_cols = {r["name"] for r in _connect().execute("PRAGMA table_info(notifications)").fetchall()}
    if "customer_id" not in notif_cols:
        execute("ALTER TABLE notifications ADD COLUMN customer_id TEXT")
    if "provider" not in notif_cols:
        execute("ALTER TABLE notifications ADD COLUMN provider TEXT")
    execute("CREATE INDEX IF NOT EXISTS idx_notifications_customer ON notifications (merchant_id, customer_id)")


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
           (id, merchant_id, name, email, phone, razorpay_customer_id,
            total_recovered_paise, failed_payment_count, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (c["id"], c["merchant_id"], c["name"], c.get("email"), c.get("phone"),
         c.get("razorpay_customer_id"),
         c.get("total_recovered_paise", 0), c.get("failed_payment_count", 0),
         c.get("created_at", now_iso())),
    )


def get_customer(merchant_id: str, customer_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM customers WHERE merchant_id=? AND id=?",
        (merchant_id, customer_id),
    )


def get_customer_by_email(merchant_id: str, email: str) -> Optional[dict]:
    """Case-insensitive exact email match within one merchant's scope."""
    return query_one(
        "SELECT * FROM customers WHERE merchant_id=? AND LOWER(email)=LOWER(?)",
        (merchant_id, email),
    )


def get_customer_by_phone(merchant_id: str, phone: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM customers WHERE merchant_id=? AND phone=?",
        (merchant_id, phone),
    )


def get_customer_by_razorpay_id(merchant_id: str, razorpay_customer_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM customers WHERE merchant_id=? AND razorpay_customer_id=?",
        (merchant_id, razorpay_customer_id),
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


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Razorpay test-mode placeholder identities CONFIRMED from live
# payment.failed payloads (evt_420edad734e64f08 carried
# "email": "void@razorpay.com" in the payment entity). These are Razorpay's
# own dummy values — never a real payer address — so they must never become
# a Reviveo customer email nor a notification recipient. Keep this set to
# exactly-confirmed values only: no giant blacklist, no pattern rules that
# could reject legitimate customer addresses (e.g. customer@example.com
# must keep working). Add a value here only with payload evidence.
PLACEHOLDER_EMAILS = frozenset({"void@razorpay.com"})


def is_placeholder_email(value: Any) -> bool:
    """True for known Razorpay/test placeholder identities. Case-insensitive
    exact match against confirmed values only."""
    return (isinstance(value, str) and value.strip().lower() in PLACEHOLDER_EMAILS)


def trusted_email(value: Any) -> Optional[str]:
    """A normalized email safe to store and send to: valid format AND NOT a
    known placeholder. Returns None otherwise — callers must treat None as
    'no usable email', never fall back to the raw value."""
    clean = normalize_email(value)
    if clean is None or is_placeholder_email(clean):
        return None
    return clean


def normalize_email(value: Any) -> Optional[str]:
    """Lowercased/stripped email, or None when it is not a plausible address.
    Never invents data — garbage in yields None, never a placeholder."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned if _EMAIL_RE.match(cleaned) else None


def normalize_phone(value: Any) -> Optional[str]:
    """Stripped phone (spaces/dashes/parens removed), or None when it does
    not look like a real dialable number. Never invents data."""
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[\s\-()]", "", value.strip())
    if not re.fullmatch(r"\+?\d{7,15}", cleaned):
        return None
    return cleaned


def _backfill_customer_contact(row: dict, *, email: Optional[str],
                               phone: Optional[str],
                               razorpay_customer_id: Optional[str]) -> dict:
    """Fill only EMPTY-or-placeholder contact fields on an existing customer.

    Trust rules (a placeholder must never override a real address):
    - `email` must already be trusted (use `trusted_email()` before calling);
      it is written only when the stored email is missing or itself a known
      placeholder. A stored trusted email is NEVER overwritten.
    - phone / razorpay id fill empty fields only, never overwrite.
    """
    updates: dict[str, Any] = {}
    stored_email = (row.get("email") or "").strip()
    if email and (not stored_email or is_placeholder_email(stored_email)):
        if stored_email.lower() != email.lower():
            updates["email"] = email
    if phone and not (row.get("phone") or "").strip():
        updates["phone"] = phone
    if razorpay_customer_id and not (row.get("razorpay_customer_id") or "").strip():
        updates["razorpay_customer_id"] = razorpay_customer_id
    if updates:
        cols = ", ".join(f"{k}=?" for k in updates)
        execute(f"UPDATE customers SET {cols} WHERE merchant_id=? AND id=?",
                (*updates.values(), row["merchant_id"], row["id"]))
        row = get_customer(row["merchant_id"], row["id"]) or row
    return row


def resolve_webhook_customer(
    merchant_id: str,
    *,
    email: Any = None,
    phone: Any = None,
    razorpay_customer_id: Any = None,
    name: Any = None,
    extra_contacts: Iterable[tuple[str, Any, Any]] = (),
    linked_customer_id: Optional[str] = None,
) -> Optional[dict]:
    """Idempotent webhook customer correlation with trusted-email priority.

    `extra_contacts` carries higher-trust contact from payload objects that
    outrank the raw payment-entity contact: an iterable of
    `(source, email, phone)` where source is e.g. `"payment_link"`,
    `"order"`, or `"notes"`. `linked_customer_id` pins CASE B (a failed
    recovery payment whose notes carry Reviveo's own recovery_attempt_id /
    event_id): the already-known recovery customer wins outright — no new
    customer is created just because the entity email differs. Callers must
    pass merchant_id from server-side context, never from the request body.

    Resolution order (a placeholder email never overrides a real one):
      0. pinned linked customer (CASE B recovery correlation)
      1. existing customer with a trusted email (extras first, then entity)
      2. existing customer matched by phone (extras, then entity)
      3. stored Razorpay customer-id mapping
      4. trusted extra (link/order/notes) email → reuse or minimal create
      5. entity email, but ONLY when trusted (not a placeholder)
      6. phone-only record when a valid phone exists but no trusted email
      7. None → caller must keep the notification skipped

    Returns the customer row, or None when the payload carries no usable
    contact information. NEVER invents an email, name, or phone number;
    NEVER stores a placeholder as a customer email.
    """
    rzp_id = razorpay_customer_id.strip() if isinstance(razorpay_customer_id, str) and razorpay_customer_id.strip() else None
    entity_email_raw = email
    entity_phone = normalize_phone(phone)

    # Trusted extras first — these outrank the raw entity contact.
    extras: list[tuple[str, Optional[str], Optional[str]]] = []
    for source, ex_email, ex_phone in (extra_contacts or ()):
        t_email = trusted_email(ex_email)
        t_phone = normalize_phone(ex_phone)
        if t_email or t_phone:
            extras.append((str(source), t_email, t_phone))

    entity_trusted = trusted_email(entity_email_raw)
    if entity_email_raw is not None and entity_trusted is None and normalize_email(entity_email_raw):
        logger.info("placeholder email rejected", extra={"context": {
            "merchant_id": merchant_id,
            "recipient_domain": _domain_of(entity_email_raw),
            "email_source": "placeholder_rejected"}})

    def _matched(row: Optional[dict], source: str) -> Optional[dict]:
        if row is None:
            return None
        best_email = next((e for _, e, _ in extras if e), None) or entity_trusted
        best_phone = entity_phone or next((p for _, _, p in extras if p), None)
        row = _backfill_customer_contact(row, email=best_email,
                                         phone=best_phone,
                                         razorpay_customer_id=rzp_id)
        logger.info("customer matched", extra={"context": {
            "merchant_id": merchant_id, "customer_id": row["id"],
            "email_source": source,
            "recipient_domain": _domain_of(row.get("email"))}})
        return row

    # 0 — CASE B pin: notes-referenced recovery customer (merchant-scoped).
    if linked_customer_id:
        pinned = get_customer(merchant_id, linked_customer_id)
        if pinned is not None:
            return _matched(pinned, "recovery_attempt")

    # 1 — existing customer with a trusted email (extras outrank entity).
    for src, t_email, _ in extras:
        if t_email:
            row = _matched(get_customer_by_email(merchant_id, t_email),
                           "existing_customer_email")
            if row:
                return row
    if entity_trusted:
        row = _matched(get_customer_by_email(merchant_id, entity_trusted),
                       "existing_customer_email")
        if row:
            return row

    # 2 — phone match (extras, then entity).
    for src, _, t_phone in extras:
        if t_phone:
            row = _matched(get_customer_by_phone(merchant_id, t_phone),
                           "existing_customer_phone")
            if row:
                return row
    if entity_phone:
        row = _matched(get_customer_by_phone(merchant_id, entity_phone),
                       "existing_customer_phone")
        if row:
            return row

    # 3 — stored Razorpay customer-id mapping.
    if rzp_id:
        row = _matched(get_customer_by_razorpay_id(merchant_id, rzp_id),
                       "razorpay_customer")
        if row:
            return row

    # 4/5 — minimal record from REAL data only (trusted extras first).
    create_email = next((e for _, e, _ in extras if e), None) or entity_trusted
    create_source = next((s for s, e, _ in extras if e), None) or "payment_entity"
    create_phone = entity_phone or next((p for _, _, p in extras if p), None)
    if create_email or create_phone:
        if create_email:
            row = get_customer_by_email(merchant_id, create_email)
            if row:
                return _matched(row, "existing_customer_email")
        if create_phone:
            row = get_customer_by_phone(merchant_id, create_phone)
            if row:
                return _matched(row, "existing_customer_phone")
        display_name = (name.strip() if isinstance(name, str) and name.strip()
                        else create_email or create_phone or rzp_id)
        customer_id = f"cust_{uuid.uuid4().hex[:12]}"
        try:
            execute(
                """INSERT INTO customers
                   (id, merchant_id, name, email, phone, razorpay_customer_id,
                    total_recovered_paise, failed_payment_count, created_at)
                   VALUES (?,?,?,?,?,?,0,0,?)""",
                (customer_id, merchant_id, display_name, create_email, create_phone,
                 rzp_id, now_iso()),
            )
        except sqlite3.IntegrityError:
            pass  # lost a create race — fall through to the re-check below
        for lookup in (lambda: get_customer_by_email(merchant_id, create_email) if create_email else None,
                       lambda: get_customer_by_phone(merchant_id, create_phone) if create_phone else None,
                       lambda: get_customer_by_razorpay_id(merchant_id, rzp_id) if rzp_id else None,
                       lambda: get_customer(merchant_id, customer_id)):
            row = lookup()
            if row:
                logger.info("customer created", extra={"context": {
                    "merchant_id": merchant_id, "customer_id": row["id"],
                    "email_source": create_source,
                    "recipient_domain": _domain_of(row.get("email"))}})
                return row

    # 6 — genuinely no usable contact: no customer, no email, no send.
    logger.info("customer resolution found no usable contact", extra={"context": {
        "merchant_id": merchant_id, "email_source": "none"}})
    return None


def _domain_of(value: Any) -> str:
    if isinstance(value, str) and "@" in value:
        return value.split("@")[-1].lower() or "unknown"
    return "unknown"


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
                cause: Optional[str] = None, origin: Optional[str] = None,
                limit: int = 20, offset: int = 0) -> list[dict]:
    where = ["merchant_id=?"]
    params: list[Any] = [merchant_id]
    if status:
        where.append("status=?"); params.append(status)
    if cause:
        where.append("cause=?"); params.append(cause)
    if origin:
        where.append("origin=?"); params.append(origin)
    clause = " AND ".join(where)
    return query_all(
        f"SELECT * FROM events WHERE {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )


def count_events(merchant_id: str, *, status: Optional[str] = None,
                 cause: Optional[str] = None, origin: Optional[str] = None) -> int:
    where = ["merchant_id=?"]
    params: list[Any] = [merchant_id]
    if status:
        where.append("status=?"); params.append(status)
    if cause:
        where.append("cause=?"); params.append(cause)
    if origin:
        where.append("origin=?"); params.append(origin)
    clause = " AND ".join(where)
    return query_one(f"SELECT COUNT(*) n FROM events WHERE {clause}",
                     params)["n"]  # type: ignore[index]


def stale_waiting_events(merchant_id: str, cutoff: str) -> list[dict]:
    """Events stuck in 'waiting_for_outcome' whose recovery window has
    already elapsed with no outcome webhook ever arriving — the scheduler's
    stale-attempt sweep uses this to finally resolve them to 'expired'
    instead of showing indefinitely pending on the dashboard."""
    return query_all(
        "SELECT * FROM events WHERE merchant_id=? AND status='waiting_for_outcome' "
        "AND created_at<?",
        (merchant_id, cutoff),
    )


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


def list_decisions_for_event(event_id: str) -> list[dict]:
    return query_all("SELECT * FROM decisions WHERE event_id=? ORDER BY id", (event_id,))


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
           (recovery_attempt_id, event_id, merchant_id, customer_id, attempt_number, action,
            execution_mechanism, amount_paise, status, execution_mode, razorpay_ref,
            reference_id, notes_json, scheduled_for, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["recovery_attempt_id"], a["event_id"], a["merchant_id"],
         a.get("customer_id"), a["attempt_number"], a["action"], a["execution_mechanism"],
         a["amount_paise"], a.get("status", "pending"),
         a.get("execution_mode", "dry_run"), a.get("razorpay_ref"),
         a.get("reference_id"), json.dumps(a.get("notes", {})),
         a.get("scheduled_for"), now_iso()),
    )


def get_recovery_attempt(recovery_attempt_id: str) -> Optional[dict]:
    row = query_one(
        "SELECT * FROM recovery_attempts WHERE recovery_attempt_id=?",
        (recovery_attempt_id,),
    )
    if row:
        notes = json.loads(row.pop("notes_json") or "{}")
        row["short_url"] = notes.get("short_url")
    return row


def get_attempt_by_reference(reference_id: str) -> Optional[dict]:
    return query_one(
        "SELECT * FROM recovery_attempts WHERE reference_id=?", (reference_id,)
    )


def list_attempts_for_event(event_id: str) -> list[dict]:
    rows = query_all(
        "SELECT * FROM recovery_attempts WHERE event_id=? ORDER BY attempt_number",
        (event_id,),
    )
    for r in rows:
        notes = json.loads(r.pop("notes_json") or "{}")
        r["short_url"] = notes.get("short_url")
    return rows


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


# ── notifications ─────────────────────────────────────────────────────────────
def insert_notification(n: dict) -> bool:
    """Returns True if newly inserted, False if (recovery_attempt_id, channel) already exists."""
    try:
        execute(
            """INSERT INTO notifications
               (notification_id, merchant_id, event_id, recovery_attempt_id,
                customer_id, channel, recipient, subject, body, status, provider,
                provider_message_id, created_at, sent_at, error, ai_generated,
                ai_model, ai_latency_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (n["notification_id"], n["merchant_id"], n["event_id"],
             n["recovery_attempt_id"], n.get("customer_id"),
             n.get("channel", "email"), n["recipient"],
             n.get("subject"), n["body"], n.get("status", "sent"),
             n.get("provider"), n.get("provider_message_id"),
             n.get("created_at") or now_iso(),
             n.get("sent_at"), n.get("error"), int(n.get("ai_generated", 0)),
             n.get("ai_model"), n.get("ai_latency_ms")),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def get_notification_by_attempt(recovery_attempt_id: str, channel: str = "email") -> Optional[dict]:
    return query_one(
        "SELECT * FROM notifications WHERE recovery_attempt_id=? AND channel=?",
        (recovery_attempt_id, channel),
    )


def list_notifications_for_event(event_id: str) -> list[dict]:
    return query_all(
        "SELECT * FROM notifications WHERE event_id=? ORDER BY id",
        (event_id,),
    )


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


def count_all_audit(merchant_id: str) -> int:
    return query_one("SELECT COUNT(*) n FROM audit_log WHERE merchant_id=?",
                     (merchant_id,))["n"]  # type: ignore[index]


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
def summary_metrics(merchant_id: str, since: str, *, until: Optional[str] = None,
                    origin: Optional[str] = None) -> dict:
    """Aggregate metrics for the half-open window [since, until). `until=None`
    means "through now" (the current period) — pass an explicit `until` to
    compute a prior comparison window of equal length (doc A1
    'deltas_vs_previous'). `origin` optionally restricts to a single
    DataOrigin ('synthetic' or 'live_test_mode'); omitted (None) preserves
    the original all-origin behavior (doc §3.14 keeps the two explicitly
    separable without forcing separation by default).
    """
    at_risk_where = "merchant_id=? AND created_at>=?"
    at_risk_params: list[Any] = [merchant_id, since]
    if until:
        at_risk_where += " AND created_at<?"; at_risk_params.append(until)
    if origin:
        at_risk_where += " AND origin=?"; at_risk_params.append(origin)
    at_risk = query_one(
        f"SELECT COALESCE(SUM(amount_paise),0) v, COUNT(*) n FROM events WHERE {at_risk_where}",
        at_risk_params,
    )

    recovered_where = "rp.merchant_id=? AND rp.recovered_at>=?"
    recovered_params: list[Any] = [merchant_id, since]
    if until:
        recovered_where += " AND rp.recovered_at<?"; recovered_params.append(until)
    recovered_join = ""
    if origin:
        recovered_join = " JOIN events e ON e.event_id=rp.event_id"
        recovered_where += " AND e.origin=?"; recovered_params.append(origin)
    recovered = query_one(
        f"SELECT COALESCE(SUM(rp.amount_paise),0) v, COUNT(*) n FROM recovered_payments rp"
        f"{recovered_join} WHERE {recovered_where}",
        recovered_params,
    )

    attempts_where = "ra.merchant_id=? AND ra.created_at>=?"
    attempts_params: list[Any] = [merchant_id, since]
    if until:
        attempts_where += " AND ra.created_at<?"; attempts_params.append(until)
    attempts_join = ""
    if origin:
        attempts_join = " JOIN events e ON e.event_id=ra.event_id"
        attempts_where += " AND e.origin=?"; attempts_params.append(origin)
    actions = query_one(
        f"SELECT COUNT(*) n FROM recovery_attempts ra{attempts_join} WHERE {attempts_where}",
        attempts_params,
    )
    executed_ok = query_one(
        f"SELECT COUNT(*) n FROM recovery_attempts ra{attempts_join} WHERE {attempts_where} "
        f"AND ra.status IN ('recovered','awaiting_outcome')",
        attempts_params,
    )
    return {
        "revenue_at_risk_paise": at_risk["v"],       # type: ignore[index]
        "events_processed": at_risk["n"],            # type: ignore[index]
        "recovered_paise": recovered["v"],           # type: ignore[index]
        "recovered_count": recovered["n"],           # type: ignore[index]
        "actions_executed": actions["n"],            # type: ignore[index]
        "actions_succeeded": executed_ok["n"],       # type: ignore[index]
    }


def timeseries_recovered(merchant_id: str, since: str, *, origin: Optional[str] = None) -> list[dict]:
    join = " JOIN events e ON e.event_id=rp.event_id" if origin else ""
    where = "rp.merchant_id=? AND rp.recovered_at>=?"
    params: list[Any] = [merchant_id, since]
    if origin:
        where += " AND e.origin=?"; params.append(origin)
    return query_all(
        f"SELECT substr(rp.recovered_at,1,10) day, COALESCE(SUM(rp.amount_paise),0) amount_paise, "
        f"COUNT(*) count FROM recovered_payments rp{join} WHERE {where} "
        f"GROUP BY day ORDER BY day",
        params,
    )


def timeseries_at_risk(merchant_id: str, since: str, *, origin: Optional[str] = None) -> list[dict]:
    where = "merchant_id=? AND created_at>=?"
    params: list[Any] = [merchant_id, since]
    if origin:
        where += " AND origin=?"; params.append(origin)
    return query_all(
        f"SELECT substr(created_at,1,10) day, COALESCE(SUM(amount_paise),0) amount_paise, "
        f"COUNT(*) count FROM events WHERE {where} "
        f"GROUP BY day ORDER BY day",
        params,
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
