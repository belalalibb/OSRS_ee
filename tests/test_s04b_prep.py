"""S04b-prep — read-only loopback adapter, /proc measurement, egress policy.

Everything runs against 127.0.0.1 (tests/fake_http) or the test process itself.
This proves the *mechanics* (bounded GET, strict parsing, contract + honesty
checks, never-dispatch, allowlist enforcement before connect). It proves nothing
about a game client, a JVM or the owner's machine: T06/T10/T30/T31/T33 remain
NOT_RUN (docs/OUT_OF_SANDBOX.md).
"""
from __future__ import annotations

import os
import unittest
import urllib.error
import urllib.request
from datetime import timedelta

from osrs_ee import measure as ms
from osrs_ee import store as st
from osrs_ee import worker as wk
from osrs_ee.adapters import (AdapterFailure, EndpointError, LoopbackConfig, LoopbackReadOnlyAdapter, NEVER_DISPATCH,
                              run_conformance)
from osrs_ee.egress import EgressDenied, EgressPolicy, guarded_opener
from osrs_ee.release import ResourceSnapshot
from osrs_ee.telegram import OutboundMessage, Redactor
from osrs_ee.transports import TelegramHttpTransport, TransportConfig
from tests.conftest import loopback_only
from tests.fake_http import FakeHttpServer
from tests.test_store import ACC, T0, StoreCase, fixture


def obs(**over):
    o = fixture("Observation", "basic")
    o["session_epoch"], o["state_version"] = 1, 6
    o.update(over)
    return o


def closed_bank_obs(items_quality="UNKNOWN", items_value=None):
    o = obs()
    o["fields"]["bank.open"]["value"] = False
    o["fields"]["bank.items"].update({"quality": items_quality, "value": items_value})
    return o


def adapter(srv, **cfg):
    return LoopbackReadOnlyAdapter(LoopbackConfig(endpoint=srv.base_url + "/agent", timeout_seconds=1.0, **cfg))


class Endpoint(unittest.TestCase):
    def test_only_loopback_http_endpoints_are_accepted(self):
        for ok in ("http://127.0.0.1:8099", "http://localhost:8099/agent", "http://[::1]:8099/a/b"):
            LoopbackConfig(endpoint=ok)
        for bad in ("https://127.0.0.1:8099", "http://10.0.0.5:8099", "http://127.0.0.1", "http://example.com:80",
                    "http://127.0.0.1:8099/x?y=1", ""):
            with self.assertRaises(EndpointError, msg=bad):
                LoopbackConfig(endpoint=bad)

    def test_bounds_are_enforced(self):
        with self.assertRaises(EndpointError):
            LoopbackConfig(endpoint="http://127.0.0.1:8099", timeout_seconds=0)
        with self.assertRaises(EndpointError):
            LoopbackConfig(endpoint="http://127.0.0.1:8099", max_response_bytes=100)


class Observe(unittest.TestCase):
    def test_valid_observation_is_returned_from_observe_path(self):
        with FakeHttpServer(default=(200, obs())) as srv:
            a = adapter(srv)
            doc = a.observe(T0)
        self.assertEqual(doc["state_version"], 6)
        self.assertEqual(srv.requests[0]["path"], "/agent/observe")
        self.assertEqual((a.observe_calls, a.last_error), (1, None))

    def test_contract_violation_http_error_and_bad_json_are_adapter_failures(self):
        bad_contract = obs()
        del bad_contract["fields"]
        with FakeHttpServer().plan((200, bad_contract), (500, {"ok": False}), (200, b"not json"),
                                   (200, b'{"a":1,"a":2}')) as srv:
            a = adapter(srv)
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
            self.assertTrue((a.last_error or "").startswith("contract"), a.last_error)
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
            self.assertEqual(a.last_error, "http 500")
            for _ in range(2):
                with self.assertRaises(AdapterFailure):
                    a.observe(T0)
                self.assertTrue((a.last_error or "").startswith("unparseable"), a.last_error)
        self.assertEqual(a.observe_calls, 4)

    def test_dead_endpoint_is_a_network_failure(self):
        with loopback_only():
            import socket
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()  # nothing listens on `port` now
            a = LoopbackReadOnlyAdapter(LoopbackConfig(endpoint=f"http://127.0.0.1:{port}/agent", timeout_seconds=0.5))
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
        self.assertTrue((a.last_error or "").startswith("network"), a.last_error)

    def test_honesty_rules(self):
        future = obs(observed_at="2026-10-23T19:10:00Z")
        field_newer = obs()
        field_newer["fields"]["client.logged_in"]["observed_at"] = "2026-10-23T19:00:01Z"
        with FakeHttpServer().plan((200, closed_bank_obs()), (200, closed_bank_obs("KNOWN", [])),
                                   (200, future), (200, field_newer),
                                   (200, obs(state_version=9)), (200, obs(state_version=8))) as srv:
            a = adapter(srv)
            a.observe(T0)  # closed bank with UNKNOWN items: honest
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
            self.assertIn("bank.items", a.last_error or "")
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
            self.assertIn("future", a.last_error or "")
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
            self.assertIn("newer", a.last_error or "")
            self.assertEqual(a.observe(T0)["state_version"], 9)
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
            self.assertIn("decreased", a.last_error or "")

    def test_oversized_response_is_refused(self):
        big = obs()
        big["fields"]["player.position"] = {"quality": "KNOWN", "source": "x", "observed_at": "2026-10-23T19:00:00Z",
                                            "value": ["a" * 1000] * 10}
        with FakeHttpServer(default=(200, big)) as srv:
            a = adapter(srv, max_response_bytes=4096)
            with self.assertRaises(AdapterFailure):
                a.observe(T0)
        self.assertEqual(a.last_error, "response too large")


class NeverDispatch(StoreCase):
    def test_dispatch_is_refused_without_any_request(self):
        with FakeHttpServer(default=(200, obs())) as srv:
            a = adapter(srv)
            r = a.dispatch(fixture("CommandIntent", "bank_withdraw"), deadline=T0 + timedelta(seconds=5), now=T0)
        self.assertIs(r, NEVER_DISPATCH)
        self.assertEqual((r.transport_status, r.effect_status, r.reason_code), ("NOT_SENT", "NOT_ATTEMPTED", "POLICY_DENIED"))
        self.assertEqual((a.dispatch_refusals, srv.requests), (1, []))

    def test_passes_conformance_with_loopback_allowlisted(self):
        with FakeHttpServer(default=(200, obs())) as srv:
            a = adapter(srv)
            report = run_conformance(a, now=T0, allowed_hosts=frozenset({"127.0.0.1"}))
        self.assertTrue(report.passed, [f for f in report.findings if not f.passed])
        self.assertEqual(len(srv.requests), 2)

    def test_worker_journal_never_shows_dispatching_or_acknowledged(self):
        cfg = wk.WorkerConfig(config_hash="c" * 64, policy_version=1, observation_max_age_seconds=10,
                              dispatch_timeout_seconds=30, max_queue=3)
        self.lease()
        with FakeHttpServer(default=(200, obs())) as srv:
            a = adapter(srv)
            w = wk.Worker(self.s, a, ACC, cfg)
            w.start(now=T0)
            intent = fixture("CommandIntent", "bank_withdraw")
            intent["session_epoch"], intent["expected_state_version"], intent["config_hash"] = 1, 6, "c" * 64
            self.assertTrue(w.enqueue(intent).allowed)
            step = w.step(now=T0 + timedelta(seconds=1))
        self.assertEqual(step.phase, "NOT_SENT")
        self.assertEqual(a.dispatch_refusals, 1)
        self.assertEqual(self.s.commands_in_phase(ACC, ("DISPATCHING", "ACKNOWLEDGED", "UNKNOWN")), [])


@unittest.skipUnless(ms.proc_available(), "/proc not available: measurement is target-only here")
class Measurement(unittest.TestCase):
    def test_first_measure_is_none_then_a_real_snapshot(self):
        pid, sampler = os.getpid(), ms.CpuSampler(os.getpid())
        self.assertIsNone(ms.measure(pid, ".", T0, cpu=sampler))
        snap = ms.measure(pid, ".", T0 + timedelta(seconds=1), cpu=sampler)
        self.assertIsInstance(snap, ResourceSnapshot)
        self.assertGreater(snap.rss_bytes, 0)
        self.assertGreater(snap.open_fds, 0)
        self.assertGreater(snap.disk_free_bytes, 0)
        self.assertGreaterEqual(snap.cpu_percent, 0.0)
        d = ms.measure_dict(pid, ".", T0 + timedelta(seconds=2), cpu=sampler)
        self.assertEqual(set(d), {"rss_bytes", "disk_free_bytes", "open_fds", "cpu_percent"})

    def test_missing_pid_or_dir_yields_none_not_a_guess(self):
        self.assertIsNone(ms.rss_bytes(2_000_000_000))
        self.assertIsNone(ms.open_fds(2_000_000_000))
        self.assertIsNone(ms.disk_free_bytes("/definitely/not/here"))
        sampler = ms.CpuSampler(os.getpid())
        sampler.sample(T0)
        self.assertIsNone(ms.measure(os.getpid(), "/definitely/not/here", T0 + timedelta(seconds=1), cpu=sampler))


class Egress(unittest.TestCase):
    def test_allowlist_parsing_and_decisions(self):
        p = EgressPolicy.from_allowlist(["api.telegram.org:443:telegram", "API.openai.com:443"])
        self.assertTrue(p.decide("api.telegram.org", 443, now=T0).allowed)
        self.assertTrue(p.decide("api.openai.com", 443, now=T0).allowed)
        self.assertFalse(p.decide("api.telegram.org", 80, now=T0).allowed)
        self.assertFalse(p.decide("evil.example.com", 443, now=T0).allowed)
        self.assertTrue(p.decide("127.0.0.1", 5, now=T0).allowed)
        self.assertEqual(len(p.denied()), 2)
        self.assertEqual(p.inventory[0], ("2026-10-23T19:00:00Z", "api.telegram.org", 443, True, "telegram"))
        for bad in ("nohost", "host:abc", "host:0", "host:70000", "*.example.com:443", ":443"):
            with self.assertRaises(ValueError, msg=bad):
                EgressPolicy.from_allowlist([bad])

    def test_guarded_opener_allows_loopback_and_blocks_when_disabled(self):
        with FakeHttpServer(default=(200, {"ok": True})) as srv:
            allowed = guarded_opener(EgressPolicy())
            with allowed.open(srv.base_url + "/x", timeout=1.0) as r:
                self.assertEqual(r.status, 200)
            blocked_policy = EgressPolicy(allow_loopback=False)
            blocked = guarded_opener(blocked_policy)
            with self.assertRaises((EgressDenied, urllib.error.URLError)):
                blocked.open(srv.base_url + "/y", timeout=1.0)
            self.assertEqual(len(srv.requests), 1)
            self.assertEqual(len(blocked_policy.denied()), 1)

    def test_transport_with_guarded_opener_fails_closed_without_sending(self):
        policy = EgressPolicy(allow_loopback=False)
        red = Redactor()
        with FakeHttpServer() as srv:
            t = TelegramHttpTransport("ref:env:TG_BOT_TOKEN", red,
                                      TransportConfig(base_url=srv.base_url, allowed_hosts=frozenset({"127.0.0.1"}),
                                                      timeout_seconds=1.0),
                                      env={"TG_BOT_TOKEN": "123456789:FAKE_TOKEN_abcdefghijklmnopqrstuvwxyz0123"},
                                      opener=guarded_opener(policy))
            res = t.send(OutboundMessage(chat_id=10, text="hello"), now=T0)
            self.assertFalse(res.ok)
            self.assertEqual(srv.requests, [])
        self.assertTrue((t.last_error or "").startswith("network:"), t.last_error)
        self.assertEqual(len(policy.denied()), 1)
