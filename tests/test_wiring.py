"""WIRE-01 — component factory from config. Fake components by default; REAL ones
only with explicit flags and ``ref:env`` secrets present; all network against a
loopback fake server. Nothing here talks to api.telegram.org or any AI provider
(T02/T03/T35 live tests remain NOT_RUN)."""
from __future__ import annotations

import unittest
from datetime import timedelta

from osrs_ee import config as c
from osrs_ee import wiring as w
from osrs_ee.advisor import FakeProvider
from osrs_ee.telegram import FakeTransport, OutboundMessage
from tests.fake_http import FakeHttpServer
from tests.test_store import T0

TOKEN = "123456789:FAKE_TOKEN_abcdefghijklmnopqrstuvwxyz0123"  # secret-scan: allow (synthetic canary)
KEY = "sk-FAKE-KEY-0123456789abcdefghijklmnopqrstuvwxyz"  # secret-scan: allow (synthetic canary)


def cfg(**over) -> c.ServiceConfig:
    text = c.example_toml()
    for old, new in over.items():
        assert old in text, old
        text = text.replace(old, new)
    return c.load_config_text(text)


def _host(url):
    return url.split("://")[1].split(":")[0].split("/")[0]


def tg_cfg(base_url, allow="127.0.0.1:443:telegram"):
    return cfg(**{"enabled = false\n": f'enabled = true\nbot_token_ref = "ref:env:TG_TOKEN"\nbase_url = "{base_url}"\nallowed_hosts = ["{_host(base_url)}"]\n',
                  "chat_ids = []": "chat_ids = [10]\napprover_user_ids = [20]",
                  "egress_allowlist = []": f'egress_allowlist = ["{allow}"]'})


def ai_cfg(base_url):
    return cfg(**{"enabled = false # ai": f'enabled = true\napi_key_ref = "ref:env:AI_KEY"\nbase_url = "{base_url}"\nallowed_hosts = ["{_host(base_url)}"] # ai'})


class Defaults(unittest.TestCase):
    def test_example_config_wires_fakes_only_and_reports_it(self):
        wd = w.build(cfg(), env={})
        self.assertIsInstance(wd.transport.obj, FakeTransport)
        self.assertIsInstance(wd.provider.obj, FakeProvider)
        self.assertFalse(wd.any_real)
        modes = {r["component"]: r["mode"] for r in wd.report()}
        self.assertEqual(modes, {"telegram.transport": "FAKE", "telegram.poller": "DISABLED", "ai.provider": "FAKE",
                                 "ai.advisor": "FAKE", "network.egress": "LOOPBACK_ONLY"})
        self.assertIsNone(wd.access)
        wd.outbox.enqueue(OutboundMessage(1, "hello"))
        wd.outbox.flush(now=T0)
        self.assertEqual(len(wd.transport.obj.sent), 1)


class RealGating(unittest.TestCase):
    def test_real_telegram_requires_flag_env_and_secret(self):
        conf = tg_cfg("https://api.telegram.org", allow="api.telegram.org:443:telegram")
        with self.assertRaises(w.WiringError) as e:
            w.build(conf, env={"TG_TOKEN": TOKEN})  # no flag
        self.assertIn("--allow-real-network", str(e.exception))
        with self.assertRaises(w.WiringError):
            w.build(conf, env={"TG_TOKEN": TOKEN}, allow_real_network=True)  # env var missing
        with self.assertRaises(w.WiringError) as e:
            w.build(conf, env={w.ALLOW_NETWORK_ENV: "1"}, allow_real_network=True)  # secret missing
        self.assertIn("telegram", str(e.exception))
        self.assertNotIn(TOKEN, str(e.exception))

    def test_real_component_needs_its_host_in_egress_allowlist(self):
        conf = tg_cfg("https://api.telegram.org", allow="api.openai.com:443:ai")
        with self.assertRaises(w.WiringError) as e:
            w.build(conf, env={"TG_TOKEN": TOKEN, w.ALLOW_NETWORK_ENV: "1"}, allow_real_network=True)
        self.assertIn('"api.telegram.org:443:telegram"', str(e.exception))

    def test_config_with_a_real_host_can_be_built_without_any_socket(self):
        conf = tg_cfg("https://api.telegram.org", allow="api.telegram.org:443:telegram")
        wd = w.build(conf, env={"TG_TOKEN": TOKEN, w.ALLOW_NETWORK_ENV: "1"}, allow_real_network=True)
        self.assertEqual(wd.transport.mode, "REAL")
        self.assertTrue(wd.any_real)
        self.assertEqual(wd.egress.inventory, [])  # building is not an egress event
        self.assertIn(TOKEN, wd.redactor.canaries)   # token registered as canary, never printed
        self.assertNotIn(TOKEN, str(wd.report()))
        self.assertEqual(wd.access.role_of(10, 20), "OPERATOR")
        self.assertIsNone(wd.access.role_of(11, 20))


class LoopbackReal(unittest.TestCase):
    """REAL implementations against the fake server: loopback needs no flag."""

    def test_telegram_real_transport_sends_through_guarded_opener(self):
        with FakeHttpServer() as srv:
            wd = w.build(tg_cfg(srv.base_url), env={"TG_TOKEN": TOKEN})
            self.assertEqual(wd.transport.mode, "REAL")
            wd.outbox.enqueue(OutboundMessage(10, "state: RESTING"))
            wd.outbox.flush(now=T0)
            self.assertEqual(len(srv.requests), 1)
            self.assertIn("sendMessage", srv.requests[0]["path"])
            self.assertNotIn(TOKEN, str(wd.egress.inventory))
            self.assertTrue(wd.egress.inventory and wd.egress.inventory[0][3])  # loopback allowed, inventoried
            res = wd.poller.obj.poll(now=T0)
            self.assertEqual(len(srv.requests), 2)
            self.assertIsNotNone(res)

    def test_ai_real_provider_against_fake_server_is_advisory_only(self):
        reply = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "not json at all"}}]}
        with FakeHttpServer(default=(200, reply)) as srv:
            wd = w.build(ai_cfg(srv.base_url), env={"AI_KEY": KEY})
            self.assertEqual((wd.provider.mode, wd.advisor.mode), ("REAL", "REAL"))
            text = wd.provider.obj.complete(b"{}", deadline=T0 + timedelta(seconds=5), now=T0)
            self.assertEqual(text, "not json at all")
            self.assertEqual(len(srv.requests), 1)
            self.assertNotIn(KEY, str(srv.requests[0]["body"]))
            self.assertIn(KEY, wd.redactor.canaries)

    def test_egress_denied_host_is_blocked_before_connect(self):
        conf = cfg(**{"egress_allowlist = []": 'egress_allowlist = ["api.telegram.org:443:telegram"]'})
        wd = w.build(conf, env={})
        self.assertFalse(wd.egress.decide("api.openai.com", 443, now=T0).allowed)
        self.assertTrue(wd.egress.decide("api.telegram.org", 443, now=T0).allowed)
        self.assertEqual(len(wd.egress.denied()), 1)
