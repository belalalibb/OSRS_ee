"""S07 — AI advisory layer, fake-first. The AI never acts.

Pure/local rules (FOUNDATION §"AI"): the model sees *redacted* data only with
consent, within size/age/budget/deadline limits; it has no action token, no
shell/files/network authority; prompt injection cannot alter policy. Its only
output is an `AIProposal` (schema-validated, `requires_human_approval` const
true, `parameters` empty) that is then checked against the live context by
`guards.check_ai_proposal_context`. Anything else is discarded with a reason.

Provider access is through `Provider`; `FakeProvider` is scripted. No sockets.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional, Protocol

from osrs_ee import canonical, contracts, guards
from osrs_ee.contracts import ContractError
from osrs_ee.guards import GuardDecision, SessionContext, parse_utc
from osrs_ee.telegram import Redactor

__all__ = ["AdvisorConfig", "Budget", "Provider", "FakeProvider", "ProviderTimeout", "Advice", "Advisor", "redact_observation"]

ALLOWED_ACTIONS = frozenset({"NO_ACTION", "REQUEST_REOBSERVATION", "REQUEST_HUMAN_REVIEW"})
# Observation fields the advisor may ever see; everything else is stripped.
VISIBLE_FIELDS = frozenset({"client.logged_in", "bank.open", "player.position", "inventory.items", "bank.items"})
STRIPPED_KEYS = frozenset({"credential_ref", "proxy_ref", "password", "token", "session_token", "cookie"})


class ProviderTimeout(Exception):
    """Provider did not answer inside the deadline."""


@dataclass(frozen=True)
class AdvisorConfig:
    max_prompt_bytes: int = 8192
    max_observation_age_seconds: int = 60
    deadline_seconds: int = 20
    max_calls_per_incident: int = 2


@dataclass
class Budget:
    """Global call/byte budget; exhausted budget denies before any provider call."""
    max_calls: int
    max_bytes: int
    calls: int = 0
    bytes_sent: int = 0
    per_incident: dict[str, int] = field(default_factory=dict)

    def allow(self, incident_id: str, nbytes: int, per_incident_cap: int) -> GuardDecision:
        if self.calls >= self.max_calls:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "advisor call budget exhausted")
        if self.bytes_sent + nbytes > self.max_bytes:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "advisor byte budget exhausted")
        if self.per_incident.get(incident_id, 0) >= per_incident_cap:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "per-incident call cap reached")
        return GuardDecision.ok()

    def charge(self, incident_id: str, nbytes: int) -> None:
        self.calls += 1
        self.bytes_sent += nbytes
        self.per_incident[incident_id] = self.per_incident.get(incident_id, 0) + 1


class Provider(Protocol):
    def complete(self, prompt: bytes, *, deadline: datetime, now: datetime) -> Any: ...


@dataclass
class FakeProvider:
    """Scripted: each call pops one item. dict -> returned as the raw proposal;
    Exception -> raised (ProviderTimeout for a deadline miss); str -> raw text
    the advisor must parse (lets tests feed injection/garbage)."""
    script: list[object] = field(default_factory=list)
    prompts: list[bytes] = field(default_factory=list)

    def plan(self, *items: object) -> "FakeProvider":
        self.script.extend(items)
        return self

    def complete(self, prompt: bytes, *, deadline: datetime, now: datetime) -> Any:
        self.prompts.append(prompt)
        if not self.script:
            raise ProviderTimeout("no scripted reply")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@dataclass(frozen=True)
class Advice:
    accepted: bool
    proposal: Optional[dict]
    reason_code: str = "NONE"
    detail: str = ""


def redact_observation(observation: Mapping, redactor: Redactor) -> dict:
    """Keep only VISIBLE_FIELDS with quality/value; alias the account; strip secret-ish keys."""
    fields = {}
    for name, entry in observation.get("fields", {}).items():
        if name in VISIBLE_FIELDS:
            fields[name] = {"quality": entry["quality"], "value": entry["value"]}
    out = {
        "account": redactor.aliases.get(observation["account_id"], "alias:unknown"),
        "session_epoch": observation["session_epoch"],
        "state_version": observation["state_version"],
        "observed_at": observation["observed_at"],
        "fields": fields,
    }
    text = json.dumps(out, sort_keys=True, ensure_ascii=False)
    reason = redactor.scan(text)
    if reason:
        raise ValueError(f"redacted observation still unsafe: {reason}")
    return out


class Advisor:
    """Builds a bounded, redacted prompt; validates the reply; never executes."""

    def __init__(self, provider: Provider, redactor: Redactor, budget: Budget, config: AdvisorConfig = AdvisorConfig()) -> None:
        self.provider, self.redactor, self.budget, self.config = provider, redactor, budget, config
        self.audit: list[tuple[str, str, str]] = []  # (incident_id, outcome, reason)

    def _log(self, incident_id: str, outcome: str, reason: str) -> None:
        self.audit.append((incident_id, outcome, reason))

    def advise(self, *, incident_id: str, observation: Mapping, ctx: SessionContext, consent: bool, now: datetime) -> Advice:
        # 1) consent gate — no data leaves without it
        if not consent:
            self._log(incident_id, "DENIED", "POLICY_DENIED")
            return Advice(False, None, "POLICY_DENIED", "no consent for AI review")
        # 2) binding + age of the data we would show
        if observation["account_id"] != ctx.account_id or observation["session_epoch"] != ctx.session_epoch:
            self._log(incident_id, "DENIED", "IDENTITY_UNVERIFIED")
            return Advice(False, None, "IDENTITY_UNVERIFIED", "observation not bound to live context")
        if (now - parse_utc(observation["observed_at"])).total_seconds() > self.config.max_observation_age_seconds:
            self._log(incident_id, "DENIED", "STALE_CONTEXT")
            return Advice(False, None, "STALE_CONTEXT", "observation too old for review")
        # 3) redact + size cap
        try:
            redacted = redact_observation(observation, self.redactor)
        except ValueError as e:
            self._log(incident_id, "DENIED", "POLICY_DENIED")
            return Advice(False, None, "POLICY_DENIED", str(e))
        prompt = canonical.canonical_bytes({"incident_id": incident_id, "observation": redacted,
                                            "allowed_actions": sorted(ALLOWED_ACTIONS), "note": "advisory only; no execution"})
        if len(prompt) > self.config.max_prompt_bytes:
            self._log(incident_id, "DENIED", "INSUFFICIENT_RESOURCES")
            return Advice(False, None, "INSUFFICIENT_RESOURCES", "prompt exceeds size cap")
        # 4) budget
        d = self.budget.allow(incident_id, len(prompt), self.config.max_calls_per_incident)
        if not d.allowed:
            self._log(incident_id, "DENIED", d.reason_code)
            return Advice(False, None, d.reason_code, d.detail)
        self.budget.charge(incident_id, len(prompt))
        # 5) call with deadline
        deadline = now + timedelta(seconds=self.config.deadline_seconds)
        try:
            raw = self.provider.complete(prompt, deadline=deadline, now=now)
        except ProviderTimeout:
            self._log(incident_id, "DENIED", "DEADLINE_EXCEEDED")
            return Advice(False, None, "DEADLINE_EXCEEDED", "provider timed out")
        except Exception as e:  # noqa: BLE001 - provider failure is advisory failure, never an action
            self._log(incident_id, "DENIED", "CAPABILITY_UNKNOWN")
            return Advice(False, None, "CAPABILITY_UNKNOWN", f"provider error: {type(e).__name__}")
        # 6) parse + schema + context; reply text is data, never instructions
        if isinstance(raw, (str, bytes)):
            try:
                raw = contracts.loads_strict(raw if isinstance(raw, str) else raw.decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                self._log(incident_id, "DENIED", "CAPABILITY_UNKNOWN")
                return Advice(False, None, "CAPABILITY_UNKNOWN", f"unparseable reply: {type(e).__name__}")
        if not isinstance(raw, dict):
            self._log(incident_id, "DENIED", "CAPABILITY_UNKNOWN")
            return Advice(False, None, "CAPABILITY_UNKNOWN", "reply is not an object")
        try:
            contracts.require_valid("AIProposal", raw)
        except ContractError as e:
            self._log(incident_id, "DENIED", "POLICY_DENIED")
            return Advice(False, None, "POLICY_DENIED", f"proposal violates contract: {str(e)[:120]}")
        if raw["incident_id"] != incident_id:
            self._log(incident_id, "DENIED", "STALE_CONTEXT")
            return Advice(False, None, "STALE_CONTEXT", "proposal for a different incident")
        g = guards.check_ai_proposal_context(raw, ctx)
        if not g.allowed:
            self._log(incident_id, "DENIED", g.reason_code)
            return Advice(False, None, g.reason_code, g.detail)
        if self.redactor.scan(raw["diagnosis"]):
            self._log(incident_id, "DENIED", "POLICY_DENIED")
            return Advice(False, None, "POLICY_DENIED", "diagnosis contains secret-shaped content")
        self._log(incident_id, "ACCEPTED", "NONE")
        return Advice(True, dict(raw))
