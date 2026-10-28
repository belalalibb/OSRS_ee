"""Pure parts of T05 (AI has no authority), T26 (time rejected/injected) and FOUNDATION §5 stale-context rules."""
from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from osrs_ee import contracts, guards

FIX = Path(__file__).resolve().parent.parent / "contracts" / "fixtures" / "valid"
utc = guards.parse_utc


def load(contract: str, name: str) -> dict:
    return contracts.require_valid(contract, json.loads((FIX / contract / f"{name}.json").read_text()))


class Base(unittest.TestCase):
    def setUp(self):
        self.intent = load("CommandIntent", "bank_withdraw")
        self.noop = load("CommandIntent", "noop")
        self.obs = load("Observation", "basic")
        self.ai = load("AIProposal", "review")
        self.ctx = guards.SessionContext(
            account_id="acc_demo001", session_id="sess_demo001", client_instance_id="client_demo001",
            session_epoch=3, lease_id="lease_demo001", lease_expires_at=utc("2026-10-23T20:00:00Z"),
            state_version=7, config_hash="c" * 64, policy_version=1)
        self.now = utc("2026-10-23T19:00:05Z")


class CommandContext(Base):
    def _deny(self, intent=None, ctx=None, now=None, reason=None):
        d = guards.check_command_context(intent or self.intent, ctx or self.ctx, now or self.now)
        self.assertFalse(d.allowed, d)
        if reason:
            self.assertEqual(d.reason_code, reason, d)

    def test_happy_path(self):
        self.assertTrue(guards.check_command_context(self.intent, self.ctx, self.now).allowed)

    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            guards.check_command_context(self.intent, self.ctx, datetime(2026, 10, 23, 19, 0, 5))

    def test_abort_blocks_everything_first(self):
        ctx = replace(self.ctx, abort_requested=True)
        self._deny(ctx=ctx, reason="POLICY_DENIED")
        self._deny(intent=self.noop, ctx=ctx, reason="POLICY_DENIED")

    def test_binding_mismatches(self):
        for field in ("account_id", "session_id", "client_instance_id", "lease_id"):
            self._deny(intent=dict(self.intent, **{field: "other_zzz001"}), reason="IDENTITY_UNVERIFIED")

    def test_epoch_mismatch_is_stale(self):
        self._deny(intent=dict(self.intent, session_epoch=2), reason="STALE_CONTEXT")
        self._deny(intent=dict(self.intent, session_epoch=4), reason="STALE_CONTEXT")

    def test_state_version_mismatch_is_stale(self):
        self._deny(intent=dict(self.intent, expected_state_version=6), reason="STALE_CONTEXT")

    def test_config_hash_mismatch(self):
        self._deny(intent=dict(self.intent, config_hash="d" * 64), reason="STALE_CONTEXT")

    def test_policy_version_mismatch(self):
        self._deny(intent=dict(self.intent, policy_version=2), reason="POLICY_DENIED")

    def test_expiry_rules(self):
        self._deny(now=utc("2026-10-23T19:00:31Z"), reason="DEADLINE_EXCEEDED")
        self._deny(now=utc("2026-10-23T19:00:00Z"), reason="STALE_CONTEXT")
        self._deny(intent=dict(self.intent, expires_at=self.intent["issued_at"]), reason="DEADLINE_EXCEEDED")

    def test_lease_rules(self):
        self._deny(ctx=replace(self.ctx, lease_expires_at=utc("2026-10-23T19:00:05Z")), reason="STALE_CONTEXT")
        self._deny(ctx=replace(self.ctx, lease_expires_at=utc("2026-10-23T19:00:20Z")), reason="STALE_CONTEXT")

    def test_unknown_pending_blocks_non_observational(self):
        ctx = replace(self.ctx, unknown_commands_pending=1)
        self._deny(ctx=ctx, reason="STALE_CONTEXT")
        self.assertTrue(guards.check_command_context(self.noop, ctx, self.now).allowed)


class ObservationFreshness(Base):
    def test_happy_path(self):
        self.assertTrue(guards.check_observation_freshness(self.intent, self.obs, self.ctx, 30, self.now).allowed)

    def test_bad_max_age(self):
        with self.assertRaises(ValueError):
            guards.check_observation_freshness(self.intent, self.obs, self.ctx, 0, self.now)

    def test_stale_field_blocks_walk(self):
        d = guards.check_observation_freshness(load("CommandIntent", "walk_to"), self.obs, self.ctx, 30, self.now)
        self.assertEqual(d.reason_code, "CAPABILITY_UNKNOWN")

    def test_too_old(self):
        d = guards.check_observation_freshness(self.intent, self.obs, self.ctx, 30, self.now + timedelta(seconds=60))
        self.assertEqual(d.reason_code, "STALE_CONTEXT")

    def test_state_version_drift(self):
        d = guards.check_observation_freshness(self.intent, dict(self.obs, state_version=8), self.ctx, 30, self.now)
        self.assertEqual(d.reason_code, "STALE_CONTEXT")

    def test_binding_mismatch(self):
        d = guards.check_observation_freshness(self.intent, dict(self.obs, client_instance_id="client_other01"), self.ctx, 30, self.now)
        self.assertEqual(d.reason_code, "IDENTITY_UNVERIFIED")

    def test_bank_closed_is_not_zero(self):
        obs = copy.deepcopy(self.obs)
        obs["fields"]["bank.open"]["value"] = False
        self.assertFalse(guards.check_observation_freshness(self.intent, obs, self.ctx, 30, self.now).allowed)
        obs["fields"]["bank.open"]["value"] = True
        obs["fields"]["bank.items"] = {"quality": "UNKNOWN", "source": "agent.bank", "observed_at": "2026-10-23T19:00:00Z", "value": None}
        self.assertEqual(guards.check_observation_freshness(self.intent, obs, self.ctx, 30, self.now).reason_code, "CAPABILITY_UNKNOWN")


class AIProposal(Base):
    def test_valid_proposal_is_considered_not_executed(self):
        self.assertTrue(guards.check_ai_proposal_context(self.ai, self.ctx).allowed)
        self.assertFalse(any(n.startswith("execute") for n in dir(guards)))

    def test_stale_epoch_or_version_rejected(self):
        self.assertEqual(guards.check_ai_proposal_context(dict(self.ai, session_epoch=2), self.ctx).reason_code, "STALE_CONTEXT")
        self.assertEqual(guards.check_ai_proposal_context(dict(self.ai, observed_state_version=6), self.ctx).reason_code, "STALE_CONTEXT")

    def test_wrong_account(self):
        self.assertEqual(guards.check_ai_proposal_context(dict(self.ai, account_id="acc_other001"), self.ctx).reason_code, "IDENTITY_UNVERIFIED")

    def test_confidence_one_grants_nothing(self):
        self.assertTrue(guards.check_ai_proposal_context(dict(self.ai, confidence=1.0), self.ctx).allowed)
        self.assertIs(self.ai["requires_human_approval"], True)


class ResultConsistency(Base):
    def test_timeout_stays_unknown(self):
        res = load("ResultEvent", "timeout_unknown")
        self.assertEqual(res["effect_status"], "UNKNOWN")
        self.assertTrue(guards.check_result_consistency(res, self.intent).allowed)

    def test_binding_mismatch(self):
        res = dict(load("ResultEvent", "verified"), session_epoch=4)
        self.assertEqual(guards.check_result_consistency(res, self.intent).reason_code, "IDENTITY_UNVERIFIED")

    def test_rejected_cannot_be_verified(self):
        res = dict(load("ResultEvent", "verified"), transport_status="REJECTED")
        self.assertFalse(guards.check_result_consistency(res, self.intent).allowed)


class ParseUtc(unittest.TestCase):
    def test_accepts_subset(self):
        self.assertEqual(utc("2026-01-01T00:00:00Z").tzinfo, timezone.utc)
        self.assertEqual(utc("2026-01-01T00:00:00.5Z").microsecond, 500000)

    def test_rejects_offsets_and_naive(self):
        for bad in ("2026-01-01T00:00:00+02:00", "2026-01-01 00:00:00", "2026-01-01T00:00:00"):
            with self.assertRaises(ValueError):
                utc(bad)
