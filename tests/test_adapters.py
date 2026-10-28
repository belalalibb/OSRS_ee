"""S04a — adapter tooling: conformance suite, recording→replay round-trip,
redaction of traces, replay strictness. All offline; no client."""
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from osrs_ee import worker
from osrs_ee.adapters import (AdapterFailure, AdapterResponse, FakeAdapter, RecordingAdapter, ReplayAdapter,
                              TraceWriter, load_trace, run_conformance)
from osrs_ee.adapters.replay import ReplayError, ReplayExhausted, ReplayMismatch
from osrs_ee.telegram import RedactionError, Redactor
from tests.test_store import ACC, T0, StoreCase, fixture

CANARY = "canary-secret-ZXCV1234"


def obs_at(t=T0, **over):
    o = fixture("Observation", "basic")
    ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    o["observed_at"] = ts
    for f in o["fields"].values():
        f["observed_at"] = ts
    o.update(over)
    return o


def finding(rep, prefix):
    return next(f for f in rep.findings if f.check.startswith(prefix))


class Conformance(unittest.TestCase):
    def test_fake_adapter_passes(self):
        a = FakeAdapter(obs_at()).script(AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_x",)))
        rep = run_conformance(a, now=T0)
        self.assertTrue(rep.passed, rep.to_dict())
        self.assertEqual({f.check[:2] for f in rep.findings}, {"C1", "C2", "C3", "C4", "C5", "C6", "C7"})

    def test_future_observation_fails_c2(self):
        rep = run_conformance(FakeAdapter(obs_at(T0 + timedelta(seconds=5))), now=T0)
        self.assertFalse(rep.passed)
        self.assertFalse(finding(rep, "C2").passed)

    def test_invalid_observation_fails_c1_without_raising(self):
        class Bad:
            def observe(self, now):
                return {"schema_version": "1.0"}
            def dispatch(self, intent, *, deadline, now):
                return None
        rep = run_conformance(Bad(), now=T0)
        self.assertFalse(rep.passed)
        self.assertFalse(finding(rep, "C1").passed)

    def test_foreign_exception_fails_c5_and_bad_enum_fails_c4(self):
        class Leaky(FakeAdapter):
            def dispatch(self, intent, *, deadline, now):
                raise KeyError("boom")
        self.assertFalse(finding(run_conformance(Leaky(obs_at()), now=T0), "C5").passed)
        a = FakeAdapter(obs_at()).script(AdapterResponse("MAYBE", "VERIFIED", ("e",)))
        self.assertFalse(finding(run_conformance(a, now=T0), "C4").passed)

    def test_adapter_failure_is_allowed_and_verified_without_evidence_fails_c6(self):
        a = FakeAdapter(obs_at()).script(AdapterFailure("link down"))
        self.assertTrue(finding(run_conformance(a, now=T0), "C5").passed)
        b = FakeAdapter(obs_at()).script(AdapterResponse("ACKNOWLEDGED", "VERIFIED", ()))
        self.assertFalse(finding(run_conformance(b, now=T0), "C6").passed)

    def test_unsafe_probe_refused(self):
        rep = run_conformance(FakeAdapter(obs_at()), now=T0, probe_intent=fixture("CommandIntent", "bank_withdraw"))
        self.assertFalse(rep.passed)
        self.assertIn("C0 probe-safe", [f.check for f in rep.findings])

    def test_network_attempt_fails_c7(self):
        import socket
        class Netty(FakeAdapter):
            def dispatch(self, intent, *, deadline, now):
                s = socket.socket()
                try:
                    s.connect(("203.0.113.1", 9))
                finally:
                    s.close()
                return None
        rep = run_conformance(Netty(obs_at()), now=T0)
        self.assertFalse(finding(rep, "C7").passed)
        self.assertTrue(finding(rep, "C5").passed)  # the guard turned it into AdapterFailure


class RecordReplay(StoreCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.trace = Path(self.tmp.name) / "trace.jsonl"
        self.red = Redactor(aliases={ACC: "alias:demo"})

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def _record(self, *responses):
        inner = FakeAdapter(obs_at(session_epoch=1, state_version=6)).script(*responses)
        w = TraceWriter(self.trace, self.red).open(now=T0)
        rec = RecordingAdapter(inner, w)
        self.lease()
        wk = worker.Worker(self.s, rec, ACC, worker.WorkerConfig(config_hash="c" * 64, policy_version=1))
        wk.start(now=T0)
        return wk, rec, w

    def test_round_trip_matches_worker_outcomes(self):
        wk, rec, w = self._record(AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_demo002",)), None, AdapterFailure("x"))
        outcomes = []
        for i, cid in enumerate(("cmd_aa1", "cmd_aa2", "cmd_aa3")):
            intent = self.intent(command_id=cid, session_epoch=1, expected_state_version=6, config_hash="c" * 64,
                                 issued_at="2026-10-23T19:00:00Z", expires_at="2026-10-23T19:00:30Z")
            if i == 2:  # after an UNKNOWN the account is RECONCILING: only SAFE_OPERATIONS may dispatch
                intent.update(operation="NOOP", params={})
            wk.enqueue(intent)
            outcomes.append(wk.step(now=T0 + timedelta(seconds=1)).phase)
        w.close()
        self.assertEqual(outcomes, ["VERIFIED", "UNKNOWN", "UNKNOWN"])
        records = load_trace(self.trace)
        self.assertEqual([r["t"] for r in records], ["observe", "dispatch"] * 3)
        self.assertEqual([r["seq"] for r in records], list(range(1, 7)))
        self.assertEqual([r["result"]["kind"] for r in records if r["t"] == "dispatch"], ["response", "timeout", "failure"])
        text = self.trace.read_text()
        self.assertNotIn(ACC, text)
        self.assertIn(w.pseudonym(ACC), text)
        self.assertNotIn("alias:demo", text)  # free-text alias is not contract-valid; pseudonym is
        rp = ReplayAdapter(records)
        self.assertEqual(rp.remaining, (3, 3))
        self.assertEqual(rp.observe(T0)["account_id"], w.pseudonym(ACC))
        r1 = rp.dispatch(records[1]["intent"], deadline=T0, now=T0)
        self.assertEqual((r1.transport_status, r1.effect_status, r1.evidence_refs), ("ACKNOWLEDGED", "VERIFIED", ("obs_demo002",)))
        self.assertIsNone(rp.dispatch(records[3]["intent"], deadline=T0, now=T0))
        with self.assertRaises(AdapterFailure):
            rp.dispatch(records[5]["intent"], deadline=T0, now=T0)
        with self.assertRaises(ReplayExhausted):
            rp.dispatch(records[5]["intent"], deadline=T0, now=T0)

    def test_canary_in_observation_is_withheld_not_written(self):
        self.red.register_canary(CANARY)
        obs = obs_at(session_epoch=1, state_version=6)
        obs["fields"]["client.logged_in"]["source"] = f"agent.{CANARY}"
        w = TraceWriter(self.trace, self.red).open(now=T0)
        rec = RecordingAdapter(FakeAdapter(obs), w)
        with self.assertRaises(RedactionError):
            rec.observe(T0)
        w.close()
        self.assertNotIn(CANARY, self.trace.read_text())
        self.assertEqual((w.records_written, w.records_rejected), (1, 1))  # header only

    def test_secret_shaped_intent_param_is_withheld(self):
        w = TraceWriter(self.trace, self.red).open(now=T0)
        rec = RecordingAdapter(FakeAdapter(obs_at()).script(None), w)
        intent = self.intent(params={"item_id": 1, "quantity": 1, "noted": False, "note": "password: hunter2hunter2"})  # secret-scan: allow (synthetic canary)
        with self.assertRaises(RedactionError):
            rec.dispatch(intent, deadline=T0, now=T0)
        w.close()
        self.assertNotIn("hunter2", self.trace.read_text())

    def test_replay_strict_mismatch_and_malformed_traces(self):
        w = TraceWriter(self.trace, self.red).open(now=T0)
        rec = RecordingAdapter(FakeAdapter(obs_at()).script(None), w)
        rec.observe(T0)
        rec.dispatch(self.intent(command_id="cmd_rec01"), deadline=T0, now=T0)
        w.close()
        rp = ReplayAdapter.from_file(self.trace)
        with self.assertRaises(ReplayMismatch):
            rp.dispatch(self.intent(command_id="cmd_other01"), deadline=T0, now=T0)
        rp2 = ReplayAdapter.from_file(self.trace, strict=False)
        self.assertIsNone(rp2.dispatch(self.intent(command_id="cmd_other01"), deadline=T0, now=T0))
        lines = self.trace.read_text().splitlines()
        bad = Path(self.tmp.name) / "bad.jsonl"
        hdr = json.loads(lines[0]); hdr["redacted"] = False
        bad.write_text("\n".join([json.dumps(hdr)] + lines[1:]) + "\n")
        with self.assertRaises(ReplayError):
            load_trace(bad)
        gap = Path(self.tmp.name) / "gap.jsonl"
        r2 = json.loads(lines[2]); r2["seq"] = 5
        gap.write_text("\n".join([lines[0], lines[1], json.dumps(r2)]) + "\n")
        with self.assertRaises(ReplayError):
            load_trace(gap)
        with self.assertRaises(ReplayError):
            ReplayAdapter([json.loads(lines[2])])

    def test_replay_adapter_passes_conformance(self):
        w = TraceWriter(self.trace, self.red).open(now=T0)
        rec = RecordingAdapter(FakeAdapter(obs_at()).script(AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("e1",))), w)
        rec.observe(T0)
        rec.dispatch(fixture("CommandIntent", "noop") | {"operation": "OBSERVE", "command_id": "cmd_conformance_probe01"},
                     deadline=T0, now=T0)
        rec.observe(T0)
        w.close()
        rep = run_conformance(ReplayAdapter.from_file(self.trace), now=T0)
        self.assertTrue(rep.passed, rep.to_dict())


if __name__ == "__main__":
    unittest.main()
