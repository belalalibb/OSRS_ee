"""S04c-local — Service loop with FakeSupervisor/FakeAdapter. Offline, injected clock.

Proves the loop's safety contract on the local machine only: it does NOT prove
anything about a real client process (S04b not implemented; ADR-007 open).
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from osrs_ee import config as c
from osrs_ee import service as sv
from osrs_ee.store import Store
from osrs_ee.supervisor import FakeSupervisor
from osrs_ee.telegram import FakeTransport, Outbox, Redactor
from osrs_ee.worker import AdapterFailure, AdapterResponse, FakeAdapter
from tests.test_store import T0, fixture

ACC = "acc_local001"
CLIENT = "client_service01"


class Clock:
    def __init__(self, step_seconds: float = 1.0):
        self.now, self.step = T0, timedelta(seconds=step_seconds)

    def __call__(self):
        self.now += self.step
        return self.now


def cfg_text(**over) -> str:
    text = c.example_toml()
    for old, new in over.items():
        assert old in text, old
        text = text.replace(old, new)
    return text


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store.open(Path(self.dir.name) / "store.sqlite", now=T0)
        self.clock = Clock()
        self.transport = FakeTransport()

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def observation(self, epoch=1, version=6):  # READY=3 -> LEASED 4 -> STARTING 5 -> RUNNING 6
        obs = fixture("Observation", "basic")
        obs["account_id"], obs["client_instance_id"] = ACC, CLIENT
        obs["session_epoch"], obs["state_version"] = epoch, version
        return obs

    def intent(self, name="noop", epoch=1, version=6, **over):
        i = fixture("CommandIntent", name)
        i["account_id"], i["session_id"], i["client_instance_id"] = ACC, f"sess_service_{epoch:03d}", CLIENT
        i["session_epoch"], i["expected_state_version"] = epoch, version
        i["lease_id"] = f"lease_service{epoch:03d}"
        i["expires_at"] = "2026-10-23T19:30:00Z"  # inside the 3600s lease; issued_at from fixture (T0+1s)
        i.update(over)
        return i

    def make(self, *, adapter=None, sup=None, intents=(), outbox=False, extra=None, **cfg_over):
        text = cfg_text(**cfg_over) if cfg_over else c.example_toml()
        self.cfg = c.load_config_text(text + (extra or ""))
        self.adapter = adapter or FakeAdapter(self.observation())
        self.sup = sup or FakeSupervisor()
        ob = None
        if outbox:
            ob = Outbox(self.transport, Redactor(aliases={ACC: "alias:local"}))
        sv.bootstrap_account(self.store, self.cfg, T0)
        return sv.Service(self.store, self.cfg, self.adapter, self.sup, ob, clock=self.clock, intents=intents, alert_chat_id=7)

    def reasons(self):
        return [t[4] for t in self.store.transitions(ACC)]


class Bootstrap(ServiceCase):
    def test_bootstrap_creates_and_reaches_ready_idempotently(self):
        cfg = c.load_config_text(c.example_toml())
        self.assertEqual(sv.bootstrap_account(self.store, cfg, T0), "READY")
        self.assertEqual(sv.bootstrap_account(self.store, cfg, T0), "READY")
        self.assertEqual(self.store.get_account(ACC).state_version, 3)

    def test_bootstrap_never_auto_readies_recovery(self):
        cfg = c.load_config_text(c.example_toml())
        sv.bootstrap_account(self.store, cfg, T0)
        acc = self.store.get_account(ACC)
        self.store.transition(ACC, "RECOVERY_REQUIRED", expected_version=acc.state_version, reason="test", now=T0)
        self.assertEqual(sv.bootstrap_account(self.store, cfg, T0), "RECOVERY_REQUIRED")
        self.assertEqual(self.store.get_account(ACC).state, "RECOVERY_REQUIRED")


class StopAndDrain(ServiceCase):
    def test_clean_run_dispatches_then_max_ticks_stops_in_resting(self):
        adapter = FakeAdapter(self.observation()).script(AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_service001",)))
        svc = self.make(adapter=adapter, intents=[self.intent()])
        res = svc.run(max_ticks=5)
        self.assertEqual(res.final_state, "RESTING")
        self.assertEqual(res.stop_reason, "max_ticks")
        self.assertEqual(self.store.get_command("cmd_demo002").phase, "VERIFIED")
        self.assertIn("session.started", res.kinds())
        self.assertIn("command.dispatched", res.kinds())
        self.assertEqual(self.sup.starts, 1)
        self.assertEqual(self.sup.stops, 1)
        self.assertIsNone(self.store.active_lease(ACC))
        self.assertNotIn("READY", [t[1] for t in self.store.transitions(ACC)][3:])  # never READY after start

    def test_request_stop_is_honoured_before_next_step(self):
        svc = self.make(intents=[self.intent()])
        self.assertTrue(svc.run_once())  # start
        svc.request_stop("operator.stop")
        self.assertFalse(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RESTING")
        self.assertEqual(self.adapter.dispatched, [])  # queued intent dropped, never journaled past PREPARED
        self.assertIn("operator.stop", self.reasons())

    def test_unknown_in_flight_settles_to_recovery_required_and_never_restarts(self):
        adapter = FakeAdapter(self.observation()).script(AdapterFailure("socket reset"))
        svc = self.make(adapter=adapter, intents=[self.intent()])
        res = svc.run(max_ticks=10)
        self.assertEqual(res.final_state, "RECOVERY_REQUIRED")
        self.assertEqual(self.store.get_command("cmd_demo002").phase, "UNKNOWN")
        self.assertIn("command.unknown", res.kinds())
        self.assertNotIn("restart", res.kinds())
        self.assertEqual(res.restarts, 0)
        self.assertEqual(self.sup.starts, 1)

    def test_no_exit_proof_settles_to_recovery_required(self):
        svc = self.make(sup=FakeSupervisor(exit_on_stop=False))
        svc.run_once()
        svc.request_stop("operator.stop")
        svc.run_once()
        self.assertEqual(self.store.get_account(ACC).state, "RECOVERY_REQUIRED")
        self.assertIn("supervisor.no_exit_proof", self.reasons())
        self.assertIn("supervisor.no_exit_proof", [e.kind for e in svc.events])


class CrashFreezeRestart(ServiceCase):
    def test_crash_restarts_within_budget_then_circuit_opens(self):
        svc = self.make(sup=FakeSupervisor(crash_at_tick=2), **{"restart_budget = 3": "restart_budget = 2"})
        res = svc.run(max_ticks=50)
        self.assertEqual(res.restarts, 2)
        self.assertEqual(self.sup.starts, 3)
        self.assertIn("CIRCUIT_OPEN", res.kinds())
        self.assertEqual(res.final_state, "RESTING")
        self.assertEqual(res.kinds().count("client.crashed"), 3)
        self.assertTrue(svc.health.circuit_open)
        # Every restart went RESTING -> READY with an explicit reason; nothing else wrote READY.
        ready_reasons = [t[4] for t in self.store.transitions(ACC) if t[1] == "READY"]
        self.assertEqual(ready_reasons, ["service.bootstrap", "service.restart", "service.restart"])

    def test_freeze_is_detected_from_ticks_and_restarted(self):
        svc = self.make(sup=FakeSupervisor(freeze_at_tick=2), **{"freeze_after_seconds = 30": "freeze_after_seconds = 3",
                                                                   "restart_budget = 3": "restart_budget = 1"})
        res = svc.run(max_ticks=40)
        self.assertIn("client.frozen", res.kinds())
        self.assertEqual(res.restarts, 1)
        self.assertEqual(self.sup.starts, 2)
        self.assertIn("CIRCUIT_OPEN", res.kinds())
        self.assertEqual(res.final_state, "RESTING")

    def test_crash_with_unknown_command_never_restarts(self):
        # Dispatch fails mid-flight (UNKNOWN) on tick 2 → RECOVERY_REQUIRED; a later crash must not restart.
        adapter = FakeAdapter(self.observation()).script(AdapterFailure("lost"))
        svc = self.make(adapter=adapter, sup=FakeSupervisor(crash_at_tick=5), intents=[self.intent()])
        res = svc.run(max_ticks=20)
        self.assertEqual(res.final_state, "RECOVERY_REQUIRED")
        self.assertEqual(res.restarts, 0)
        self.assertEqual(self.sup.starts, 1)


class Pressure(ServiceCase):
    def test_admission_denies_start_when_disk_low(self):
        svc = self.make(sup=FakeSupervisor(disk_free_bytes=10), outbox=True)
        res = svc.run(max_ticks=5)
        self.assertEqual(res.final_state, "READY")
        self.assertEqual(self.sup.starts, 0)
        self.assertIn("start.denied", res.kinds())
        self.assertIsNone(self.store.active_lease(ACC))

    def test_pressure_during_run_stops_orderly(self):
        sup = FakeSupervisor()
        svc = self.make(sup=sup)
        self.assertTrue(svc.run_once())  # started
        sup.rss_bytes = 10 * 1024 ** 3  # over the 2 GiB limit
        self.assertFalse(svc.run_once())
        self.assertEqual(self.store.get_account(ACC).state, "RESTING")
        self.assertEqual(svc.stop_reason, "resources.pressure")
        self.assertIn("resources.pressure", self.reasons())
        self.assertTrue(sup.stop_requested)


class Alerts(ServiceCase):
    def test_alerts_are_redacted_and_delivered(self):
        svc = self.make(sup=FakeSupervisor(crash_at_tick=2), outbox=True, **{"restart_budget = 3": "restart_budget = 0"})
        res = svc.run(max_ticks=10)
        self.assertIn("CIRCUIT_OPEN", res.kinds())
        self.assertGreaterEqual(len(self.transport.sent), 2)
        for m in self.transport.sent:
            self.assertEqual(m.kind, "ALERT")
            self.assertNotIn(ACC, m.text)
            self.assertIn("alias:local", m.text)
        self.assertTrue(any("CIRCUIT_OPEN" in m.text for m in self.transport.sent))

    def test_alert_failing_redaction_is_never_sent(self):
        svc = self.make(outbox=True)
        svc.outbox.redactor.register_canary("CANARY-SECRET-123")
        svc._emit("test.alert", "leak CANARY-SECRET-123 here", alert=True)
        self.assertEqual(len(svc.outbox), 0)
        self.assertIn("alert.redaction_refused", [e.kind for e in svc.events])


if __name__ == "__main__":
    unittest.main()
