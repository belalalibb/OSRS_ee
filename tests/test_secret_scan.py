"""SEC-03 — `osrs-ee secret-scan` (metadata-only) and `python -m osrs_ee` entry point."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from osrs_ee import cli
from osrs_ee import secret_scan as ss

ROOT = Path(__file__).resolve().parents[1]
# Synthetic shapes only (never real). Built by concatenation so this file itself stays clean.
FAKE_TG = "123456789:" + "FAKE_" + "x" * 31
FAKE_GH = "ghp_" + "F" * 36
FAKE_SK = "sk-" + "FAKE" * 6


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ScanText(unittest.TestCase):
    def test_finds_shapes_and_reports_metadata_only(self):
        text = f"a = '{FAKE_TG}'\nb = '{FAKE_GH}'\nkey = '{FAKE_SK}'\npassword = hunter2hunter2\n"
        f = ss.scan_text(text, "x.py")
        self.assertEqual([x.pattern for x in f], ["telegram_bot_token", "github_pat_classic", "openai_style_key", "literal_assignment"])
        self.assertEqual([x.line for x in f], [1, 2, 3, 4])
        dumped = json.dumps([x.to_dict() for x in f])
        for v in (FAKE_TG, FAKE_GH, FAKE_SK, "hunter2"):
            self.assertNotIn(v, dumped)  # metadata only, never the value

    def test_refs_env_placeholders_and_allow_marker_are_not_findings(self):
        clean = ("bot_token_ref = \"ref:env:TG_BOT_TOKEN\"\napi_key = ${OPENAI_KEY}\ntoken = ref:vault:x\n"
                 f"canary = '{FAKE_GH}'  # secret-scan: allow (synthetic)\n")
        self.assertEqual(ss.scan_text(clean, "c.toml"), [])

    def test_private_key_block_is_found(self):
        block = "-----BEGIN RSA " + "PRIVATE KEY-----\n"  # concatenated so this file stays clean
        self.assertEqual(ss.scan_text(block, "k.pem")[0].pattern, "private_key_block")


class ScanPath(unittest.TestCase):
    def test_walk_skips_git_and_binaries_and_reports_relative_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir(); (root / ".git" / "config").write_text(f"t={FAKE_GH}\n")
            (root / "sub").mkdir(); (root / "sub" / "a.py").write_text(f"T = '{FAKE_TG}'\n")
            (root / "bin.dat").write_bytes(b"\x00\x01" + FAKE_GH.encode())
            (root / "ok.md").write_text("token = ref:env:X\n")
            findings, n = ss.scan_path(root)
            self.assertEqual([(f.path, f.pattern) for f in findings], [("sub/a.py", "telegram_bot_token")])
            self.assertEqual(n, 2)  # sub/a.py + ok.md; .git and the binary are skipped

    def test_repository_is_clean(self):
        """Regression: the committed tree must stay clean (canaries carry the allow marker)."""
        findings, n = ss.scan_path(ROOT)
        self.assertGreater(n, 50)
        self.assertEqual([f.to_dict() for f in findings], [])


class Cli(unittest.TestCase):
    def test_secret_scan_exit_codes_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "clean.txt").write_text("nothing here\n")
            code, out, _ = run("secret-scan", d)
            doc = json.loads(out)
            self.assertEqual((code, doc["verdict"], doc["findings"]), (0, "CLEAN", []))
            (Path(d) / "leak.txt").write_text(f"x={FAKE_GH}\n")
            code, out, _ = run("secret-scan", d)
            doc = json.loads(out)
            self.assertEqual((code, doc["verdict"]), (2, "REVIEW_REQUIRED"))
            self.assertEqual(doc["findings"][0]["path"], "leak.txt")
            self.assertNotIn(FAKE_GH, out)
            code, _, err = run("secret-scan", str(Path(d) / "missing"))
            self.assertEqual(code, 1)

    @unittest.skipUnless(os.name == "posix", "permission bits are POSIX")
    def test_secret_scan_config_reports_world_readable_store(self):
        with tempfile.TemporaryDirectory() as d:
            text = (ROOT / "config.example.toml").read_text().replace('data_dir = "data"', f'data_dir = "{d}/data"')
            cfg = Path(d) / "c.toml"; cfg.write_text(text)
            data = Path(d) / "data"; data.mkdir()
            store = data / "store.sqlite"; store.write_bytes(b""); store.chmod(0o644)
            code, out, _ = run("secret-scan", d, "--config", str(cfg))
            doc = json.loads(out)
            self.assertEqual(code, 2)
            self.assertTrue(any(p["path"].endswith("store.sqlite") for p in doc["permission_issues"]))
            store.chmod(0o600); data.chmod(0o700)
            code, out, _ = run("secret-scan", d, "--config", str(cfg))
            self.assertEqual((code, json.loads(out)["permission_issues"]), (0, []))


class MainModule(unittest.TestCase):
    def test_python_m_osrs_ee_matches_console_script(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        r = subprocess.run([sys.executable, "-m", "osrs_ee", "status"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip())
        r2 = subprocess.run([sys.executable, "-m", "osrs_ee"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r2.returncode, 2)  # argparse: subcommand required
