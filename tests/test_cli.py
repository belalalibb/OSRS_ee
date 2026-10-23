"""CLI smoke tests: the entry point must only expose what actually exists (no fake 'run bot')."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from osrs_ee import cli

FIX = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CLI(unittest.TestCase):
    def test_status_declares_unimplemented_components(self):
        code, out, _ = run("status")
        info = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIn("NOT IMPLEMENTED", info["components"]["game client adapter / JVM / GUI supervisor"])

    def test_validate_exit_codes(self):
        self.assertEqual(run("validate", "CommandIntent", str(FIX / "valid/CommandIntent/noop.json"))[0], 0)
        bad = next((FIX / "invalid/CommandIntent").glob("*.json"))
        code, _, err = run("validate", "CommandIntent", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("INVALID", err)

    def test_store_init_and_show(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "s.sqlite")
            code, out, _ = run("store", "init", p)
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(out)["integrity_ok"])
            code, out, _ = run("store", "show", p)
            self.assertEqual(json.loads(out)["schema_version"], "1")
            self.assertEqual(run("store", "show", str(Path(d) / "missing.sqlite"))[0], 1)

    def test_demo_is_labelled_simulated_and_settles(self):
        code, out, _ = run("demo")
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertIn("SIMULATED", res["mode"])
        self.assertEqual(res["worker_step"]["phase"], "VERIFIED")
        self.assertEqual(res["final_account_state"], "RESTING")

    def test_no_run_bot_subcommand_exists(self):
        parser = cli.build_parser()
        names = set(parser._subparsers._group_actions[0].choices)  # type: ignore[attr-defined]
        self.assertEqual(names, {"status", "validate", "store", "demo", "target-check", "conformance", "replay"})
        self.assertFalse(names & {"run", "run-bot", "start", "play", "login"})


class CLIS04a(unittest.TestCase):
    def test_target_check_in_sandbox_exits_2_with_missing_list(self):
        code, out, _ = run("target-check", "--no-java-probe")
        rep = json.loads(out)
        self.assertEqual(code, 2)
        self.assertFalse(rep["ready_for_s04b"])
        self.assertTrue(any("ADR-007" in m for m in rep["missing"]))

    def test_conformance_builtin_fake_passes(self):
        code, out, _ = run("conformance")
        rep = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(rep["passed"])
        self.assertIn("FakeAdapter", rep["adapter"])

    def test_replay_reproduces_recorded_phase_and_refuses_unredacted(self):
        from datetime import datetime, timedelta, timezone
        from osrs_ee import worker
        from osrs_ee.adapters import RecordingAdapter, TraceWriter
        from osrs_ee.store import Store
        from osrs_ee.telegram import Redactor
        t0 = datetime(2026, 10, 23, 19, 0, tzinfo=timezone.utc)
        obs = json.loads((FIX / "valid" / "Observation" / "basic.json").read_text()) | {"session_epoch": 1, "state_version": 6}
        intent = json.loads((FIX / "valid" / "CommandIntent" / "bank_withdraw.json").read_text()) | {
            "session_epoch": 1, "expected_state_version": 6, "config_hash": "c" * 64}
        with tempfile.TemporaryDirectory() as d:
            s = Store.open(Path(d) / "s.sqlite", now=t0)
            s.create_account("acc_demo001", "demo", "UNKNOWN", "ref:vault:x", now=t0)
            for v, st in enumerate(("PENDING_DISCOVERY", "DISCOVERING", "READY")):
                s.transition("acc_demo001", st, expected_version=v, reason="t", now=t0)
            s.acquire_lease("acc_demo001", lease_id="lease_demo001", session_id="sess_demo001",
                            client_instance_id="client_demo001", expected_version=3, ttl_seconds=3600, now=t0)
            trace = Path(d) / "trace.jsonl"
            w = TraceWriter(trace, Redactor(aliases={"acc_demo001": "alias:demo"})).open(now=t0)
            rec = RecordingAdapter(worker.FakeAdapter(obs).script(worker.AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_demo002",))), w)
            wk = worker.Worker(s, rec, "acc_demo001", worker.WorkerConfig(config_hash="c" * 64, policy_version=1))
            wk.start(now=t0); wk.enqueue(intent)
            self.assertEqual(wk.step(now=t0 + timedelta(seconds=1)).phase, "VERIFIED")
            w.close(); s.close()
            code, out, _ = run("replay", str(trace))
            rep = json.loads(out)
            self.assertEqual(code, 0)
            self.assertIn("REPLAY", rep["mode"])
            self.assertEqual([x["phase"] for x in rep["steps"]], ["VERIFIED"])
            self.assertEqual(rep["final_account_state"], "RESTING")
            lines = trace.read_text().splitlines()
            hdr = json.loads(lines[0]); hdr["redacted"] = False
            bad = Path(d) / "bad.jsonl"; bad.write_text("\n".join([json.dumps(hdr)] + lines[1:]) + "\n")
            code, _, err = run("replay", str(bad))
            self.assertEqual(code, 1)
            self.assertIn("not marked redacted", err)
