"""S04b-prep — generic ProcessSupervisor tested with a harmless Python child.

The child is ``sys.executable`` running a tiny loop that writes a tick counter
into the ready file. This proves spawn / readiness proof / tick / SIGTERM→SIGKILL
stop / exit proof / /proc measurement for *a process*. It proves nothing about a
game client, JVM or GUI (ADR-007 open; T06/T10/T30/T31 remain NOT_RUN).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path

from osrs_ee import config as c
from osrs_ee import measure as ms
from osrs_ee import service as sv
from osrs_ee.store import Store
from osrs_ee.supervisor import ProcessSpec, ProcessSupervisor
from osrs_ee.worker import FakeAdapter
from tests.test_service import ACC, CLIENT, Clock, cfg_text
from tests.test_store import T0, fixture

# Child: optional readiness delay, optional SIGTERM ignore, optional early exit.
CHILD = r"""
import os, signal, sys, time
ready, delay, ignore_term, exit_after = sys.argv[1], float(sys.argv[2]), sys.argv[3] == "1", float(sys.argv[4])
if ignore_term:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
t0 = time.monotonic(); tick = 0
while True:
    el = time.monotonic() - t0
    if exit_after > 0 and el >= exit_after:
        sys.exit(3)
    if el >= delay:
        tick += 1
        tmp = ready + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(f"{tick}\n")
        os.replace(tmp, ready)
    time.sleep(0.05)
"""


def _wait(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


class ProcCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ready = os.path.join(self.dir.name, "ready")
        self.sups: list[ProcessSupervisor] = []

    def tearDown(self):
        for s in self.sups:
            s.stop(T0)
        self.dir.cleanup()

    def spec(self, delay=0.0, ignore_term=False, exit_after=0.0, stop_grace_seconds=1.0):
        return ProcessSpec(argv=(sys.executable, "-c", CHILD, self.ready, str(delay), "1" if ignore_term else "0", str(exit_after)),
                           ready_file=self.ready, stop_grace_seconds=stop_grace_seconds)

    def sup(self, log=None, **kw):
        s = ProcessSupervisor(self.spec(**kw), log_path=log, data_dir=self.dir.name)
        self.sups.append(s)
        return s


class Spec(unittest.TestCase):
    def test_spec_fails_closed(self):
        with self.assertRaises(ValueError):
            ProcessSpec(argv=())
        with self.assertRaises(ValueError):
            ProcessSpec(argv=("python3",))  # relative: no PATH lookup
        with self.assertRaises(ValueError):
            ProcessSpec(argv=("/definitely/missing",))
        with self.assertRaises(ValueError):
            ProcessSpec(argv=(sys.executable,), stop_grace_seconds=0)
        with self.assertRaises(ValueError):
            ProcessSpec(argv=(sys.executable,), cwd="/definitely/missing")
        ProcessSpec(argv=(sys.executable, "-c", "pass"))


class Lifecycle(ProcCase):
    def test_ready_is_proof_not_liveness_then_orderly_sigterm_stop(self):
        s = self.sup(delay=0.4)
        self.assertFalse(s.exited(T0))
        self.assertIsNone(s.measure(T0))
        s.start(T0)
        self.assertFalse(s.ready(T0))         # alive but no proof yet
        self.assertIsNone(s.tick(T0))
        self.assertTrue(_wait(lambda: s.ready(T0)))
        t1 = s.tick(T0)
        self.assertIsInstance(t1, int)
        self.assertTrue(_wait(lambda: (s.tick(T0) or 0) > t1))
        self.assertFalse(s.exited(T0))
        s.stop(T0)
        self.assertTrue(s.exited(T0))
        self.assertEqual(s.last_stop_method, "SIGTERM")
        self.assertIsNotNone(s.last_exit_code)
        self.assertFalse(s.ready(T0))
        self.assertIsNone(s.measure(T0))

    def test_stale_ready_file_is_removed_on_start(self):
        Path(self.ready).write_text("99\n")
        s = self.sup(delay=5.0)
        s.start(T0)
        self.assertFalse(s.ready(T0))
        self.assertFalse(os.path.exists(self.ready))

    def test_sigterm_ignored_escalates_to_sigkill_with_exit_proof(self):
        s = self.sup(ignore_term=True, stop_grace_seconds=0.5)
        s.start(T0)
        self.assertTrue(_wait(lambda: s.ready(T0)))
        s.stop(T0)
        self.assertEqual(s.last_stop_method, "SIGKILL")
        self.assertTrue(s.exited(T0))

    def test_early_exit_is_detected_without_stop(self):
        s = self.sup(delay=10.0, exit_after=0.3)
        s.start(T0)
        self.assertTrue(_wait(lambda: s.exited(T0)))
        self.assertEqual(s.last_exit_code, 3)
        self.assertFalse(s.ready(T0))

    def test_double_start_refused_and_output_goes_to_log_file(self):
        log = os.path.join(self.dir.name, "child.log")
        s = self.sup(log=log)
        s.start(T0)
        with self.assertRaises(RuntimeError):
            s.start(T0)
        s.stop(T0)
        self.assertTrue(os.path.exists(log))
        self.assertEqual(s.starts, 1)

    @unittest.skipUnless(ms.proc_available(), "/proc not available")
    def test_measure_reads_the_child_not_the_parent(self):
        s = self.sup()
        s.start(T0)
        self.assertTrue(_wait(lambda: s.ready(T0)))
        self.assertIsNone(s.measure(T0))  # cpu needs two samples
        m = s.measure(T0 + timedelta(seconds=1))
        self.assertIsNotNone(m)
        self.assertEqual(set(m), {"rss_bytes", "disk_free_bytes", "open_fds", "cpu_percent"})
        self.assertNotEqual(s.pid, os.getpid())
        self.assertGreater(m["rss_bytes"], 0)


@unittest.skipUnless(ms.proc_available(), "/proc not available: Service admission needs real measurement")
class ServiceWithProcess(ProcCase):
    """Service loop driving a real child process (FakeAdapter for observations)."""

    def setUp(self):
        super().setUp()
        self.store = Store.open(Path(self.dir.name) / "store.sqlite", now=T0)

    def tearDown(self):
        self.store.close()
        super().tearDown()

    def observation(self):
        obs = fixture("Observation", "basic")
        obs["account_id"], obs["client_instance_id"] = ACC, CLIENT
        obs["session_epoch"], obs["state_version"] = 1, 6
        return obs

    def make(self, sup, host_measure="host", **over):
        over.setdefault("freeze_after_seconds = 30", "freeze_after_seconds = 2")
        over.setdefault("disk_reserve_bytes = 1073741824", "disk_reserve_bytes = 0")  # sandbox disks are small
        cfg = c.load_config_text(cfg_text(**over))
        sv.bootstrap_account(self.store, cfg, T0)
        hm = ms.host_measurer(self.dir.name, T0) if host_measure == "host" else None
        return sv.Service(self.store, cfg, FakeAdapter(self.observation()), sup, None, clock=Clock(), host_measure=hm)

    def test_without_host_measure_a_real_supervisor_never_admits(self):
        s = self.sup()
        svc = self.make(s, host_measure=None)
        self.assertFalse(svc.run_once())  # refused start ends the loop; nothing was spawned
        self.assertIn("start.refused", [e.kind for e in svc.events])
        self.assertEqual((self.store.get_account(ACC).state, s.starts), ("READY", 0))

    def test_readiness_gate_then_orderly_stop_to_resting(self):
        s = self.sup(delay=0.3)
        svc = self.make(s)
        self.assertTrue(svc.run_once())  # host snapshot admitted; LEASED -> STARTING; child spawned
        self.assertEqual(self.store.get_account(ACC).state, "STARTING")
        self.assertEqual(s.starts, 1)
        self.assertTrue(_wait(lambda: os.path.exists(self.ready)))
        self.assertTrue(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RUNNING")
        time.sleep(0.2)
        self.assertTrue(svc.run_once())  # child ticks advance; health OK
        svc.request_stop("operator.stop")
        self.assertFalse(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RESTING")
        self.assertTrue(s.exited(T0))
        self.assertEqual(s.last_stop_method, "SIGTERM")
        self.assertIsNone(self.store.active_lease(ACC))

    def test_child_crash_is_detected_and_restarted_within_budget(self):
        s = self.sup(delay=0.0, exit_after=0.6)
        svc = self.make(s, **{"restart_budget = 3": "restart_budget = 1"})
        self.assertTrue(svc.run_once())
        self.assertTrue(_wait(lambda: os.path.exists(self.ready)))
        svc.run_once()
        self.assertEqual(self.store.get_account(ACC).state, "RUNNING")
        self.assertTrue(_wait(lambda: s.exited(T0), timeout=3.0))
        for _ in range(6):
            if not svc.run_once():
                break
        kinds = [e.kind for e in svc.events]
        self.assertIn("client.crashed", kinds)
        self.assertIn("restart", kinds)
        self.assertGreaterEqual(s.starts, 2)

    def test_readiness_timeout_with_slow_child_fails_start(self):
        s = self.sup(delay=30.0)
        svc = self.make(s, **{"ready_timeout_seconds = 60": "ready_timeout_seconds = 2"})
        res = svc.run(max_ticks=8)
        self.assertEqual(res.final_state, "RECOVERY_REQUIRED")
        self.assertIn("start.failed", res.kinds())
        self.assertTrue(s.exited(T0))  # stopped and exit proven
