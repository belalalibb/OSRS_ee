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
        self.assertEqual(names, {"status", "validate", "store", "demo"})
