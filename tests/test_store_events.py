"""S02 Store tests part 2 — result events, approvals, recovery edges.
Persistent SQLite, injected clock, no network. Pure/local parts of T10/T12/T28.
Does NOT prove power-loss durability on the target OS.

Uses the S02b base case (StoreCase) so both files share the same fixtures/clock."""
from __future__ import annotations

from datetime import timedelta

from osrs_ee import store as st
from tests.test_store import ACC, T0, StoreCase, fixture


def event(name, **over):
    e = fixture("ResultEvent", name)
    e["session_epoch"], e["state_version"] = 1, 4
    e.update(over)
    return e


class Events(StoreCase):
    def dispatched(self):
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        return self.s.mark_dispatching("cmd_demo001", now=T0)

    def test_verified_event_sets_terminal_phase(self):
        self.dispatched()
        self.assertTrue(self.s.record_event(event("verified"), now=T0))
        cmd = self.s.get_command("cmd_demo001")
        self.assertEqual(cmd.phase, "VERIFIED")
        self.assertIsNotNone(cmd.finished_at)

    def test_duplicate_event_id_is_deduped(self):
        self.dispatched()
        self.assertTrue(self.s.record_event(event("verified"), now=T0))
        self.assertFalse(self.s.record_event(event("verified"), now=T0))
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "VERIFIED")

    def test_timeout_event_leaves_unknown_not_finished(self):
        self.dispatched()
        self.s.record_event(event("timeout_unknown"), now=T0)
        cmd = self.s.get_command("cmd_demo001")
        self.assertEqual(cmd.phase, "UNKNOWN")
        self.assertIsNone(cmd.finished_at)
        self.assertEqual(self.s.unknown_pending(ACC), 1)

    def test_unknown_can_be_resolved_only_by_verified_outcome(self):
        self.dispatched()
        self.s.record_event(event("timeout_unknown"), now=T0)
        # A second non-verified event cannot "upgrade" UNKNOWN.
        with self.assertRaises(st.StoreError):
            self.s.record_event(event("timeout_unknown", event_id="evt_demo009"), now=T0)
        self.assertTrue(self.s.record_event(event("verified", event_id="evt_demo010"), now=T0))
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "VERIFIED")
        self.assertEqual(self.s.unknown_pending(ACC), 0)

    def test_second_terminal_event_rejected(self):
        self.dispatched()
        self.s.record_event(event("verified"), now=T0)
        with self.assertRaises(st.StoreError):
            self.s.record_event(event("timeout_unknown"), now=T0)

    def test_event_with_wrong_epoch_or_session_rejected(self):
        self.dispatched()
        with self.assertRaises(st.LeaseConflict):
            self.s.record_event(event("verified", session_epoch=2), now=T0)
        with self.assertRaises(st.LeaseConflict):
            self.s.record_event(event("verified", session_id="sess_other01"), now=T0)
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "DISPATCHING")

    def test_invalid_event_schema_rejected_before_write(self):
        self.dispatched()
        bad = event("verified")
        bad["evidence_refs"] = []  # VERIFIED requires evidence
        with self.assertRaises(Exception):
            self.s.record_event(bad, now=T0)
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "DISPATCHING")

    def test_event_for_unknown_command_rejected(self):
        self.lease()
        with self.assertRaises(st.StoreError):
            self.s.record_event(event("verified", command_id="cmd_missing01"), now=T0)

    def test_not_sent_event_marks_not_sent(self):
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        self.assertTrue(self.s.record_event(event("not_sent"), now=T0))
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "NOT_SENT")


class Approvals(StoreCase):
    PLAN = "d" * 64

    def make(self, expires=timedelta(minutes=10)):
        if self.s.active_lease(ACC) is None:
            self.lease()  # approvals are FK-bound to a real account
        self.s.create_approval(approval_id="apr_demo001", incident_id="inc_demo001", account_id=ACC, session_epoch=1,
                               plan_hash=self.PLAN, state_version=4, approver_ref="ref:tg:owner", expires_at=T0 + expires, now=T0)

    def consume(self, now=T0, **over):
        kw = dict(incident_id="inc_demo001", account_id=ACC, session_epoch=1, plan_hash=self.PLAN, state_version=4)
        kw.update(over)
        self.s.consume_approval("apr_demo001", now=now, **kw)

    def test_single_use(self):
        self.make()
        self.consume()
        with self.assertRaises(st.ApprovalError):
            self.consume()

    def test_bound_context_mismatch_refused(self):
        self.make()
        for over in (dict(plan_hash="e" * 64), dict(session_epoch=2), dict(state_version=5), dict(incident_id="inc_demo002")):
            with self.assertRaises(st.ApprovalError):
                self.consume(**over)
        self.consume()  # still unused after refused attempts

    def test_expiry_enforced_at_create_and_consume(self):
        with self.assertRaises(st.ApprovalError):
            self.make(expires=timedelta(0))
        self.make()

    def test_approval_requires_existing_account(self):
        with self.assertRaises(Exception):
            self.s.create_approval(approval_id="apr_demo002", incident_id="inc_demo001", account_id="acc_ghost01", session_epoch=1,
                                   plan_hash=self.PLAN, state_version=4, approver_ref="ref:tg:owner", expires_at=T0 + timedelta(minutes=1), now=T0)
        with self.assertRaises(st.ApprovalError):
            self.consume(now=T0 + timedelta(minutes=10))


class RecoveryEdges(StoreCase):
    def test_recover_reports_no_affected_on_clean_store(self):
        self.lease()
        self.assertEqual(self.s.recover(now=T0), [])
        self.assertEqual(self.s.get_account(ACC).state, "LEASED")

    def test_recovery_from_resting_with_stale_inflight_row(self):
        """READY/RESTING must have a direct edge to RECOVERY_REQUIRED (FOUNDATION §5)."""
        self.lease()
        self.s.prepare_command(self.intent(), now=T0)
        self.s.mark_dispatching("cmd_demo001", now=T0)
        # Operator drives the account to RESTING while a DISPATCHING row is stale on disk.
        self.s.release_lease("lease_demo001", session_epoch=1, reason="test", now=T0)
        acc = self.s.get_account(ACC)
        for state in ("STARTING", "RUNNING", "DRAINING", "RESTING"):
            acc = self.s.transition(ACC, state, expected_version=acc.state_version, reason="test", now=T0)
        self.assertEqual(acc.state, "RESTING")
        affected = self.reopen().recover(now=T0) or [ACC]
        self.assertIn(ACC, affected)
        self.assertEqual(self.s.get_account(ACC).state, "RECOVERY_REQUIRED")
        self.assertEqual(self.s.get_command("cmd_demo001").phase, "UNKNOWN")
