"""S06 Telegram control plane tests — fake transport, no network.
Pure/local parts of T02 (no secrets in sinks), T03 (RBAC + bound single-use approvals),
T29 (bounded, deduped, prioritized outbox with bounded retries)."""
from __future__ import annotations

import unittest
from datetime import timedelta

from osrs_ee import telegram as tg
from tests.test_store import ACC, T0, StoreCase

CHAT, OWNER, OPERATOR, VIEWER, STRANGER = 1001, 11, 22, 33, 99
POLICY = tg.AccessPolicy(frozenset({CHAT}), {OWNER: "OWNER", OPERATOR: "OPERATOR", VIEWER: "VIEWER"})
CANARY = "CANARY-7f3a9c2e-SECRET"
PLAN = "d" * 64


def redactor():
    r = tg.Redactor(aliases={ACC: "alias:demo"})
    r.register_canary(CANARY)
    return r


class RBAC(unittest.TestCase):
    def test_default_deny_outside_allowlists(self):
        self.assertFalse(POLICY.authorize(CHAT, STRANGER, "/status").allowed)
        self.assertFalse(POLICY.authorize(2002, OWNER, "/status").allowed)  # right user, wrong chat
        self.assertEqual(POLICY.authorize(CHAT, STRANGER, "/status").reason_code, "IDENTITY_UNVERIFIED")

    def test_role_matrix(self):
        self.assertTrue(POLICY.authorize(CHAT, VIEWER, "/status").allowed)
        self.assertFalse(POLICY.authorize(CHAT, VIEWER, "/stop").allowed)
        self.assertTrue(POLICY.authorize(CHAT, OPERATOR, "/stop").allowed)
        self.assertFalse(POLICY.authorize(CHAT, OPERATOR, "/approve").allowed)
        self.assertTrue(POLICY.authorize(CHAT, OWNER, "/approve").allowed)

    def test_unknown_command_denied_even_for_owner(self):
        d = POLICY.authorize(CHAT, OWNER, "/eval")
        self.assertEqual((d.allowed, d.reason_code), (False, "POLICY_DENIED"))

    def test_unknown_role_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            tg.AccessPolicy(frozenset({CHAT}), {OWNER: "ROOT"})


class Redaction(unittest.TestCase):
    def test_canary_never_renders(self):
        r = redactor()
        with self.assertRaises(tg.RedactionError):
            r.render("status: {x}", x=CANARY)

    def test_secret_shapes_rejected(self):
        r = redactor()
        for bad in ("token ghp_" + "A" * 36, "bot 123456789:" + "x" * 35, "password: hunter2222"):  # secret-scan: allow (synthetic canary)
            self.assertIsNotNone(r.scan(bad), bad)

    def test_account_id_replaced_by_alias(self):
        self.assertEqual(redactor().render("{a} READY", a=ACC), "alias:demo READY")

    def test_short_canary_refused(self):
        with self.assertRaises(ValueError):
            tg.Redactor().register_canary("abc")


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.t = tg.FakeTransport()
        self.o = tg.Outbox(self.t, redactor(), capacity=3, max_attempts=2)

    def msg(self, text, kind="INFO", key=None):
        return tg.OutboundMessage(CHAT, text, kind, key)

    def test_dedupe_and_priority_order(self):
        self.o.enqueue(self.msg("info 1"))
        self.o.enqueue(self.msg("stopping", "STOP"))
        self.assertFalse(self.o.enqueue(self.msg("info 1")).allowed)
        self.assertEqual([m.kind for m in self.o.pending()], ["STOP", "INFO"])
        self.assertEqual(self.o.flush(now=T0), 2)
        self.assertEqual([m.kind for m in self.t.sent], ["STOP", "INFO"])

    def test_full_outbox_drops_low_priority_not_state(self):
        for i in range(3):
            self.o.enqueue(self.msg(f"info {i}"))
        self.assertFalse(self.o.enqueue(self.msg("info 9")).allowed)       # equal priority -> new one dropped
        self.assertTrue(self.o.enqueue(self.msg("state", "STATE")).allowed)  # evicts newest INFO
        self.assertEqual(len(self.o), 3)
        self.assertEqual(self.o.pending()[0].kind, "STATE")
        self.assertEqual([m.text for m in self.o.dropped], ["info 9", "info 2"])

    def test_redaction_blocks_enqueue(self):
        d = self.o.enqueue(self.msg(f"leak {CANARY}"))
        self.assertEqual((d.allowed, d.reason_code), (False, "POLICY_DENIED"))
        self.assertEqual(len(self.o), 0)

    def test_retry_after_honoured_and_bounded(self):
        self.t.plan(tg.SendResult(False, retry_after_seconds=30), tg.SendResult(False))
        self.o.enqueue(self.msg("alert", "ALERT"))
        self.assertEqual(self.o.flush(now=T0), 0)
        self.assertEqual(self.o.flush(now=T0 + timedelta(seconds=10)), 0)   # still backing off: no attempt
        self.assertEqual(self.t.attempts, 1)
        self.assertEqual(self.o.flush(now=T0 + timedelta(seconds=31)), 0)   # 2nd attempt fails -> dead (max 2)
        self.assertEqual(len(self.o), 0)
        self.assertEqual([m.text for m in self.o.dead], ["alert"])
        self.assertEqual(self.t.attempts, 2)

    def test_permanent_failure_goes_dead_immediately(self):
        self.t.plan(tg.SendResult(False, permanent=True))
        self.o.enqueue(self.msg("x"))
        self.o.flush(now=T0)
        self.assertEqual(len(self.o.dead), 1)
        self.assertEqual(self.t.attempts, 1)

    def test_flush_budget_limits_sends(self):
        for i in range(3):
            self.o.enqueue(self.msg(f"m{i}"))
        self.assertEqual(self.o.flush(now=T0, budget=2), 2)
        self.assertEqual(len(self.o), 1)


class ControlPlaneTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.lease()
        self.t = tg.FakeTransport()
        self.r = redactor()
        self.o = tg.Outbox(self.t, self.r)
        self.stops = []
        self.cp = tg.ControlPlane(self.s, POLICY, self.o, self.r, approver_refs={OWNER: "ref:tg:owner"},
                                  on_stop=lambda now: self.stops.append(now))
        self.s.create_approval(approval_id="apr_demo001", incident_id="inc_demo001", account_id=ACC, session_epoch=1,
                               plan_hash=PLAN, state_version=4, approver_ref="ref:tg:owner",
                               expires_at=T0 + timedelta(minutes=5), now=T0)

    def cb(self, **over):
        kw = dict(chat_id=CHAT, user_id=OWNER, callback_id="cbk_demo001", approval_id="apr_demo001", incident_id="inc_demo001",
                  account_id=ACC, session_epoch=1, plan_hash=PLAN, state_version=4)
        kw.update(over)
        return tg.InboundCallback(**kw)

    def test_stop_by_operator_delegates_and_notifies(self):
        h = self.cp.handle_message(tg.InboundMessage(CHAT, OPERATOR, "/stop", 1), now=T0)
        self.assertEqual((h.accepted, h.action), (True, "STOP"))
        self.assertEqual(self.stops, [T0])
        self.assertEqual(self.o.pending()[0].kind, "STOP")

    def test_viewer_stop_denied_and_audited(self):
        h = self.cp.handle_message(tg.InboundMessage(CHAT, VIEWER, "/stop", 2), now=T0)
        self.assertEqual((h.accepted, h.reason_code), (False, "POLICY_DENIED"))
        self.assertEqual(self.stops, [])
        self.assertEqual(self.cp.audit[-1][3], "DENIED")

    def test_text_approve_refused_even_for_owner(self):
        h = self.cp.handle_message(tg.InboundMessage(CHAT, OWNER, "/approve apr_demo001", 3), now=T0)
        self.assertFalse(h.accepted)
        self.assertIsNone(self.s.get_approval("apr_demo001").used_at)

    def test_bound_callback_consumes_once(self):
        self.assertTrue(self.cp.handle_callback(self.cb(), now=T0).accepted)
        self.assertIsNotNone(self.s.get_approval("apr_demo001").used_at)
        h = self.cp.handle_callback(self.cb(callback_id="cbk_demo002"), now=T0)
        self.assertEqual((h.accepted, h.reason_code), (False, "STALE_CONTEXT"))

    def test_callback_replay_rejected(self):
        self.cp.handle_callback(self.cb(), now=T0)
        h = self.cp.handle_callback(self.cb(), now=T0)
        self.assertEqual((h.accepted, h.detail), (False, "callback replay"))

    def test_wrong_user_wrong_role_wrong_approver(self):
        self.assertEqual(self.cp.handle_callback(self.cb(user_id=STRANGER), now=T0).reason_code, "IDENTITY_UNVERIFIED")
        self.assertEqual(self.cp.handle_callback(self.cb(user_id=OPERATOR, callback_id="cbk_x2"), now=T0).reason_code, "POLICY_DENIED")
        # OWNER-role user whose approver_ref differs from the one the approval was issued to
        cp2 = tg.ControlPlane(self.s, POLICY, self.o, self.r, approver_refs={OWNER: "ref:tg:other"})
        self.assertEqual(cp2.handle_callback(self.cb(callback_id="cbk_x3"), now=T0).reason_code, "IDENTITY_UNVERIFIED")
        self.assertIsNone(self.s.get_approval("apr_demo001").used_at)

    def test_changed_plan_or_expired_rejected(self):
        self.assertEqual(self.cp.handle_callback(self.cb(plan_hash="e" * 64), now=T0).reason_code, "STALE_CONTEXT")
        self.assertEqual(self.cp.handle_callback(self.cb(callback_id="cbk_x2", state_version=5), now=T0).reason_code, "STALE_CONTEXT")
        self.assertEqual(self.cp.handle_callback(self.cb(callback_id="cbk_x3"), now=T0 + timedelta(minutes=6)).reason_code, "STALE_CONTEXT")
        self.assertIsNone(self.s.get_approval("apr_demo001").used_at)

    def test_unknown_approval_id_denied(self):
        self.assertEqual(self.cp.handle_callback(self.cb(approval_id="apr_ghost01"), now=T0).reason_code, "IDENTITY_UNVERIFIED")
