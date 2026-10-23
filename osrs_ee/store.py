"""SQLite Store — the single logical writer for OSRS_ee state (ADR-003/004).

Guarantees implemented here (and tested in tests/test_store.py):
- Account state machine: only transitions listed in FOUNDATION §5 are allowed;
  every transition increments state_version atomically (CAS on expected version).
- Leases: at most one active lease per account (partial unique index); acquiring
  bumps session_epoch; a lease can only be released by its own (lease_id, epoch).
- Command journal: PREPARED is durable *before* dispatch; DISPATCHING is marked
  before the network call; terminal phase is set once. A crash leaves UNKNOWN,
  never a guessed success.
- Idempotency: same command_id + same payload hash -> stored record returned,
  no second journal row; same id + different payload -> IdempotencyConflict.
- Event dedupe: duplicate event_id is a no-op; a second terminal event for the
  same command is rejected.
- Approvals: single-use (atomic consume), bound to incident/account/epoch/
  plan hash/state version/expiry.
- Recovery: on open, every DISPATCHING/ACKNOWLEDGED command is converted to
  UNKNOWN and the account moved to RECOVERY_REQUIRED; nothing becomes READY
  automatically.

Time is injected (``now`` parameters) — the Store never reads the wall clock,
so tests are deterministic and monotonic deadlines stay the caller's concern.
No network; no secrets (refs only).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from . import canonical, contracts
from .guards import parse_utc

SCHEMA_VERSION = "1"
_SCHEMA_SQL = "\n".join(
    line for line in (Path(__file__).resolve().parent / "store_schema.sql").read_text(encoding="utf-8").splitlines()
    if not line.lstrip().startswith("--")
)

# FOUNDATION §5 transition table (from -> allowed to). Anything else is rejected.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW": frozenset({"PENDING_DISCOVERY", "DISABLED"}),
    "PENDING_DISCOVERY": frozenset({"DISCOVERING", "DISABLED"}),
    "DISCOVERING": frozenset({"READY", "BLOCKED", "RECOVERY_REQUIRED", "DISABLED"}),
    "READY": frozenset({"LEASED", "BLOCKED", "RECOVERY_REQUIRED", "DISABLED"}),
    "LEASED": frozenset({"STARTING", "RECOVERY_REQUIRED", "DISABLED"}),
    "STARTING": frozenset({"RUNNING", "RECOVERY_REQUIRED", "DISABLED"}),
    "RUNNING": frozenset({"DRAINING", "BLOCKED", "RECOVERY_REQUIRED", "DISABLED"}),
    "DRAINING": frozenset({"RESTING", "RECOVERY_REQUIRED", "DISABLED"}),
    "RESTING": frozenset({"READY", "RECOVERY_REQUIRED", "DISABLED"}),
    "BLOCKED": frozenset({"RECONCILING", "DISABLED"}),
    "RECOVERY_REQUIRED": frozenset({"RECONCILING", "DISABLED"}),
    "RECONCILING": frozenset({"RESTING", "READY", "RECOVERY_REQUIRED", "BLOCKED", "DISABLED"}),
    "DISABLED": frozenset(),
}
TERMINAL_PHASES = frozenset({"VERIFIED", "FAILED_VERIFIED", "REJECTED", "NOT_SENT", "UNKNOWN"})
IN_FLIGHT_PHASES = frozenset({"DISPATCHING", "ACKNOWLEDGED"})


class StoreError(Exception):
    pass


class InvalidTransition(StoreError):
    pass


class VersionConflict(StoreError):
    pass


class LeaseConflict(StoreError):
    pass


class IdempotencyConflict(StoreError):
    pass


class ApprovalError(StoreError):
    pass


@dataclass(frozen=True)
class AccountRow:
    account_id: str
    alias: str
    auth_mode: str
    credential_ref: str
    proxy_ref: Optional[str]
    state: str
    state_version: int
    session_epoch: int
    cooldown_until: Optional[str]


@dataclass(frozen=True)
class LeaseRow:
    lease_id: str
    account_id: str
    session_id: str
    client_instance_id: str
    session_epoch: int
    acquired_at: str
    expires_at: str
    released_at: Optional[str]


@dataclass(frozen=True)
class CommandRow:
    command_id: str
    account_id: str
    session_id: str
    lease_id: str
    session_epoch: int
    payload_hash: str
    phase: str
    finished_at: Optional[str] = None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware UTC")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    """Open with ``Store.open(path)``; use as context manager or call ``close()``."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------ lifecycle
    @classmethod
    def open(cls, path: str | Path, *, now: datetime) -> "Store":
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        store = cls(conn)
        with store._tx():
            # executescript() would implicitly COMMIT; run statements inside our transaction instead.
            for stmt in _SCHEMA_SQL.split(";"):
                if stmt.strip() and not stmt.strip().startswith("PRAGMA"):
                    conn.execute(stmt)
            row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_meta(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))
            elif row["value"] != SCHEMA_VERSION:
                raise StoreError(f"schema_version {row['value']} != {SCHEMA_VERSION}; migration required (ADR-012)")
        store.recover(now=now)
        return store

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    class _Tx:
        def __init__(self, conn: sqlite3.Connection):
            self.conn = conn

        def __enter__(self):
            self.conn.execute("BEGIN IMMEDIATE")
            return self

        def __exit__(self, exc_type, *_):
            self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
            return False

    def _tx(self) -> "Store._Tx":
        return Store._Tx(self._conn)

    def integrity_ok(self) -> bool:
        return self._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def backup_to(self, path: str | Path) -> None:
        dest = sqlite3.connect(str(path))
        try:
            self._conn.backup(dest)
        finally:
            dest.close()

    # ------------------------------------------------------------- accounts
    def create_account(self, account_id: str, alias: str, auth_mode: str, credential_ref: str, *,
                       proxy_ref: Optional[str] = None, now: datetime) -> AccountRow:
        if not credential_ref.startswith("ref:"):
            raise StoreError("credential_ref must be an opaque ref, never a secret value")
        ts = _iso(now)
        with self._tx():
            self._conn.execute(
                "INSERT INTO accounts(account_id,alias,auth_mode,credential_ref,proxy_ref,state,state_version,session_epoch,created_at,updated_at)"
                " VALUES(?,?,?,?,?,'NEW',0,0,?,?)",
                (account_id, alias, auth_mode, credential_ref, proxy_ref, ts, ts))
        return self.get_account(account_id)

    def get_account(self, account_id: str) -> AccountRow:
        row = self._conn.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
        if row is None:
            raise StoreError(f"unknown account {account_id}")
        return AccountRow(row["account_id"], row["alias"], row["auth_mode"], row["credential_ref"], row["proxy_ref"],
                          row["state"], row["state_version"], row["session_epoch"], row["cooldown_until"])

    def transition(self, account_id: str, to_state: str, *, expected_version: int, reason: str, now: datetime) -> AccountRow:
        """CAS state transition. Raises InvalidTransition / VersionConflict."""
        with self._tx():
            return self._transition_locked(account_id, to_state, expected_version, reason, now)

    def _transition_locked(self, account_id: str, to_state: str, expected_version: int, reason: str, now: datetime) -> AccountRow:
        acc = self.get_account(account_id)
        if acc.state_version != expected_version:
            raise VersionConflict(f"{account_id}: expected version {expected_version}, have {acc.state_version}")
        if to_state not in ALLOWED_TRANSITIONS.get(acc.state, frozenset()):
            raise InvalidTransition(f"{account_id}: {acc.state} -> {to_state} not allowed")
        new_version = acc.state_version + 1
        ts = _iso(now)
        self._conn.execute("UPDATE accounts SET state=?, state_version=?, updated_at=? WHERE account_id=? AND state_version=?",
                           (to_state, new_version, ts, account_id, expected_version))
        self._conn.execute("INSERT INTO transitions(account_id,from_state,to_state,from_version,to_version,reason,at) VALUES(?,?,?,?,?,?,?)",
                           (account_id, acc.state, to_state, acc.state_version, new_version, reason, ts))
        return self.get_account(account_id)

    def transitions(self, account_id: str) -> list[tuple[str, str, int, int, str]]:
        rows = self._conn.execute("SELECT from_state,to_state,from_version,to_version,reason FROM transitions WHERE account_id=? ORDER BY seq", (account_id,)).fetchall()
        return [tuple(r) for r in rows]

    # --------------------------------------------------------------- leases
    def acquire_lease(self, account_id: str, *, lease_id: str, session_id: str, client_instance_id: str,
                      expected_version: int, ttl_seconds: int, now: datetime) -> LeaseRow:
        """READY -> LEASED with a fresh epoch and exactly one active lease."""
        if ttl_seconds < 1:
            raise StoreError("ttl_seconds must be >= 1")
        with self._tx():
            acc = self.get_account(account_id)
            active = self._conn.execute("SELECT lease_id FROM leases WHERE account_id=? AND released_at IS NULL", (account_id,)).fetchone()
            if active is not None:
                raise LeaseConflict(f"{account_id}: active lease {active['lease_id']} exists")
            if acc.cooldown_until and parse_utc(acc.cooldown_until) > now:
                raise LeaseConflict(f"{account_id}: cooldown until {acc.cooldown_until}")
            new_epoch = acc.session_epoch + 1
            self._transition_locked(account_id, "LEASED", expected_version, f"lease {lease_id}", now)
            self._conn.execute("UPDATE accounts SET session_epoch=? WHERE account_id=?", (new_epoch, account_id))
            from datetime import timedelta
            self._conn.execute(
                "INSERT INTO leases(lease_id,account_id,session_id,client_instance_id,session_epoch,acquired_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                (lease_id, account_id, session_id, client_instance_id, new_epoch, _iso(now), _iso(now + timedelta(seconds=ttl_seconds))))
        return self.get_lease(lease_id)

    def get_lease(self, lease_id: str) -> LeaseRow:
        r = self._conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        if r is None:
            raise StoreError(f"unknown lease {lease_id}")
        return LeaseRow(r["lease_id"], r["account_id"], r["session_id"], r["client_instance_id"], r["session_epoch"],
                        r["acquired_at"], r["expires_at"], r["released_at"])

    def active_lease(self, account_id: str) -> Optional[LeaseRow]:
        r = self._conn.execute("SELECT lease_id FROM leases WHERE account_id=? AND released_at IS NULL", (account_id,)).fetchone()
        return self.get_lease(r["lease_id"]) if r else None

    def release_lease(self, lease_id: str, *, session_epoch: int, reason: str, now: datetime) -> None:
        """Only the holder (lease_id + epoch) may release. Idempotent for the holder."""
        with self._tx():
            lease = self.get_lease(lease_id)
            if lease.session_epoch != session_epoch:
                raise LeaseConflict(f"lease {lease_id}: epoch {session_epoch} is not the holder's {lease.session_epoch}")
            if lease.released_at is not None:
                return
            self._conn.execute("UPDATE leases SET released_at=?, release_reason=? WHERE lease_id=?", (_iso(now), reason, lease_id))

    # ------------------------------------------------------------- commands
    def prepare_command(self, intent: dict, *, now: datetime) -> tuple[CommandRow, bool]:
        """Durable PREPARED record before any dispatch.

        Returns (row, created). Same id+payload -> existing row, created=False.
        Same id, different payload -> IdempotencyConflict. Validates the intent
        against the schema and against the *current* active lease/epoch.
        """
        contracts.require_valid("CommandIntent", intent)
        payload_hash = canonical.content_hash(intent)
        with self._tx():
            existing = self._conn.execute("SELECT * FROM commands WHERE command_id=?", (intent["command_id"],)).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    raise IdempotencyConflict(f"command {intent['command_id']}: payload differs from journaled intent")
                return self._row(existing), False
            lease = self.active_lease(intent["account_id"])
            if lease is None or lease.lease_id != intent["lease_id"] or lease.session_epoch != intent["session_epoch"] \
                    or lease.session_id != intent["session_id"] or lease.client_instance_id != intent["client_instance_id"]:
                raise LeaseConflict("intent is not bound to the account's active lease/epoch")
            if parse_utc(lease.expires_at) <= now:
                raise LeaseConflict("lease expired")
            self._conn.execute(
                "INSERT INTO commands(command_id,account_id,session_id,lease_id,session_epoch,payload_hash,intent_json,phase,prepared_at)"
                " VALUES(?,?,?,?,?,?,?,'PREPARED',?)",
                (intent["command_id"], intent["account_id"], intent["session_id"], intent["lease_id"], intent["session_epoch"],
                 payload_hash, json.dumps(intent, sort_keys=True), _iso(now)))
        return self.get_command(intent["command_id"]), True

    @staticmethod
    def _row(r: sqlite3.Row) -> CommandRow:
        return CommandRow(r["command_id"], r["account_id"], r["session_id"], r["lease_id"], r["session_epoch"], r["payload_hash"], r["phase"], r["finished_at"])

    def get_command(self, command_id: str) -> CommandRow:
        r = self._conn.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
        if r is None:
            raise StoreError(f"unknown command {command_id}")
        return self._row(r)

    def mark_dispatching(self, command_id: str, *, now: datetime) -> CommandRow:
        """PREPARED -> DISPATCHING, strictly before the network call."""
        with self._tx():
            cur = self._conn.execute("UPDATE commands SET phase='DISPATCHING', dispatching_at=? WHERE command_id=? AND phase='PREPARED'", (_iso(now), command_id))
            if cur.rowcount != 1:
                raise StoreError(f"command {command_id}: not in PREPARED phase")
        return self.get_command(command_id)

    def mark_not_sent(self, command_id: str, *, now: datetime) -> CommandRow:
        """PREPARED -> NOT_SENT when a guard denies before dispatch."""
        with self._tx():
            cur = self._conn.execute("UPDATE commands SET phase='NOT_SENT', finished_at=? WHERE command_id=? AND phase='PREPARED'", (_iso(now), command_id))
            if cur.rowcount != 1:
                raise StoreError(f"command {command_id}: not in PREPARED phase")
        return self.get_command(command_id)

    def record_event(self, event: dict, *, now: datetime) -> bool:
        """Record a ResultEvent; returns False if event_id already recorded (dedupe).

        Sets the command's terminal phase from the event; rejects a second
        terminal event for the same command; never 'upgrades' UNKNOWN to a
        guessed success without evidence (the schema already forces evidence
        for VERIFIED).
        """
        contracts.require_valid("ResultEvent", event)
        with self._tx():
            if self._conn.execute("SELECT 1 FROM events WHERE event_id=?", (event["event_id"],)).fetchone():
                return False
            cmd = self.get_command(event["command_id"])
            if cmd.session_epoch != event["session_epoch"] or cmd.session_id != event["session_id"]:
                raise LeaseConflict("event binding does not match journaled command")
            if cmd.phase in TERMINAL_PHASES and not (cmd.phase == "UNKNOWN" and event["effect_status"] in ("VERIFIED", "FAILED_VERIFIED")):
                raise StoreError(f"command {cmd.command_id}: already terminal ({cmd.phase})")
            phase = self._phase_from_event(event)
            self._conn.execute(
                "INSERT INTO events(event_id,command_id,session_epoch,state_version,transport_status,effect_status,reason_code,event_json,recorded_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (event["event_id"], event["command_id"], event["session_epoch"], event["state_version"], event["transport_status"],
                 event["effect_status"], event["reason_code"], json.dumps(event, sort_keys=True), _iso(now)))
            self._conn.execute("UPDATE commands SET phase=?, finished_at=CASE WHEN ? IN ('VERIFIED','FAILED_VERIFIED','REJECTED','NOT_SENT') THEN ? ELSE finished_at END WHERE command_id=?",
                               (phase, phase, _iso(now), cmd.command_id))
        return True

    @staticmethod
    def _phase_from_event(event: dict) -> str:
        t, e = event["transport_status"], event["effect_status"]
        if e in ("VERIFIED", "FAILED_VERIFIED"):
            return e
        if t == "NOT_SENT":
            return "NOT_SENT"
        if t == "REJECTED" and e == "NOT_ATTEMPTED":
            return "REJECTED"
        if t == "ACKNOWLEDGED" and e == "UNKNOWN":
            return "ACKNOWLEDGED"
        return "UNKNOWN"

    def commands_in_phase(self, account_id: str, phases: Iterable[str]) -> list[CommandRow]:
        ph = tuple(phases)
        q = f"SELECT * FROM commands WHERE account_id=? AND phase IN ({','.join('?'*len(ph))}) ORDER BY prepared_at"
        return [self._row(r) for r in self._conn.execute(q, (account_id, *ph)).fetchall()]

    def unknown_pending(self, account_id: str) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM commands WHERE account_id=? AND phase IN ('UNKNOWN','DISPATCHING','ACKNOWLEDGED')", (account_id,)).fetchone()[0]

    # ------------------------------------------------------------ approvals
    def create_approval(self, *, approval_id: str, incident_id: str, account_id: str, session_epoch: int, plan_hash: str,
                        state_version: int, approver_ref: str, expires_at: datetime, now: datetime) -> None:
        if expires_at <= now:
            raise ApprovalError("approval already expired")
        with self._tx():
            self._conn.execute(
                "INSERT INTO approvals(approval_id,incident_id,account_id,session_epoch,plan_hash,state_version,approver_ref,expires_at,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (approval_id, incident_id, account_id, session_epoch, plan_hash, state_version, approver_ref, _iso(expires_at), _iso(now)))

    def consume_approval(self, approval_id: str, *, incident_id: str, account_id: str, session_epoch: int, plan_hash: str,
                         state_version: int, now: datetime) -> None:
        """Atomic single-use consume; every bound field must match; raises ApprovalError."""
        with self._tx():
            r = self._conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if r is None:
                raise ApprovalError("unknown approval")
            if r["used_at"] is not None:
                raise ApprovalError("approval already used")
            if parse_utc(r["expires_at"]) <= now:
                raise ApprovalError("approval expired")
            bound = (r["incident_id"], r["account_id"], r["session_epoch"], r["plan_hash"], r["state_version"])
            if bound != (incident_id, account_id, session_epoch, plan_hash, state_version):
                raise ApprovalError("approval context mismatch")
            cur = self._conn.execute("UPDATE approvals SET used_at=? WHERE approval_id=? AND used_at IS NULL", (_iso(now), approval_id))
            if cur.rowcount != 1:
                raise ApprovalError("approval already used (race)")

    # ------------------------------------------------------------- recovery
    def recover(self, *, now: datetime) -> list[str]:
        """Run at open: in-flight commands -> UNKNOWN; their accounts -> RECOVERY_REQUIRED.

        Never sets READY. Returns affected account ids.
        """
        affected: list[str] = []
        with self._tx():
            rows = self._conn.execute("SELECT DISTINCT account_id FROM commands WHERE phase IN ('DISPATCHING','ACKNOWLEDGED')").fetchall()
            for r in rows:
                acc_id = r["account_id"]
                self._conn.execute("UPDATE commands SET phase='UNKNOWN' WHERE account_id=? AND phase IN ('DISPATCHING','ACKNOWLEDGED')", (acc_id,))
                acc = self.get_account(acc_id)
                if acc.state not in ("RECOVERY_REQUIRED", "DISABLED", "RECONCILING", "BLOCKED"):
                    # Every non-terminal operational state has a direct edge to RECOVERY_REQUIRED (FOUNDATION §5).
                    self._transition_locked(acc_id, "RECOVERY_REQUIRED", acc.state_version, "recover(): in-flight command", now)
                affected.append(acc_id)
            # Accounts in active-session states without an active lease are inconsistent.
            rows = self._conn.execute(
                "SELECT a.account_id, a.state, a.state_version FROM accounts a WHERE a.state IN ('LEASED','STARTING','RUNNING','DRAINING')"
                " AND NOT EXISTS (SELECT 1 FROM leases l WHERE l.account_id=a.account_id AND l.released_at IS NULL)").fetchall()
            for r in rows:
                self._transition_locked(r["account_id"], "RECOVERY_REQUIRED", r["state_version"], "recover(): session state without lease", now)
                if r["account_id"] not in affected:
                    affected.append(r["account_id"])
        return affected
