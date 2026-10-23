"""S03 worker/scheduler/fake adapter/cancellation/health tests.
Pure/local parts of T16/T17/T21/T29. Injected clock; no sockets, threads or sleeps.
Does NOT prove anything about a real client, JVM or OS process supervision."""
from __future__ import annotations

from datetime import timedelta

from osrs_ee import store as st
from osrs_ee import worker as wk
from tests.test_store import ACC, T0, StoreCase, fixture

CFG = wk.WorkerConfig(config_hash="c" * 64, policy_version=1, observation_max_age_seconds=10, dispatch_timeout_seconds=30, max_queue=3)
ACK_VERIFIED = wk.AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_demo002",))
ACK_UNKNOWN = wk.AdapterResponse("ACKNOWLEDGED", "UNKNOWN")
REJECTED = wk.AdapterResponse("REJECTED", "NOT_ATTEMPTED", (), "POLICY_DENIED")


def observation(**over):
    o = fixture("Observation", "basic")
    o["session_epoch"], o["state_version"] = 1, 6
    o.update(over)
    return o


class WorkerCase(StoreCase):
    def setUp(self):
        super().setUp()
        self.lease()
        self.adapter = wk.FakeAdapter(observation())
        self.w = wk.Worker(self.s, self.adapter, ACC, CFG)
        self.w.start(now=T0)

    def intent(self, **over):  # type: ignore[override]
        i = fixture("CommandIntent", "bank_withdraw")
        i["session_epoch"], i["expected_state_version"], i["config_hash"] = 1, 6, "c" * 64
        i.update(over)
        return i

    def noop(self, cid="cmd_noop0001"):
        return self.intent(command_id=cid, operation="NOOP", params={})


class Lifecycle(WorkerCase):
    def test_start_runs_through_store_transitions(self):
        acc = self.s.get_account(ACC)
        self.assertEqual((acc.state, acc.state_version), ("RUNNING", 6))
        self.assertEqual([t[1] for t in self.s.transitions(ACC)][-3:], ["LEASED", "STARTING", "RUNNING"])

    def test_idle_step_is_noop(self):
        self.assertEqual(self.w.step(now=T0).outcome, "IDLE")
        self.assertEqual(self.adapter.dispatched, [])


class Dispatch(WorkerCase):
    def test_verified_round_trip_journals_every_phase(self):
        self.adapter.script(ACK_VERIFIED)
        self.assertTrue(self.w.enqueue(self.intent()).allowed)
        r = self.w.step(now=T0 + timedelta(seconds=2))
        self.assertEqual((r.outcome, r.phase), ("DISPATCHED", "VERIFIED"))
        self.assertEqual(len(self.adapter.dispatched), 1)
        self.assertEqual(self.s.unknown_pending(ACC), 0)

    def test_guard_denial_is_not_sent_and_never_reaches_adapter(self):
        self.w.enqueue(self.intent(expected_state_version=5))  # stale version
        r = self.w.step(now=T0 + timedelta(seconds=2))
        self.assertEqual((r.outcome, r.phase, r.reason_code), ("DENIED", "NOT_SENT", "STALE_CONTEXT"))
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "NOT_SENT")
        self.assertEqual(self.adapter.dispatched, [])

    def test_stale_observation_denies_before_dispatch(self):
        self.w.enqueue(self.intent())
        r = self.w.step(now=T0 + timedelta(seconds=60))  # observation older than max_age -> intent also expired
        self.assertEqual((r.outcome, r.phase), ("DENIED", "NOT_SENT"))
        self.assertIn(r.reason_code, ("STALE_CONTEXT", "DEADLINE_EXCEEDED"))
        self.assertEqual(self.adapter.dispatched, [])

    def test_unknown_field_denies_action_but_allows_noop(self):
        obs = observation()
        obs["fields"]["bank.items"]["quality"] = "UNKNOWN"
        obs["fields"]["bank.items"]["value"] = None
        self.adapter.observation = obs
        self.adapter.script(ACK_VERIFIED)
        self.w.enqueue(self.intent())
        self.w.enqueue(self.noop())
        r1 = self.w.step(now=T0 + timedelta(seconds=1))
        r2 = self.w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual((r1.outcome, r1.reason_code), ("DENIED", "CAPABILITY_UNKNOWN"))
        self.assertEqual((r2.outcome, r2.phase), ("DISPATCHED", "VERIFIED"))

    def test_timeout_is_unknown_and_blocks_further_actions(self):
        self.adapter.script(None, ACK_VERIFIED)
        self.w.enqueue(self.intent())
        self.w.enqueue(self.intent(command_id="cmd_demo002"))
        r1 = self.w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual((r1.outcome, r1.phase, r1.reason_code), ("DISPATCHED", "UNKNOWN", "DEADLINE_EXCEEDED"))
        self.assertEqual(self.s.unknown_pending(ACC), 1)
        r2 = self.w.step(now=T0 + timedelta(seconds=2))
        self.assertEqual((r2.outcome, r2.phase, r2.reason_code), ("DENIED", "NOT_SENT", "STALE_CONTEXT"))
        self.assertEqual(len(self.adapter.dispatched), 1)  # second action never dispatched

    def test_adapter_crash_after_dispatch_is_unknown_never_not_sent(self):
        self.adapter.script(wk.AdapterFailure("pipe broke"))
        self.w.enqueue(self.intent())
        r = self.w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual((r.outcome, r.phase), ("DISPATCHED", "UNKNOWN"))
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "UNKNOWN")

    def test_rejected_transport_is_terminal_rejected(self):
        self.adapter.script(REJECTED)
        self.w.enqueue(self.intent())
        r = self.w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual((r.outcome, r.phase), ("DISPATCHED", "REJECTED"))
        self.assertEqual(self.s.unknown_pending(ACC), 0)

    def test_same_intent_twice_is_not_dispatched_twice(self):
        self.adapter.script(ACK_VERIFIED, ACK_VERIFIED)
        self.w.enqueue(self.intent())
        self.w.enqueue(self.intent())
        self.w.step(now=T0 + timedelta(seconds=1))
        r = self.w.step(now=T0 + timedelta(seconds=2))
        self.assertEqual(r.outcome, "DROPPED")
        self.assertEqual(len(self.adapter.dispatched), 1)

    def test_intent_not_bound_to_lease_is_dropped_before_journal(self):
        self.w.enqueue(self.intent(lease_id="lease_other001"))
        r = self.w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual((r.outcome, r.phase, r.reason_code), ("DROPPED", None, "STALE_CONTEXT"))
        with self.assertRaises(st.StoreError):
            self.s.get_command("cmd_demo001")


class Scheduling(WorkerCase):
    def test_queue_is_bounded(self):
        for i in range(3):
            self.assertTrue(self.w.enqueue(self.noop(f"cmd_noop000{i}")).allowed)
        d = self.w.enqueue(self.noop("cmd_noop0009"))
        self.assertEqual((d.allowed, d.reason_code), (False, "INSUFFICIENT_RESOURCES"))
        self.assertEqual(self.w.queued, 3)

    def test_replan_drops_only_unjournaled_work(self):
        self.adapter.script(ACK_VERIFIED)
        self.w.enqueue(self.intent())
        self.w.step(now=T0 + timedelta(seconds=1))
        self.w.enqueue(self.noop("cmd_noop0001"))
        self.w.enqueue(self.noop("cmd_noop0002"))
        self.assertEqual(self.w.replan("resource changed"), 2)
        self.assertEqual(self.w.queued, 0)
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "VERIFIED")  # Store commit untouched


class Cancellation(WorkerCase):
    def test_abort_closes_queue_and_denies_pending(self):
        self.w.enqueue(self.intent())
        self.w.request_abort()
        d = self.w.enqueue(self.noop())
        self.assertEqual((d.allowed, d.reason_code), (False, "POLICY_DENIED"))
        r = self.w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual((r.outcome, r.phase, r.reason_code), ("ABORTED", "NOT_SENT", "POLICY_DENIED"))
        self.assertEqual(self.adapter.dispatched, [])

    def test_drain_clean_ends_resting_and_releases_lease(self):
        self.adapter.script(ACK_VERIFIED)
        self.w.enqueue(self.intent())
        self.w.step(now=T0 + timedelta(seconds=1))
        self.w.request_abort()
        self.assertEqual(self.w.drain(now=T0 + timedelta(seconds=2)), "RESTING")
        self.assertIsNone(self.s.active_lease(ACC))
        self.assertEqual(self.s.get_account(ACC).state, "RESTING")

    def test_drain_with_unknown_ends_recovery_required_never_ready(self):
        self.adapter.script(None)
        self.w.enqueue(self.intent())
        self.w.step(now=T0 + timedelta(seconds=1))
        self.w.request_abort()
        self.assertEqual(self.w.drain(now=T0 + timedelta(seconds=2)), "RECOVERY_REQUIRED")
        self.assertIsNone(self.s.active_lease(ACC))
        # a fresh open must not "heal" it
        self.reopen(now=T0 + timedelta(seconds=3))
        self.assertEqual(self.s.get_account(ACC).state, "RECOVERY_REQUIRED")

    def test_drain_requires_abort(self):
        with self.assertRaises(st.StoreError):
            self.w.drain(now=T0)


class Health(WorkerCase):
    def test_stationary_with_live_ticks_is_not_frozen(self):
        h = wk.HealthMonitor(freeze_after_seconds=5, restart_budget=2, restart_window_seconds=60)
        self.assertEqual(h.status(T0), "UNKNOWN")
        for i in range(10):
            h.observe_tick(i, (1, 2, 0), T0 + timedelta(seconds=i))
        self.assertEqual(h.status(T0 + timedelta(seconds=12)), "OK")
        self.assertIsNotNone(h.stationary_since)

    def test_no_ticks_means_frozen_even_if_position_changes(self):
        h = wk.HealthMonitor(freeze_after_seconds=5, restart_budget=2, restart_window_seconds=60)
        h.observe_tick(1, (1, 2, 0), T0)
        h.observe_tick(1, (2, 2, 0), T0 + timedelta(seconds=10))  # same tick, "moved"
        self.assertEqual(h.status(T0 + timedelta(seconds=10)), "FROZEN")

    def test_restart_budget_opens_circuit(self):
        h = wk.HealthMonitor(freeze_after_seconds=5, restart_budget=2, restart_window_seconds=60)
        self.assertTrue(h.allow_restart(T0))
        self.assertTrue(h.allow_restart(T0 + timedelta(seconds=1)))
        self.assertFalse(h.allow_restart(T0 + timedelta(seconds=2)))
        self.assertTrue(h.circuit_open)
        self.assertFalse(h.allow_restart(T0 + timedelta(hours=1)))  # circuit stays open until operator resets
