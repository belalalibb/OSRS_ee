"""SUP-04 — one service per data_dir + orphaned-session reconciliation.

Gap found while comparing with Engine-Docs ``reconcile_on_boot`` / PR-16
``reconcile_orphaned_leases``: after a SIGKILL/power loss our Store left a
RUNNING account with an *active* lease untouched on reopen (reproduced before
this change: state RUNNING, lease active, recover() == []). We resolve it with
a different design than the reference (re-implemented, nothing copied): the
exclusive ``ServiceLock`` is the liveness proof, not a stored pid.
POSIX ``flock`` only; Windows branch NOT tested here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path

from osrs_ee.lock import LockHeld, ServiceLock
from osrs_ee.store import Store
from tests.test_store import T0, fixture

ACC = "acc_orphan001"


def _running_with_lease(path: Path, *, dispatching: bool = False) -> None:
    s = Store.open(path, now=T0)
    s.create_account(ACC, "alias:o", "UNKNOWN", "ref:vault:x", now=T0)
    acc = s.get_account(ACC)
    for st in ("PENDING_DISCOVERY", "DISCOVERING", "READY"):
        acc = s.transition(ACC, st, expected_version=acc.state_version, reason="t", now=T0)
    s.acquire_lease(ACC, lease_id="lease_o001", session_id="sess_o001", client_instance_id="client_o001",
                    expected_version=acc.state_version, ttl_seconds=3600, now=T0)
    acc = s.get_account(ACC)
    acc = s.transition(ACC, "STARTING", expected_version=acc.state_version, reason="t", now=T0)
    s.transition(ACC, "RUNNING", expected_version=acc.state_version, reason="t", now=T0)
    if dispatching:
        intent = fixture("CommandIntent", "bank_withdraw")
        intent.update({"account_id": ACC, "session_id": "sess_o001", "client_instance_id": "client_o001",
                       "lease_id": "lease_o001", "session_epoch": 1, "expected_state_version": 6})
        s.prepare_command(intent, now=T0)
        s.mark_dispatching(intent["command_id"], now=T0)
    s._conn.close()  # abrupt death: no drain, no release


class OrphanedSessions(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "store.sqlite"

    def tearDown(self):
        self.dir.cleanup()

    def test_recover_alone_leaves_running_with_active_lease(self):
        """Documents the Store's limit: it cannot tell a live session from a dead one."""
        _running_with_lease(self.path)
        s = Store.open(self.path, now=T0 + timedelta(hours=2))
        self.assertEqual(s.get_account(ACC).state, "RUNNING")
        self.assertIsNotNone(s.active_lease(ACC))
        s.close()

    def test_reconcile_orphans_releases_lease_and_requires_recovery_never_ready(self):
        _running_with_lease(self.path)
        s = Store.open(self.path, now=T0 + timedelta(seconds=5))
        now = T0 + timedelta(seconds=6)
        self.assertEqual(s.reconcile_orphaned_sessions(now=now), [ACC])
        acc = s.get_account(ACC)
        self.assertEqual(acc.state, "RECOVERY_REQUIRED")
        self.assertIsNone(s.active_lease(ACC))
        lease = s.get_lease("lease_o001")
        self.assertIn("orphan", lease.release_reason or "") if hasattr(lease, "release_reason") else None
        self.assertEqual(s.reconcile_orphaned_sessions(now=now), [])  # idempotent
        self.assertNotIn("READY", [t[1] for t in s.transitions(ACC)][3:])
        # a fresh lease is possible only after owner reconciliation (RECONCILING -> READY)
        from osrs_ee.store import LeaseConflict, StoreError
        with self.assertRaises((LeaseConflict, StoreError)):
            s.acquire_lease(ACC, lease_id="lease_o002", session_id="sess_o002", client_instance_id="client_o001",
                            expected_version=acc.state_version, ttl_seconds=60, now=now)
        s.close()

    def test_reconcile_orphans_marks_in_flight_command_unknown(self):
        _running_with_lease(self.path, dispatching=True)
        s = Store.open(self.path, now=T0 + timedelta(seconds=5))  # recover(): in-flight -> UNKNOWN + RECOVERY_REQUIRED
        self.assertEqual(s.get_account(ACC).state, "RECOVERY_REQUIRED")
        self.assertIsNotNone(s.active_lease(ACC))  # recover() does not release leases
        self.assertEqual(s.reconcile_orphaned_sessions(now=T0 + timedelta(seconds=6)), [])  # not a session state any more
        self.assertEqual(s.unknown_pending(ACC), 1)
        s.close()

    def test_reconcile_orphans_ignores_healthy_states(self):
        s = Store.open(self.path, now=T0)
        s.create_account(ACC, "alias:o", "UNKNOWN", "ref:vault:x", now=T0)
        acc = s.get_account(ACC)
        for st in ("PENDING_DISCOVERY", "DISCOVERING", "READY"):
            acc = s.transition(ACC, st, expected_version=acc.state_version, reason="t", now=T0)
        self.assertEqual(s.reconcile_orphaned_sessions(now=T0), [])
        self.assertEqual(s.get_account(ACC).state, "READY")
        s.close()


HOLDER = r"""
import sys, time
from osrs_ee.lock import ServiceLock
with ServiceLock(sys.argv[1]):
    print("held", flush=True)
    time.sleep(float(sys.argv[2]))
"""


@unittest.skipUnless(os.name == "posix", "flock semantics tested on POSIX only")
class Lock(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def test_second_acquire_in_same_process_is_refused_and_release_frees_it(self):
        a = ServiceLock(self.dir.name).acquire()
        self.assertTrue(a.held)
        self.assertEqual(int((Path(self.dir.name) / "service.lock").read_text()), os.getpid())
        b = ServiceLock(self.dir.name)
        with self.assertRaises(LockHeld) as ctx:
            b.acquire()
        self.assertEqual(ctx.exception.holder_pid, os.getpid())
        a.release()
        self.assertFalse(a.held)
        b.acquire(); b.release()

    def test_lock_held_by_another_live_process_is_refused_and_freed_on_its_death(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        p = subprocess.Popen([sys.executable, "-c", HOLDER, self.dir.name, "30"], stdout=subprocess.PIPE, env=env, text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(), "held")
            with self.assertRaises(LockHeld) as ctx:
                ServiceLock(self.dir.name).acquire()
            self.assertEqual(ctx.exception.holder_pid, p.pid)
            p.kill(); p.wait(timeout=5)  # abrupt death: kernel drops the flock, no stale lock
            lk = ServiceLock(self.dir.name).acquire()
            lk.release()
        finally:
            if p.poll() is None:
                p.kill(); p.wait()

    def test_stale_pid_file_without_holder_is_not_a_lock(self):
        (Path(self.dir.name) / "service.lock").write_text("999999\n")
        lk = ServiceLock(self.dir.name).acquire()
        self.assertEqual(int((Path(self.dir.name) / "service.lock").read_text()), os.getpid())
        lk.release()


@unittest.skipUnless(os.name == "posix", "flock semantics tested on POSIX only")
class ServiceCli(unittest.TestCase):
    """End-to-end through `osrs-ee service`: duplicate instance refused; orphan reconciled on next start."""

    def _cfg(self, d: str) -> str:
        text = (Path(__file__).resolve().parent.parent / "config.example.toml").read_text()
        text = text.replace('data_dir = "data"', f'data_dir = "{d}/data"')
        p = Path(d) / "c.toml"
        p.write_text(text)
        return str(p)

    def _run(self, *argv):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from osrs_ee import cli
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_second_service_on_same_data_dir_is_refused_with_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            (Path(d) / "data").mkdir()
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            p = subprocess.Popen([sys.executable, "-c", HOLDER, f"{d}/data", "30"], stdout=subprocess.PIPE, env=env, text=True)
            try:
                self.assertEqual(p.stdout.readline().strip(), "held")
                code, out, err = self._run("service", "--config", cfg, "--max-ticks", "2", "--fast")
                self.assertEqual(code, 2)
                self.assertIn("One service per data_dir", err)
                self.assertFalse((Path(d) / "data" / "store.sqlite").exists())  # refused before touching the store
            finally:
                p.kill(); p.wait()

    def test_orphaned_running_session_is_reconciled_to_recovery_required_on_next_start(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg(d)
            from osrs_ee.config import load_config
            c = load_config(cfg)
            Path(c.target.data_dir).mkdir(parents=True)
            # leave an orphan under the configured account id
            s = Store.open(c.store_path, now=T0)
            a = c.account
            s.create_account(a.account_id, a.alias, a.auth_mode, a.credential_ref, now=T0)
            acc = s.get_account(a.account_id)
            for st in ("PENDING_DISCOVERY", "DISCOVERING", "READY"):
                acc = s.transition(a.account_id, st, expected_version=acc.state_version, reason="t", now=T0)
            s.acquire_lease(a.account_id, lease_id="lease_dead", session_id="sess_dead", client_instance_id="client_dead",
                            expected_version=acc.state_version, ttl_seconds=3600, now=T0)
            acc = s.get_account(a.account_id)
            acc = s.transition(a.account_id, "STARTING", expected_version=acc.state_version, reason="t", now=T0)
            s.transition(a.account_id, "RUNNING", expected_version=acc.state_version, reason="t", now=T0)
            s._conn.close()
            code, out, err = self._run("service", "--config", cfg, "--max-ticks", "2", "--fast")
            rep = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(rep["orphaned_sessions_reconciled"], [a.account_id])
            self.assertEqual((rep["state_before"], rep["final_state"]), ("RECOVERY_REQUIRED", "RECOVERY_REQUIRED"))
            self.assertIn("start.refused", [e["kind"] for e in rep["events"]])
            self.assertTrue(rep["lock"].endswith("service.lock"))
            # the lock is released after the run: a second run is possible (and still refuses to start)
            code, out, _ = self._run("service", "--config", cfg, "--max-ticks", "1", "--fast")
            self.assertEqual((code, json.loads(out)["orphaned_sessions_reconciled"]), (0, []))
