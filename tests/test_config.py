"""S04c-local — ServiceConfig: fail-closed TOML loading. No network, no files outside tmp."""
from __future__ import annotations

import unittest

from osrs_ee import config as c

EX = c.example_toml()


def swap(old: str, new: str) -> str:
    assert old in EX, old
    return EX.replace(old, new)


class ConfigLoading(unittest.TestCase):
    def test_example_loads_and_is_simulated(self):
        cfg = c.load_config_text(EX)
        self.assertEqual(cfg.target.mode, "simulated")
        self.assertIsNone(cfg.target.client_path)
        self.assertEqual(cfg.account.auth_mode, "UNKNOWN")
        self.assertFalse(cfg.telegram.enabled)
        self.assertEqual(str(cfg.store_path), "data/store.sqlite")
        self.assertEqual(cfg.config_hash, "c" * 64)

    def test_defaults_apply_for_missing_sections(self):
        cfg = c.load_config_text('config_hash = "%s"' % ("a" * 64))
        self.assertEqual(cfg.worker.max_queue, 16)
        self.assertEqual(cfg.health.restart_budget, 3)
        self.assertEqual(cfg.resources.fd_limit, 2048)
        self.assertEqual(cfg.network.required_route, "DIRECT")
        self.assertEqual(cfg.account.account_id, "acc_local001")

    def test_bad_hash_unknown_keys_and_typos_refused(self):
        with self.assertRaises(c.ConfigError):
            c.load_config_text('config_hash = "abc"')
        with self.assertRaises(c.ConfigError):
            c.load_config_text(EX + '\n[extra]\nx = 1\n')
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap("max_queue = 16", "max_queu = 16"))
        with self.assertRaises(c.ConfigError):
            c.load_config_text('config_hash = "%s"\nunknown_top = 1' % ("a" * 64))

    def test_secret_shaped_literals_refused_refs_accepted(self):
        for bad in ("ghp_" + "A" * 30, "123456789:" + "x" * 35, "password: hunter2"):
            with self.assertRaises(c.ConfigError, msg=bad):
                c.load_config_text(swap('alias = "alias:local"', f'alias = "{bad}"'))
        cfg = c.load_config_text(swap('credential_ref = "ref:vault:acc_local001"', 'credential_ref = "ref:keyring:main"'))
        self.assertEqual(cfg.account.credential_ref, "ref:keyring:main")
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap('credential_ref = "ref:vault:acc_local001"', 'credential_ref = "hunter2hunter2"'))

    def test_device_requires_client_path_and_auth_mode_locked(self):
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap('mode = "simulated"', 'mode = "device"'))
        cfg = c.load_config_text(swap('mode = "simulated"', 'mode = "device"\nclient_path = "/opt/client/RuneLite.jar"'))
        self.assertEqual(cfg.target.mode, "device")
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap('auth_mode = "UNKNOWN"', 'auth_mode = "PASSWORD"'))
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap('mode = "simulated"', 'mode = "live"'))

    def test_bounds_enforced(self):
        bad = (
            ("observation_max_age_seconds = 10", "observation_max_age_seconds = 0"),
            ("dispatch_timeout_seconds = 30", "dispatch_timeout_seconds = 601"),
            ("max_queue = 16", "max_queue = 0"),
            ("tick_seconds = 1.0", "tick_seconds = 0.001"),
            ("freeze_after_seconds = 30", "freeze_after_seconds = 0"),
            ("restart_budget = 3", "restart_budget = -1"),
            ("rss_limit_bytes = 2147483648", "rss_limit_bytes = 1"),
            ("fd_limit = 2048", "fd_limit = 1"),
            ("cpu_limit_percent = 90.0", "cpu_limit_percent = 150.0"),
            ("required_route = \"DIRECT\"", "required_route = \"TOR\""),
            ("outbox_capacity = 32", "outbox_capacity = 0"),
            ("policy_version = 1", "policy_version = 0"),
        )
        for old, new in bad:
            with self.assertRaises(c.ConfigError, msg=new):
                c.load_config_text(swap(old, new))
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap("enabled = false\n", 'enabled = true\n'))  # needs token ref + chat ids
        cfg = c.load_config_text(swap("enabled = false\n", 'enabled = true\nbot_token_ref = "ref:vault:tg"\n').replace("chat_ids = []", "chat_ids = [42]"))
        self.assertEqual(cfg.telegram.chat_ids, (42,))
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap("enabled = false # ai", "enabled = true # ai"))  # needs api_key_ref
        cfg = c.load_config_text(swap("enabled = false # ai", 'enabled = true\napi_key_ref = "ref:env:OSRS_EE_AI_KEY" # ai'))
        self.assertTrue(cfg.ai.enabled)
        for old, new in (("max_calls = 20", "max_calls = -1"), ("max_bytes = 200000", "max_bytes = -5")):
            with self.assertRaises(c.ConfigError, msg=new):
                c.load_config_text(swap(old, new))
        with self.assertRaises(c.ConfigError):
            c.load_config_text(swap("# base_url = \"https://api.openai.com\"", 'base_url = "http://evil.example.com"'))

    def test_invalid_toml_and_missing_file(self):
        with self.assertRaises(c.ConfigError):
            c.load_config_text("x = [")
        with self.assertRaises(c.ConfigError):
            c.load_config("/nonexistent/osrs_ee/config.toml")


if __name__ == "__main__":
    unittest.main()
