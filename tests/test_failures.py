"""Failure / recovery / resource-limit / permission tests (local; no client, no network).

Each test injects a concrete fault and asserts the fail-closed outcome. Nothing
here is a target proof: power-loss on the owner's OS, real client crashes and
real disk pressure stay in docs/OUT_OF_SANDBOX.md (T-matrix).
"""
from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from osrs_ee import config as c
from osrs_ee import service as sv
from osrs_ee.store import Store, StoreError
from osrs_ee.supervisor import FakeSupervisor
from osrs_ee.telegram import FakeTransport, Outbox, OutboundMessage, Redactor, SendResult
from osrs_ee.worker import FakeAdapter
from tests.test_service import ACC, Clock, cfg_text
from tests.test_store import T0, fixture


class StoreFaults(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "store.sqlite"

    def tearDown(self):
        self.dir.cleanup()

    def test_simulated_power_loss_mid_dispatch_recovers_to_recovery_required(self):
        """Process dies after DISPATCHING is durable: reopen → UNKNOWN + RECOVERY_REQUIRED, never READY."""
        s = Store.open(self.path, now=T0)
        s.create_account(ACC, "alias:x", "UNKNOWN", "ref:vault:x", now=T0)
        acc = s.get_account(ACC)
        for st in ("PENDING_DISCOVERY", "DISCOVERING", "READY"):
            acc = s.transition(ACC, st, expected_version=acc.state_version, reason="t", now=T0)
        s.acquire_lease(ACC, lease_id="lease_pl001", session_id="sess_pl001", client_instance_id="client_pl001",
                        expected_version=acc.state_version, ttl_seconds=600, now=T0)
        acc = s.get_account(ACC)
        acc = s.transition(ACC, "STARTING", expected_version=acc.state_version, reason="t", now=T0)
        s.transition(ACC, "RUNNING", expected_version=acc.state_version, reason="t", now=T0)
        intent = fixture("CommandIntent", "bank_withdraw")
        intent.update({"account_id": ACC, "session_id": "sess_pl001", "client_instance_id": "client_pl001",
                       "lease_id": "lease_pl001", "session_epoch": 1, "expected_state_version": 6})
        s.prepare_command(intent, now=T0)
        s.mark_dispatching(intent["command_id"], now=T0)
        s._conn.close()  # abrupt: no DRAINING, no release, no terminal phase
        s2 = Store.open(self.path, now=T0 + timedelta(seconds=5))  # open() runs recover() itself
        self.assertEqual(s2.get_command(intent["command_id"]).phase, "UNKNOWN")
        self.assertEqual(s2.get_account(ACC).state, "RECOVERY_REQUIRED")
        self.assertIn("recover(): in-flight command", [t[4] for t in s2.transitions(ACC)])
        self.assertEqual(s2.recover(now=T0 + timedelta(seconds=6)), [])  # idempotent
        self.assertNotIn("READY", [t[1] for t in s2.transitions(ACC)][3:])
        s2.close()

    def test_corrupt_database_file_is_refused_not_recreated(self):
        self.path.write_bytes(b"this is not a sqlite database" * 100)
        with self.assertRaises((sqlite3.DatabaseError, StoreError)):
            Store.open(self.path, now=T0)
        self.assertTrue(self.path.read_bytes().startswith(b"this is not"))  # untouched

    @unittest.skipIf(os.geteuid() == 0, "root bypasses permission bits")
    def test_unwritable_directory_fails_closed(self):
        ro = Path(self.dir.name) / "ro"
        ro.mkdir()
        ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            with self.assertRaises((sqlite3.OperationalError, StoreError, OSError)):
                Store.open(ro / "store.sqlite", now=T0)
        finally:
            ro.chmod(stat.S_IRWXU)

    def test_read_only_database_refuses_writes(self):
        s = Store.open(self.path, now=T0)
        s.close()
        self.path.chmod(stat.S_IRUSR)
        try:
            if os.geteuid() == 0:
                self.skipTest("root bypasses permission bits")
            with self.assertRaises((sqlite3.OperationalError, StoreError)):
                s2 = Store.open(self.path, now=T0)
                s2.create_account(ACC, "alias:x", "UNKNOWN", "ref:vault:x", now=T0)
        finally:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)


class ServiceFaults(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store.open(Path(self.dir.name) / "store.sqlite", now=T0)

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def observation(self):
        obs = fixture("Observation", "basic")
        obs["account_id"], obs["client_instance_id"] = ACC, "client_service01"
        obs["session_epoch"], obs["state_version"] = 1, 6
        return obs

    def make(self, sup=None, outbox=None, **over):
        cfg = c.load_config_text(cfg_text(**over) if over else c.example_toml())
        sv.bootstrap_account(self.store, cfg, T0)
        return sv.Service(self.store, cfg, FakeAdapter(self.observation()), sup or FakeSupervisor(), outbox,
                          clock=Clock(), alert_chat_id=7)

    def test_rss_over_limit_denies_start_and_alerts(self):
        transport = FakeTransport()
        ob = Outbox(transport, Redactor(aliases={ACC: "alias:local"}))
        svc = self.make(sup=FakeSupervisor(rss_bytes=10 * 1024 ** 3), outbox=ob)
        self.assertFalse(svc.run_once())
        kinds = [e.kind for e in svc.events]
        self.assertIn("start.denied", kinds)
        self.assertEqual(self.store.get_account(ACC).state, "READY")
        self.assertEqual(self.sup_starts(svc), 0)
        ob.flush(now=T0)
        self.assertTrue(any("start.denied" in m.text for m in transport.sent))

    def sup_starts(self, svc):
        return svc.sup.starts

    def test_fd_limit_breach_denies_the_next_start_but_does_not_kill_a_running_session(self):
        """Documented policy (release.Admission): FD/CPU limits gate *admission*; only
        disk-below-reserve and RSS-over-limit stop a running session (must_stop)."""
        sup = FakeSupervisor()
        svc = self.make(sup=sup)
        self.assertTrue(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RUNNING")
        sup.open_fds = 10_000  # breach fd_limit=2048 mid-run
        self.assertTrue(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RUNNING")
        self.assertNotIn("resources.pressure", [e.kind for e in svc.events])
        svc.request_stop("operator.stop")
        self.assertFalse(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RESTING")
        # a fresh service on the same (still breached) supervisor is denied admission
        svc2 = sv.Service(self.store, svc.cfg, FakeAdapter(self.observation()), sup, None, clock=Clock())
        self.store.transition(ACC, "READY", expected_version=self.store.get_account(ACC).state_version, reason="t", now=T0)
        self.assertFalse(svc2.run_once())
        self.assertIn("start.denied", [e.kind for e in svc2.events])

    def test_disk_below_reserve_while_running_stops_orderly(self):
        sup = FakeSupervisor()
        svc = self.make(sup=sup)
        svc.run_once()
        sup.disk_free_bytes = 1
        for _ in range(3):
            if not svc.run_once():
                break
        self.assertEqual(self.store.get_account(ACC).state, "RESTING")
        self.assertIn("resources.pressure", [e.kind for e in svc.events])

    def test_alert_transport_permanently_failing_never_blocks_the_loop(self):
        transport = FakeTransport()
        for _ in range(50):
            transport.script.append(SendResult(False, permanent=True))
        ob = Outbox(transport, Redactor(aliases={ACC: "alias:local"}), capacity=4)
        svc = self.make(sup=FakeSupervisor(crash_at_tick=2), outbox=ob, **{"restart_budget = 3": "restart_budget = 0"})
        res = svc.run(max_ticks=20)
        self.assertIn("CIRCUIT_OPEN", res.kinds())
        self.assertLessEqual(len(ob), 4)  # bounded; dropped/dead, never unbounded growth
        self.assertEqual(self.store.get_account(ACC).state, "RESTING")

    def test_restart_budget_zero_means_no_automatic_restart(self):
        svc = self.make(sup=FakeSupervisor(crash_at_tick=2), **{"restart_budget = 3": "restart_budget = 0"})
        res = svc.run(max_ticks=10)
        self.assertEqual(res.restarts, 0)
        self.assertIn("CIRCUIT_OPEN", res.kinds())
        self.assertEqual(svc.sup.starts, 1)

    def test_untouchable_account_is_never_bootstrapped_or_started(self):
        cfg = c.load_config_text(c.example_toml())
        self.store.create_account(ACC, "alias:local", "UNKNOWN", "ref:vault:x", now=T0)
        acc = self.store.get_account(ACC)
        for st in ("PENDING_DISCOVERY", "DISCOVERING", "RECOVERY_REQUIRED"):
            acc = self.store.transition(ACC, st, expected_version=acc.state_version, reason="t", now=T0)
        self.assertEqual(sv.bootstrap_account(self.store, cfg, T0), "RECOVERY_REQUIRED")
        svc = sv.Service(self.store, cfg, FakeAdapter(self.observation()), FakeSupervisor(), None, clock=Clock())
        self.assertFalse(svc.run_once())
        self.assertIn("start.refused", [e.kind for e in svc.events])
        self.assertEqual(svc.sup.starts, 0)


class RedactionFaults(unittest.TestCase):
    def test_canary_in_alert_is_refused_before_transport(self):
        transport = FakeTransport()
        red = Redactor()
        red.register_canary("SECRET-CANARY-123")
        ob = Outbox(transport, red)
        d = ob.enqueue(OutboundMessage(1, "leak SECRET-CANARY-123 here"))
        self.assertFalse(d.allowed)
        ob.flush(now=T0)
        self.assertEqual(transport.sent, [])
