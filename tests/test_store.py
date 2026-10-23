"""S02 Store tests part 1 — lifecycle, state machine, leases, journal.
Persistent SQLite, injected clock, no network. Pure/local parts of T04/T07/T08/T09.
Does NOT prove power-loss durability on the target OS."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from osrs_ee import store as st

FIX = Path(__file__).resolve().parent.parent / "contracts" / "fixtures" / "valid"
T0 = datetime(2026, 10, 23, 19, 0, 0, tzinfo=timezone.utc)
ACC = "acc_demo001"


def fixture(contract, name):
    return json.loads((FIX / contract / f"{name}.json").read_text())


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "store.sqlite"
        self.s = st.Store.open(self.path, now=T0)

    def tearDown(self):
        self.s.close()
        self.dir.cleanup()

    def reopen(self, now=T0):
        self.s.close()
        self.s = st.Store.open(self.path, now=now)
        return self.s

    def make_ready(self):
        self.s.create_account(ACC, "demo", "UNKNOWN", "ref:vault:acc_demo001", now=T0)
        for v, state in enumerate(("PENDING_DISCOVERY", "DISCOVERING", "READY")):
            self.s.transition(ACC, state, expected_version=v, reason="setup", now=T0)
        return 3

    def lease(self, ttl=3600):
        v = self.make_ready()
        return self.s.acquire_lease(ACC, lease_id="lease_demo001", session_id="sess_demo001",
                                    client_instance_id="client_demo001", expected_version=v, ttl_seconds=ttl, now=T0)

    def intent(self, **over):
        i = fixture("CommandIntent", "bank_withdraw")
        i["session_epoch"], i["expected_state_version"] = 1, 4
        i.update(over)
        return i


class Lifecycle(StoreCase):
    def test_schema_version_and_wal(self):
        conn = sqlite3.connect(self.path)
        self.assertEqual(conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0], "1")
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        conn.close()
        self.assertTrue(self.s.integrity_ok())

    def test_secret_value_refused_as_credential(self):
        with self.assertRaises(st.StoreError):
            self.s.create_account(ACC, "demo", "UNKNOWN", "hunter2", now=T0)

    def test_backup_restores_identical_state(self):
        self.lease()
        bak = Path(self.dir.name) / "bak.sqlite"
        self.s.backup_to(bak)
        other = st.Store.open(bak, now=T0)
        try:
            self.assertEqual(other.get_account(ACC).state, "LEASED")
            self.assertEqual(other.active_lease(ACC).lease_id, "lease_demo001")
        finally:
            other.close()

    def test_schema_version_mismatch_refuses_open(self):
        self.s.close()
        conn = sqlite3.connect(self.path)
        conn.execute("UPDATE schema_meta SET value='99' WHERE key='schema_version'"); conn.commit(); conn.close()
        with self.assertRaises(st.StoreError):
            st.Store.open(self.path, now=T0)
        self.s = st.Store.open(Path(self.dir.name) / "other.sqlite", now=T0)


class StateMachine(StoreCase):
    def test_only_listed_transitions(self):
        self.s.create_account(ACC, "demo", "UNKNOWN", "ref:vault:x", now=T0)
        for bad in ("READY", "RUNNING", "RESTING"):
            with self.assertRaises(st.InvalidTransition):
                self.s.transition(ACC, bad, expected_version=0, reason="skip", now=T0)
        self.assertEqual(self.s.get_account(ACC).state_version, 0)

    def test_cas_version_conflict_is_atomic(self):
        self.s.create_account(ACC, "demo", "UNKNOWN", "ref:vault:x", now=T0)
        self.s.transition(ACC, "PENDING_DISCOVERY", expected_version=0, reason="a", now=T0)
        with self.assertRaises(st.VersionConflict):
            self.s.transition(ACC, "DISABLED", expected_version=0, reason="stale writer", now=T0)
        acc = self.s.get_account(ACC)
        self.assertEqual((acc.state, acc.state_version), ("PENDING_DISCOVERY", 1))
        self.assertEqual(len(self.s.transitions(ACC)), 1)

    def test_disabled_is_terminal(self):
        self.s.create_account(ACC, "demo", "UNKNOWN", "ref:vault:x", now=T0)
        self.s.transition(ACC, "DISABLED", expected_version=0, reason="x", now=T0)
        with self.assertRaises(st.InvalidTransition):
            self.s.transition(ACC, "NEW", expected_version=1, reason="x", now=T0)


class Leases(StoreCase):
    def test_acquire_bumps_epoch_and_state(self):
        self.assertEqual(self.lease().session_epoch, 1)
        acc = self.s.get_account(ACC)
        self.assertEqual((acc.state, acc.state_version, acc.session_epoch), ("LEASED", 4, 1))

    def test_second_lease_rejected_while_active(self):
        self.lease()
        with self.assertRaises(st.LeaseConflict):
            self.s.acquire_lease(ACC, lease_id="lease_other001", session_id="sess_other001", client_instance_id="client_x001",
                                 expected_version=4, ttl_seconds=60, now=T0)

    def test_release_requires_holder_epoch_and_is_idempotent(self):
        self.lease()
        with self.assertRaises(st.LeaseConflict):
            self.s.release_lease("lease_demo001", session_epoch=2, reason="old worker", now=T0)
        self.s.release_lease("lease_demo001", session_epoch=1, reason="drain", now=T0)
        self.s.release_lease("lease_demo001", session_epoch=1, reason="drain", now=T0)
        self.assertIsNone(self.s.active_lease(ACC))

    def test_lease_requires_ready_and_positive_ttl(self):
        self.s.create_account(ACC, "demo", "UNKNOWN", "ref:vault:x", now=T0)
        with self.assertRaises(st.InvalidTransition):
            self.s.acquire_lease(ACC, lease_id="lease_a1", session_id="sess_a1", client_instance_id="client_a1", expected_version=0, ttl_seconds=60, now=T0)
        with self.assertRaises(st.StoreError):
            self.s.acquire_lease(ACC, lease_id="lease_a1", session_id="sess_a1", client_instance_id="client_a1", expected_version=0, ttl_seconds=0, now=T0)

    def test_epoch_increases_across_sessions(self):
        self.lease()
        self.s.release_lease("lease_demo001", session_epoch=1, reason="drain", now=T0)
        v = 4
        for state in ("STARTING", "RUNNING", "DRAINING", "RESTING", "READY"):
            self.s.transition(ACC, state, expected_version=v, reason="cycle", now=T0); v += 1
        second = self.s.acquire_lease(ACC, lease_id="lease_demo002", session_id="sess_demo002", client_instance_id="client_demo001",
                                      expected_version=v, ttl_seconds=60, now=T0)
        self.assertEqual(second.session_epoch, 2)


class CommandJournal(StoreCase):
    def test_prepared_is_durable_before_dispatch(self):
        self.lease()
        row, created = self.s.prepare_command(self.intent(), now=T0)
        self.assertTrue(created); self.assertEqual(row.phase, "PREPARED")
        self.reopen()
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "PREPARED")
        self.assertEqual(self.s.get_account(ACC).state, "LEASED")

    def test_idempotent_same_payload_conflict_on_different(self):
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        _, created = self.s.prepare_command(self.intent(), now=T0)
        self.assertFalse(created)
        with self.assertRaises(st.IdempotencyConflict):
            self.s.prepare_command(self.intent(params={"item_id": 1511, "quantity": 11, "noted": False}), now=T0)

    def test_intent_must_match_active_lease(self):
        self.lease()
        for bad in (dict(lease_id="lease_other001"), dict(session_epoch=2), dict(client_instance_id="client_other01"), dict(session_id="sess_other001")):
            with self.assertRaises(st.LeaseConflict):
                self.s.prepare_command(self.intent(**bad), now=T0)

    def test_expired_lease_refuses_new_commands(self):
        self.lease(ttl=10)
        with self.assertRaises(st.LeaseConflict):
            self.s.prepare_command(self.intent(), now=T0 + timedelta(seconds=10))

    def test_crash_after_dispatching_yields_unknown_and_recovery(self):
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        self.s.mark_dispatching("cmd_demo001", now=T0)
        self.reopen(now=T0 + timedelta(seconds=1))
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "UNKNOWN")
        self.assertEqual(self.s.get_account(ACC).state, "RECOVERY_REQUIRED")
        self.assertEqual(self.s.unknown_pending(ACC), 1)
        self.reopen(now=T0 + timedelta(seconds=2))
        self.assertEqual(self.s.get_account(ACC).state, "RECOVERY_REQUIRED")
        self.assertNotEqual(self.s.get_account(ACC).state, "READY")

    def test_phase_guards(self):
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        self.s.mark_dispatching("cmd_demo001", now=T0)
        with self.assertRaises(st.StoreError):
            self.s.mark_dispatching("cmd_demo001", now=T0)
        with self.assertRaises(st.StoreError):
            self.s.mark_not_sent("cmd_demo001", now=T0)

    def test_not_sent_before_dispatch(self):
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        self.assertEqual(self.s.mark_not_sent("cmd_demo001", now=T0).phase, "NOT_SENT")
        self.assertEqual(self.s.unknown_pending(ACC), 0)
