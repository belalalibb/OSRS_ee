-- OSRS_ee Store schema v1 (ADR-003: SQLite, single logical writer).
-- Every state/lease/command/event mutation goes through one transaction in store.py.
-- No secrets: only *_ref columns (opaque references), never values.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id      TEXT PRIMARY KEY,
    alias           TEXT NOT NULL UNIQUE,
    auth_mode       TEXT NOT NULL CHECK (auth_mode IN ('UNKNOWN','LEGACY','JAGEX_SESSION')),
    credential_ref  TEXT NOT NULL,
    proxy_ref       TEXT,
    state           TEXT NOT NULL CHECK (state IN ('NEW','PENDING_DISCOVERY','DISCOVERING','READY','LEASED','STARTING','RUNNING','DRAINING','RESTING','BLOCKED','RECOVERY_REQUIRED','RECONCILING','DISABLED')),
    state_version   INTEGER NOT NULL DEFAULT 0 CHECK (state_version >= 0),
    session_epoch   INTEGER NOT NULL DEFAULT 0 CHECK (session_epoch >= 0),
    cooldown_until  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Exactly one active lease per account; fencing by (lease_id, session_epoch).
CREATE TABLE IF NOT EXISTS leases (
    lease_id            TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(account_id),
    session_id          TEXT NOT NULL UNIQUE,
    client_instance_id  TEXT NOT NULL,
    session_epoch       INTEGER NOT NULL CHECK (session_epoch >= 1),
    acquired_at         TEXT NOT NULL,
    expires_at          TEXT NOT NULL,
    released_at         TEXT,
    release_reason      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS leases_one_active_per_account
    ON leases(account_id) WHERE released_at IS NULL;

-- Command journal: written BEFORE any dispatch (PREPARED), then advanced.
CREATE TABLE IF NOT EXISTS commands (
    command_id      TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(account_id),
    session_id      TEXT NOT NULL,
    lease_id        TEXT NOT NULL REFERENCES leases(lease_id),
    session_epoch   INTEGER NOT NULL,
    payload_hash    TEXT NOT NULL,             -- canonical hash of the full CommandIntent
    intent_json     TEXT NOT NULL,
    phase           TEXT NOT NULL CHECK (phase IN ('PREPARED','DISPATCHING','ACKNOWLEDGED','UNKNOWN','VERIFIED','FAILED_VERIFIED','REJECTED','NOT_SENT')),
    prepared_at     TEXT NOT NULL,
    dispatching_at  TEXT,
    finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS commands_by_account_phase ON commands(account_id, phase);

-- Result events: idempotent by event_id; at most one terminal event per command.
CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    command_id      TEXT NOT NULL REFERENCES commands(command_id),
    session_epoch   INTEGER NOT NULL,
    state_version   INTEGER NOT NULL,
    transport_status TEXT NOT NULL,
    effect_status   TEXT NOT NULL,
    reason_code     TEXT NOT NULL,
    event_json      TEXT NOT NULL,
    recorded_at     TEXT NOT NULL
);

-- Approvals are single-use and bound to incident/account/epoch/plan hash/state version.
CREATE TABLE IF NOT EXISTS approvals (
    approval_id     TEXT PRIMARY KEY,
    incident_id     TEXT NOT NULL,
    account_id      TEXT NOT NULL REFERENCES accounts(account_id),
    session_epoch   INTEGER NOT NULL,
    plan_hash       TEXT NOT NULL,
    state_version   INTEGER NOT NULL,
    approver_ref    TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    used_at         TEXT
);

-- Append-only transition log for audit and recovery reasoning.
CREATE TABLE IF NOT EXISTS transitions (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT NOT NULL REFERENCES accounts(account_id),
    from_state      TEXT NOT NULL,
    to_state        TEXT NOT NULL,
    from_version    INTEGER NOT NULL,
    to_version      INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    at              TEXT NOT NULL
);
