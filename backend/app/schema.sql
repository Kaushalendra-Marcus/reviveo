-- Reviveo schema (SQLite). Raw SQL, no ORM (doc §0). All money in paise (INTEGER).
-- Every core table carries merchant_id for SaaS-ready multi-tenancy (doc §3.15).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- Raw inbound webhook envelopes (doc §3.6). Dedup by razorpay_event_id.
CREATE TABLE IF NOT EXISTS webhook_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id        TEXT NOT NULL,
    razorpay_event_id  TEXT NOT NULL,
    event_name         TEXT,
    raw_payload        TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'received', -- received|processed|failed|duplicate
    error_message      TEXT,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    received_at        TEXT NOT NULL,
    processed_at       TEXT,
    UNIQUE (merchant_id, razorpay_event_id)
);

CREATE TABLE IF NOT EXISTS customers (
    id                 TEXT PRIMARY KEY,
    merchant_id        TEXT NOT NULL,
    name               TEXT NOT NULL,
    email              TEXT,
    phone              TEXT,
    -- Razorpay `cust_…` identifier when known (nullable; backfilled from
    -- payment.failed entities and used for correlation before falling back
    -- to minimal-record creation). NULL for seeded/synthetic customers.
    razorpay_customer_id TEXT,
    total_recovered_paise INTEGER NOT NULL DEFAULT 0,
    failed_payment_count  INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers (merchant_id, email);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (merchant_id, phone);
-- NOTE: idx_customers_rzp (on the nullable razorpay_customer_id column) is
-- created by db._migrate_existing_dbs(), not here: CREATE INDEX fails on
-- pre-existing customers tables that do not have the column yet, which would
-- abort the whole executescript on startup. Fresh DBs get it via the same
-- migration, which always runs inside init_db().

CREATE TABLE IF NOT EXISTS subscriptions (
    id                 TEXT PRIMARY KEY,
    merchant_id        TEXT NOT NULL,
    customer_id        TEXT NOT NULL,
    plan_name          TEXT,
    amount_paise       INTEGER NOT NULL,
    state              TEXT NOT NULL DEFAULT 'active',
    created_at         TEXT NOT NULL
);

-- The event is the dashboard source of truth (doc §3.5).
CREATE TABLE IF NOT EXISTS events (
    event_id                   TEXT PRIMARY KEY,
    merchant_id                TEXT NOT NULL,
    customer_id                TEXT,
    subscription_id            TEXT,
    invoice_id                 TEXT,
    type                       TEXT NOT NULL,   -- EventType
    cause                      TEXT,            -- Cause
    error_code                 TEXT,
    amount_paise               INTEGER NOT NULL DEFAULT 0,
    status                     TEXT NOT NULL,   -- EventStatus
    subscription_state_before  TEXT,
    subscription_state_after   TEXT,
    payment_recovered          INTEGER NOT NULL DEFAULT 0,
    subscription_restored      INTEGER NOT NULL DEFAULT 0,
    origin                     TEXT NOT NULL DEFAULT 'synthetic', -- DataOrigin
    razorpay_payment_id        TEXT,
    decision_expires_at        TEXT,
    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_merchant_status ON events (merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_events_created ON events (created_at);

CREATE TABLE IF NOT EXISTS decisions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id           TEXT NOT NULL,
    merchant_id        TEXT NOT NULL,
    action              TEXT NOT NULL,
    execution_mechanism TEXT,
    confidence         REAL NOT NULL,
    risk_tier          TEXT NOT NULL,
    requires_approval  INTEGER NOT NULL DEFAULT 0,
    reasoning          TEXT,
    ai_used            INTEGER NOT NULL DEFAULT 0,
    policy_version     TEXT,
    decision_expires_at TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_event ON decisions (event_id);

-- Explicit recovery chain (doc §3.1). UNIQUE(event_id, attempt_number) prevents
-- double-counting the headline metric.
CREATE TABLE IF NOT EXISTS recovery_attempts (
    recovery_attempt_id TEXT PRIMARY KEY,
    event_id            TEXT NOT NULL,
    merchant_id         TEXT NOT NULL,
    -- Owner of this attempt (copied from events.customer_id at execution
    -- time so the payment → customer → event → attempt → link → notification
    -- chain stays auditable without joins). Nullable for rows written before
    -- this column existed.
    customer_id          TEXT,
    attempt_number      INTEGER NOT NULL,
    action               TEXT NOT NULL,
    execution_mechanism TEXT NOT NULL,
    amount_paise        INTEGER NOT NULL,
    status               TEXT NOT NULL DEFAULT 'pending', -- pending|awaiting_outcome|recovered|expired|failed
    execution_mode       TEXT NOT NULL DEFAULT 'dry_run', -- ExecutionMode
    razorpay_ref         TEXT,   -- payment_link id / order id
    reference_id          TEXT,   -- unique Razorpay Payment Link reference (doc §3.7)
    notes_json            TEXT,   -- carries event_id, recovery_attempt_id, attempt_number
    scheduled_for          TEXT,
    created_at             TEXT NOT NULL,
    resolved_at             TEXT,
    UNIQUE (event_id, attempt_number)
);
CREATE INDEX IF NOT EXISTS idx_attempts_event ON recovery_attempts (event_id);
CREATE INDEX IF NOT EXISTS idx_attempts_ref ON recovery_attempts (reference_id);

-- A payment counts as recovered only via a row here (doc §3.1). UNIQUE on the
-- razorpay payment id so the same confirmed payment can never be counted twice.
CREATE TABLE IF NOT EXISTS recovered_payments (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                      TEXT NOT NULL,
    merchant_id                   TEXT NOT NULL,
    recovery_attempt_id           TEXT NOT NULL,
    recovered_razorpay_payment_id TEXT NOT NULL,
    amount_paise                  INTEGER NOT NULL,
    within_window                 INTEGER NOT NULL,
    recovered_at                  TEXT NOT NULL,
    UNIQUE (recovered_razorpay_payment_id)
);

-- Human approval queue (doc §A2 + §3.12).
CREATE TABLE IF NOT EXISTS pending_approvals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id         TEXT NOT NULL,
    event_id            TEXT NOT NULL,
    recovery_attempt_id TEXT,
    proposed_action     TEXT NOT NULL,
    execution_mechanism TEXT,
    amount_paise        INTEGER NOT NULL,
    reason              TEXT,
    ai_summary          TEXT,
    status              TEXT NOT NULL DEFAULT 'pending', -- ApprovalStatus
    created_at          TEXT NOT NULL,
    resolved_at         TEXT,
    resolved_by         TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON pending_approvals (merchant_id, status);

-- Customer recovery notifications (email/sms). UNIQUE(recovery_attempt_id, channel) ensures idempotency.
CREATE TABLE IF NOT EXISTS notifications (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id      TEXT UNIQUE NOT NULL,
    merchant_id          TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    recovery_attempt_id  TEXT NOT NULL,
    -- Resolution owner (Reviveo customer id the recipient was taken from).
    -- Nullable for rows written before this column existed.
    customer_id          TEXT,
    channel              TEXT NOT NULL DEFAULT 'email', -- email|sms
    recipient            TEXT NOT NULL,
    subject              TEXT,
    body                 TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'sent', -- sent|simulated|failed|skipped
    -- Which provider path produced this row: 'resend' (live Resend API,
    -- including failed attempts) or 'simulated' (synthetic/disabled mode).
    -- NULL for skipped rows, which never reached a provider.
    provider             TEXT,
    provider_message_id  TEXT,
    created_at           TEXT NOT NULL,
    sent_at              TEXT,
    error                TEXT,
    ai_generated         INTEGER NOT NULL DEFAULT 0,
    ai_model             TEXT,
    ai_latency_ms        INTEGER,
    UNIQUE (recovery_attempt_id, channel)
);
CREATE INDEX IF NOT EXISTS idx_notifications_event ON notifications (event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_attempt ON notifications (recovery_attempt_id);

-- Full audit trail with AI-usage columns (doc C7).
CREATE TABLE IF NOT EXISTS audit_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id           TEXT NOT NULL,
    merchant_id        TEXT NOT NULL,
    stage              TEXT NOT NULL,   -- AuditStage
    message             TEXT,
    payload_json       TEXT,
    ai_used            INTEGER NOT NULL DEFAULT 0,
    ai_model           TEXT,
    ai_latency_ms      INTEGER,
    fallback_triggered INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log (event_id, id);

-- One config row per merchant (doc §3.16).
CREATE TABLE IF NOT EXISTS guardrail_config (
    merchant_id                       TEXT PRIMARY KEY,
    environment                       TEXT NOT NULL DEFAULT 'test', -- test|production
    recovery_window_days              INTEGER NOT NULL DEFAULT 7,
    high_confidence                   REAL NOT NULL DEFAULT 0.85,
    low_confidence                    REAL NOT NULL DEFAULT 0.50,
    max_retries                       INTEGER NOT NULL DEFAULT 3,
    cooldown_hours                    INTEGER NOT NULL DEFAULT 24,
    max_autonomous_recovery_amount_paise INTEGER NOT NULL DEFAULT 500000,
    daily_recovery_value_cap_paise    INTEGER NOT NULL DEFAULT 5000000,
    daily_contact_cap                 INTEGER NOT NULL DEFAULT 100,
    allowed_channels_json             TEXT NOT NULL DEFAULT '["email","payment_link"]',
    updated_at                        TEXT NOT NULL
);

-- Aggregate daily counters with date-based reset (doc §3.10 / A1).
CREATE TABLE IF NOT EXISTS daily_counters (
    merchant_id           TEXT NOT NULL,
    day                   TEXT NOT NULL,  -- YYYY-MM-DD (UTC)
    recovery_value_paise  INTEGER NOT NULL DEFAULT 0,
    contact_count         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (merchant_id, day)
);

-- Reproducible simulation runs (doc §3.14).
CREATE TABLE IF NOT EXISTS simulation_runs (
    simulation_run_id  TEXT PRIMARY KEY,
    merchant_id        TEXT NOT NULL,
    random_seed        INTEGER NOT NULL,
    dataset_version    TEXT NOT NULL,
    agent_version      TEXT NOT NULL,
    policy_version     TEXT NOT NULL,
    n_events           INTEGER NOT NULL,
    use_ai             INTEGER NOT NULL DEFAULT 0,
    dry_run            INTEGER NOT NULL DEFAULT 1,
    baseline_json      TEXT,
    treatment_json     TEXT,
    created_at         TEXT NOT NULL
);
