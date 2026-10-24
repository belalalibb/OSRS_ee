"""S06b-local — real HTTP transport + poller against a scripted loopback server.

Proves wire behaviour (status mapping, retry_after, token handling, strict update
parsing) on 127.0.0.1 only. Does NOT prove anything about api.telegram.org or a
real bot/chat (T02/T03 on a live chat remain NOT_RUN).
"""
from __future__ import annotations

import json
import unittest

from osrs_ee.telegram import AccessPolicy, ControlPlane, FakeTransport, Outbox, OutboundMessage, Redactor, SendResult
from osrs_ee.transports import (PollResult, TelegramHttpTransport, TelegramPoller, TransportConfig, TransportError,
                                resolve_secret_ref)
from osrs_ee.transports.telegram_poll import parse_update
from tests.fake_http import FakeHttpServer
from tests.test_store import T0

TOKEN = "123456789:FAKE_TOKEN_abcdefghijklmnopqrstuvwxyz0123"
ENV = {"TG_BOT_TOKEN": TOKEN}
LOOPBACK = frozenset({"127.0.0.1"})


def transport(server, redactor=None, **cfg):
    red = redactor or Redactor()
    return TelegramHttpTransport("ref:env:TG_BOT_TOKEN", red, TransportConfig(base_url=server.base_url, allowed_hosts=LOOPBACK,
                                                                               timeout_seconds=2.0, **cfg), env=ENV), red


class SecretRefs(unittest.TestCase):
    def test_only_env_refs_are_accepted_and_value_must_exist(self):
        self.assertEqual(resolve_secret_ref("ref:env:TG_BOT_TOKEN", env=ENV), TOKEN)
        for bad in (TOKEN, "ref:vault:x", "ref:env:", "ref:env:bad-name", None):
            with self.assertRaises(TransportError, msg=str(bad)):
                resolve_secret_ref(bad, env=ENV)
        with self.assertRaises(TransportError):
            resolve_secret_ref("ref:env:MISSING", env=ENV)
        with self.assertRaises(TransportError):
            resolve_secret_ref("ref:env:SHORT", env={"SHORT": "abc"})

    def test_config_refuses_unlisted_hosts_and_plain_http_offsite(self):
        TransportConfig()  # default api.telegram.org is allowed
        with self.assertRaises(TransportError):
            TransportConfig(base_url="https://evil.example.com")
        with self.assertRaises(TransportError):
            TransportConfig(base_url="http://api.telegram.org", allowed_hosts=frozenset({"api.telegram.org"}))
        with self.assertRaises(TransportError):
            TransportConfig(timeout_seconds=0)
        TransportConfig(base_url="http://127.0.0.1:1", allowed_hosts=LOOPBACK)

    def test_token_becomes_canary_and_never_renders(self):
        red = Redactor()
        with FakeHttpServer() as srv:
            transport(srv, red)
        self.assertIn(TOKEN, red.canaries)
        self.assertIsNotNone(red.scan(f"token leaked: {TOKEN}"))
        ob = Outbox(FakeTransport(), red)
        self.assertFalse(ob.enqueue(OutboundMessage(1, f"debug {TOKEN}")).allowed)


class SendMapping(unittest.TestCase):
    def test_200_ok_sends_with_token_in_path_and_json_body(self):
        with FakeHttpServer() as srv:
            t, _ = transport(srv)
            r = t.send(OutboundMessage(42, "state: RESTING", "STATE"), now=T0)
            self.assertEqual(r, SendResult(True))
            req = srv.requests[0]
            self.assertEqual(req["path"], f"/bot{TOKEN}/sendMessage")
            self.assertEqual(req["body"]["chat_id"], 42)
            self.assertEqual(req["body"]["text"], "state: RESTING")
            self.assertEqual(req["headers"]["Content-Type"], "application/json")

    def test_429_honours_retry_after_5xx_transient_4xx_permanent(self):
        with FakeHttpServer() as srv:
            srv.plan((429, {"ok": False, "parameters": {"retry_after": 7}}),
                     (503, {"ok": False, "description": "bad gateway"}),
                     (400, {"ok": False, "description": "chat not found"}),
                     (200, {"ok": False, "description": "weird"}),
                     (200, b"not json"))
            t, _ = transport(srv)
            m = OutboundMessage(1, "hi")
            self.assertEqual(t.send(m, now=T0), SendResult(False, retry_after_seconds=7))
            self.assertEqual(t.send(m, now=T0), SendResult(False))
            self.assertIn("http 503", t.last_error)
            self.assertEqual(t.send(m, now=T0), SendResult(False, permanent=True))
            self.assertIn("chat not found", t.last_error)
            self.assertEqual(t.send(m, now=T0), SendResult(False, permanent=True))
            self.assertEqual(t.send(m, now=T0), SendResult(False, permanent=True))
            self.assertEqual(t.requests, 5)

    def test_unsafe_text_is_refused_before_any_request(self):
        with FakeHttpServer() as srv:
            t, red = transport(srv)
            red.register_canary("CANARY-XYZ-123")
            r = t.send(OutboundMessage(1, "leak CANARY-XYZ-123"), now=T0)
            self.assertEqual(r, SendResult(False, permanent=True))
            self.assertEqual(srv.requests, [])
            self.assertEqual(t.requests, 0)

    def test_server_error_text_never_echoes_token(self):
        with FakeHttpServer() as srv:
            srv.plan((500, {"ok": False, "description": f"internal {TOKEN} oops"}))
            t, _ = transport(srv)
            t.send(OutboundMessage(1, "x"), now=T0)
            self.assertNotIn(TOKEN, t.last_error)
            self.assertIn("<token>", t.last_error)

    def test_connection_refused_is_transient_not_exception(self):
        with FakeHttpServer() as srv:
            t, _ = transport(srv)
            dead = TelegramHttpTransport("ref:env:TG_BOT_TOKEN", Redactor(),
                                         TransportConfig(base_url="http://127.0.0.1:9", allowed_hosts=LOOPBACK, timeout_seconds=1.0), env=ENV)
            self.assertEqual(dead.send(OutboundMessage(1, "x"), now=T0), SendResult(False))
            self.assertTrue(dead.last_error.startswith("network:"))

    def test_outbox_end_to_end_with_real_transport_retries_then_delivers(self):
        with FakeHttpServer() as srv:
            srv.plan((429, {"ok": False, "parameters": {"retry_after": 3}}))
            t, red = transport(srv)
            ob = Outbox(t, red)
            ob.enqueue(OutboundMessage(5, "stop requested", "STOP"))
            self.assertEqual(ob.flush(now=T0), 0)
            self.assertEqual(ob.flush(now=T0), 0)  # backing off, no request made
            self.assertEqual(len(srv.requests), 1)
            from datetime import timedelta
            self.assertEqual(ob.flush(now=T0 + timedelta(seconds=5)), 1)
            self.assertEqual(len(srv.requests), 2)
            self.assertEqual(len(ob), 0)


def upd(update_id, **kw):
    return {"update_id": update_id, **kw}


def text_update(uid, chat, user, text, mid=1):
    return upd(uid, message={"message_id": mid, "chat": {"id": chat}, "from": {"id": user}, "text": text})


def cb_update(uid, chat, user, data, cb_id="cb1"):
    return upd(uid, callback_query={"id": cb_id, "from": {"id": user}, "data": data, "message": {"chat": {"id": chat}}})


CB = json.dumps({"a": "apr_1", "i": "inc_1", "acc": "acc_demo001", "e": 1, "p": "p" * 64, "v": 4})


class Parsing(unittest.TestCase):
    def test_message_and_bound_callback_parse(self):
        m, c = parse_update(text_update(1, 10, 20, "/stop", 7))
        self.assertEqual((m.chat_id, m.user_id, m.text, m.message_id), (10, 20, "/stop", 7))
        self.assertIsNone(c)
        m, c = parse_update(cb_update(2, 10, 20, CB))
        self.assertIsNone(m)
        self.assertEqual((c.chat_id, c.user_id, c.callback_id, c.approval_id, c.session_epoch, c.state_version),
                         (10, 20, "cb1", "apr_1", 1, 4))

    def test_malformed_updates_are_dropped_not_raised(self):
        bad = [
            {},  # no update_id
            upd(1, message={"chat": {"id": 1}, "text": "x"}),            # no from / message_id
            upd(2, message={"message_id": 1, "chat": {"id": "1"}, "from": {"id": 2}, "text": "x"}),  # chat id str
            upd(3, message={"message_id": 1, "chat": {"id": 1}, "from": {"id": 2, "is_bot": True}, "text": "x"}),
            upd(4, message={"message_id": 1, "chat": {"id": 1}, "from": {"id": 2}, "text": 5}),
            cb_update(5, 1, 2, "not json"),
            cb_update(6, 1, 2, json.dumps({"a": "x"})),                       # missing keys
            cb_update(7, 1, 2, json.dumps({"a": "x", "i": "y", "acc": "z", "e": "1", "p": "q", "v": 1})),  # epoch str
            cb_update(8, 1, 2, json.dumps({"a": "", "i": "y", "acc": "z", "e": 1, "p": "q", "v": 1})),     # empty id
            upd(9, edited_message={"x": 1}),
            "garbage",
        ]
        for b in bad:
            self.assertEqual(parse_update(b), (None, None), msg=str(b)[:60])

    def test_long_text_is_truncated(self):
        m, _ = parse_update(text_update(1, 1, 2, "x" * 5000))
        self.assertEqual(len(m.text), 512)


class Polling(unittest.TestCase):
    def test_poll_advances_offset_and_routes_through_control_plane_default_deny(self):
        with FakeHttpServer() as srv:
            srv.plan((200, {"ok": True, "result": [text_update(100, 10, 20, "/status"),
                                                   text_update(101, 10, 99, "/stop"),      # unknown user
                                                   cb_update(102, 10, 20, CB),
                                                   {"update_id": 103, "poll": "unsupported"}]}),
                     (200, {"ok": True, "result": []}))
            t, red = transport(srv)
            poller = TelegramPoller(t)
            res = poller.poll(now=T0)
            self.assertEqual((len(res.messages), len(res.callbacks), res.dropped, res.next_offset), (2, 1, 1, 104))
            self.assertEqual(poller.offset, 104)
            res2 = poller.poll(now=T0)
            self.assertEqual(srv.requests[1]["body"]["offset"], 104)
            self.assertEqual(srv.requests[1]["path"], f"/bot{TOKEN}/getUpdates")
            self.assertEqual((res2.messages, res2.callbacks, res2.next_offset), ([], [], None))
            # control plane: user 20 is VIEWER in chat 10; /status ok, /stop by 99 denied, callback by VIEWER denied
            policy = AccessPolicy(chat_ids=frozenset({10}), users={20: "VIEWER"})
            cp = ControlPlane(_store_stub(), policy, Outbox(FakeTransport(), red), red, approver_refs={})
            outcomes = [cp.handle_message(m, now=T0).action for m in res.messages]
            self.assertEqual(outcomes, ["STATUS", "DENIED"])
            self.assertEqual(cp.handle_callback(res.callbacks[0], now=T0).action, "DENIED")

    def test_poll_error_statuses_leave_offset_untouched(self):
        with FakeHttpServer() as srv:
            srv.plan((502, {"ok": False}), (200, {"ok": False}), (200, {"ok": True, "result": "nope"}))
            t, _ = transport(srv)
            poller = TelegramPoller(t)
            for _ in range(3):
                res = poller.poll(now=T0)
                self.assertEqual((res.messages, res.callbacks, res.next_offset), ([], [], None))
            self.assertIsNone(poller.offset)
            with self.assertRaises(ValueError):
                TelegramPoller(t, poll_timeout_seconds=99)


def _store_stub():
    class _S:
        def get_approval(self, _id):
            return None
    return _S()


if __name__ == "__main__":
    unittest.main()
