"""Pure context guards (no I/O, no clock access; time is injected).

Implement the stale-context rules of FOUNDATION §5/§6 as pure functions over
already schema-valid documents. They decide whether a command/proposal may
proceed; they never dispatch anything. Deny-by-default; first failure wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

RFC3339_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")


def parse_utc(value: str) -> datetime:
    for fmt in RFC3339_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"not RFC3339 UTC: {value!r}")


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason_code: str
    detail: str

    @staticmethod
    def ok() -> "GuardDecision":
        return GuardDecision(True, "NONE", "")

    @staticmethod
    def deny(reason: str, detail: str) -> "GuardDecision":
        return GuardDecision(False, reason, detail)


@dataclass(frozen=True)
class SessionContext:
    """What the Store currently believes about a session (injected, not read)."""
    account_id: str
    session_id: str
    client_instance_id: str
    session_epoch: int
    lease_id: str
    lease_expires_at: datetime
    state_version: int
    config_hash: str
    policy_version: int
    abort_requested: bool = False
    unknown_commands_pending: int = 0


REQUIRED_KNOWN_FIELDS: Mapping[str, tuple[str, ...]] = {
    "NOOP": (), "OBSERVE": (),
    "LOGOUT": ("client.logged_in",),
    "WALK_TO": ("client.logged_in", "player.position"),
    "BANK_OPEN": ("client.logged_in", "bank.open"),
    "BANK_CLOSE": ("client.logged_in", "bank.open"),
    "BANK_DEPOSIT_INVENTORY": ("client.logged_in", "bank.open", "inventory.items"),
    "BANK_WITHDRAW": ("client.logged_in", "bank.open", "bank.items"),
}


def check_command_context(intent: Mapping, ctx: SessionContext, now: datetime) -> GuardDecision:
    """Binding/epoch/version/expiry/lease/abort checks for a schema-valid CommandIntent."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware UTC")
    if ctx.abort_requested:
        return GuardDecision.deny("POLICY_DENIED", "abort requested; no new actions")
    for field, expected in (("account_id", ctx.account_id), ("session_id", ctx.session_id),
                            ("client_instance_id", ctx.client_instance_id), ("lease_id", ctx.lease_id)):
        if intent[field] != expected:
            return GuardDecision.deny("IDENTITY_UNVERIFIED", f"{field} mismatch")
    if intent["session_epoch"] != ctx.session_epoch:
        return GuardDecision.deny("STALE_CONTEXT", "session_epoch mismatch")
    if intent["expected_state_version"] != ctx.state_version:
        return GuardDecision.deny("STALE_CONTEXT", "state_version mismatch; re-evaluate")
    if intent["config_hash"] != ctx.config_hash:
        return GuardDecision.deny("STALE_CONTEXT", "config_hash mismatch")
    if intent["policy_version"] != ctx.policy_version:
        return GuardDecision.deny("POLICY_DENIED", "policy_version mismatch")
    issued, expires = parse_utc(intent["issued_at"]), parse_utc(intent["expires_at"])
    if not issued < expires:
        return GuardDecision.deny("DEADLINE_EXCEEDED", "issued_at must precede expires_at")
    if now >= expires:
        return GuardDecision.deny("DEADLINE_EXCEEDED", "intent expired")
    if now < issued:
        return GuardDecision.deny("STALE_CONTEXT", "issued_at in the future (clock skew)")
    # Lease expiry alone never proves fencing (FOUNDATION §8), but an expired lease always denies.
    if now >= ctx.lease_expires_at:
        return GuardDecision.deny("STALE_CONTEXT", "lease expired")
    if expires > ctx.lease_expires_at:
        return GuardDecision.deny("STALE_CONTEXT", "intent outlives lease")
    if ctx.unknown_commands_pending > 0 and intent["operation"] not in ("NOOP", "OBSERVE"):
        return GuardDecision.deny("STALE_CONTEXT", "UNKNOWN command pending; reconcile first")
    return GuardDecision.ok()


def check_observation_freshness(intent: Mapping, observation: Mapping, ctx: SessionContext,
                                max_age_seconds: int, now: datetime) -> GuardDecision:
    """An action needs a KNOWN, fresh, same-binding observation for its required fields."""
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be >= 1")
    if observation["account_id"] != ctx.account_id or observation["client_instance_id"] != ctx.client_instance_id:
        return GuardDecision.deny("IDENTITY_UNVERIFIED", "observation binding mismatch")
    if observation["session_epoch"] != ctx.session_epoch:
        return GuardDecision.deny("STALE_CONTEXT", "observation epoch mismatch")
    if observation["state_version"] != intent["expected_state_version"]:
        return GuardDecision.deny("STALE_CONTEXT", "observation state_version differs from intent")
    if (now - parse_utc(observation["observed_at"])).total_seconds() > max_age_seconds:
        return GuardDecision.deny("STALE_CONTEXT", "observation too old")
    required = REQUIRED_KNOWN_FIELDS.get(intent["operation"])
    if required is None:
        return GuardDecision.deny("CAPABILITY_UNKNOWN", f"no field requirements for {intent['operation']}")
    fields = observation["fields"]
    for name in required:
        entry = fields.get(name)
        if entry is None or entry["quality"] != "KNOWN":
            return GuardDecision.deny("CAPABILITY_UNKNOWN", f"field {name} not KNOWN")
        if (now - parse_utc(entry["observed_at"])).total_seconds() > max_age_seconds:
            return GuardDecision.deny("STALE_CONTEXT", f"field {name} too old")
    # Bank semantics: closed/missing list is UNKNOWN, never zero (FOUNDATION §5).
    if intent["operation"] in ("BANK_DEPOSIT_INVENTORY", "BANK_WITHDRAW") and fields["bank.open"]["value"] is not True:
        return GuardDecision.deny("STALE_CONTEXT", "bank not open")
    return GuardDecision.ok()


def check_ai_proposal_context(proposal: Mapping, ctx: SessionContext) -> GuardDecision:
    """AI output is advisory: considered only if bound to the live epoch/version; never executed here."""
    if proposal["account_id"] != ctx.account_id:
        return GuardDecision.deny("IDENTITY_UNVERIFIED", "proposal account mismatch")
    if proposal["session_epoch"] != ctx.session_epoch:
        return GuardDecision.deny("STALE_CONTEXT", "proposal epoch mismatch")
    if proposal["observed_state_version"] != ctx.state_version:
        return GuardDecision.deny("STALE_CONTEXT", "proposal state_version stale")
    if proposal["requires_human_approval"] is not True:
        return GuardDecision.deny("POLICY_DENIED", "proposal must require human approval")
    if proposal["parameters"]:
        return GuardDecision.deny("POLICY_DENIED", "proposal parameters must be empty")
    return GuardDecision.ok()


def check_result_consistency(result: Mapping, intent: Mapping) -> GuardDecision:
    """A ResultEvent must match the intent binding; ACK/timeout are not verification."""
    for field in ("command_id", "session_id", "session_epoch"):
        if result[field] != intent[field]:
            return GuardDecision.deny("IDENTITY_UNVERIFIED", f"result {field} mismatch")
    if result["effect_status"] == "VERIFIED" and result["transport_status"] == "REJECTED":
        return GuardDecision.deny("STALE_CONTEXT", "REJECTED transport cannot be VERIFIED")
    return GuardDecision.ok()
