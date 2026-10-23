"""S04a — target-check must inventory honestly and launch nothing."""
import os
import subprocess
import unittest
from unittest import mock

from osrs_ee import target_check as tc


class TargetCheck(unittest.TestCase):
    def test_sandbox_reports_missing_instead_of_failing(self):
        rep = tc.run_target_check(run_java_probe=False)
        self.assertFalse(rep.ready_for_s04b)
        joined = " ".join(rep.missing)
        self.assertIn("game client path", joined)
        self.assertIn("ADR-007", joined)
        self.assertIn("python", rep.facts)
        self.assertEqual(rep.to_dict()["ready_for_s04b"], False)

    def test_missing_java_is_a_finding(self):
        with mock.patch.object(tc.shutil, "which", return_value=None):
            rep = tc.run_target_check(run_java_probe=True)
        self.assertTrue(any("java runtime" in m for m in rep.missing))
        self.assertIsNone(rep.facts["java"]["path"])

    def test_no_subprocess_other_than_java_version(self):
        calls = []
        def fake_run(argv, **kw):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr='openjdk version "17.0.1"')
        with mock.patch.object(tc.shutil, "which", return_value="/usr/bin/java"), \
             mock.patch.object(tc.subprocess, "run", side_effect=fake_run):
            rep = tc.run_target_check(client_path="/nonexistent/client.jar")
        self.assertEqual(calls, [["/usr/bin/java", "-version"]])
        self.assertEqual(rep.facts["java"]["version"], 'openjdk version "17.0.1"')
        self.assertTrue(any("game client not found" in m for m in rep.missing))

    def test_no_java_probe_flag_runs_nothing(self):
        with mock.patch.object(tc.subprocess, "run") as run:
            tc.run_target_check(run_java_probe=False)
        run.assert_not_called()

    def test_display_detection(self):
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}):
            rep = tc.run_target_check(run_java_probe=False)
        self.assertFalse(any("graphical session" in m for m in rep.missing))
        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(tc.platform, "system", return_value="Linux"):
            rep = tc.run_target_check(run_java_probe=False)
        self.assertTrue(any("graphical session" in m for m in rep.missing))


if __name__ == "__main__":
    unittest.main()
