"""Adapter conformance suite — what *any* adapter must satisfy before the
worker is allowed to use it (S04a; reused unchanged for the real S04b adapter).

Checks (each yields PASS/FAIL with detail; the suite never raises for an
adapter defect — defects are findings):

  C1 observe-contract      observe() returns a document valid against the
                           Observation contract (strict validator).
  C2 observe-honest-time   observed_at is not in the future relative to `now`
                           and every field's observed_at <= observation.observed_at.
  C3 observe-stable        two consecutive observe() calls with the same `now`
                           produce the same state_version or a higher one (never lower).
  C4 dispatch-type         dispatch() returns None or AdapterResponse with
                           transport/effect statuses from the contract enums.
  C5 dispatch-no-leak      dispatch() raises only AdapterFailure (or returns);
                           any other exception type is a defect.
  C6 dispatch-noop-safe    an OBSERVE/NOOP intent never yields effect_status
                           VERIFIED with evidence_refs empty (an effect claim
                           must carry evidence).
  C7 no-network            the adapter did not open sockets during the run
                           (socket.socket patched; real adapters with an
                           allowlisted loopback endpoint declare it via
                           `allowed_hosts`).

The suite only ever sends `probe_intent` (default: OBSERVE, which is in
SAFE_OPERATIONS). It must never be run against a live account without an
explicit S04b/S05 permission — that rule is documented, not enforceable here.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from osrs_ee import contracts
from osrs_ee.guards import parse_utc
from osrs_ee.worker import Adapter, AdapterFailure, AdapterResponse, SAFE_OPERATIONS

TRANSPORT_STATUSES = frozenset({"ACKNOWLEDGED", "REJECTED", "TIMEOUT", "CONNECTION_LOST", "NOT_SENT"})
EFFECT_STATUSES = frozenset({"UNKNOWN", "VERIFIED", "FAILED_VERIFIED", "NOT_ATTEMPTED"})


@dataclass(frozen=True)
class Finding:
    check: str
    passed: bool
    detail: str = ""


@dataclass
class ConformanceReport:
    adapter: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(f.passed for f in self.findings)

    def add(self, check: str, passed: bool, detail: str = "") -> None:
        self.findings.append(Finding(check, passed, detail))

    def to_dict(self) -> dict:
        return {"adapter": self.adapter, "passed": self.passed,
                "findings": [{"check": f.check, "passed": f.passed, "detail": f.detail} for f in self.findings]}


def _default_probe(now: datetime, observation: dict) -> dict:
    """OBSERVE intent shaped like the CommandIntent contract (see fixtures/valid/CommandIntent/noop.json)."""
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": "1.0",
        "command_id": "cmd_conformance_probe01",
        "account_id": observation.get("account_id", "acc_conformance01"),
        "session_id": "sess_conformance01",
        "client_instance_id": observation.get("client_instance_id", "client_conformance01"),
        "session_epoch": observation.get("session_epoch", 1),
        "lease_id": "lease_conformance01",
        "expected_state_version": observation.get("state_version", 1),
        "operation": "OBSERVE",
        "params": {},
        "precondition_ref": "a" * 64,
        "postcondition_ref": "b" * 64,
        "issued_at": ts,
        "expires_at": (now + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy_version": 1,
        "config_hash": "0" * 64,
    }


def run_conformance(adapter: Adapter, *, now: datetime, probe_intent: Optional[dict] = None,
                    allowed_hosts: frozenset[str] = frozenset(),
                    name: Optional[str] = None) -> ConformanceReport:
    report = ConformanceReport(name or type(adapter).__name__)
    opened: list[tuple] = []
    real_socket = socket.socket
    if isinstance(real_socket, type):
        class _GuardSocket(real_socket):  # type: ignore[misc,valid-type]
            def connect(self, address):  # noqa: D401
                host = address[0] if isinstance(address, tuple) else str(address)
                opened.append(address)
                if host not in allowed_hosts:
                    raise AdapterFailure(f"conformance: connection to {host!r} not in allowlist")
                return super().connect(address)
        socket.socket = _GuardSocket  # type: ignore[misc]
    else:
        # socket.socket already replaced by a harness guard (e.g. tests/conftest.py);
        # wrap it so any attempt is still recorded as an out-of-allowlist connection.
        def _blocked(*_a, **_k):
            opened.append(("<blocked-by-harness>",))
            raise AdapterFailure("conformance: socket creation blocked")
        socket.socket = _blocked  # type: ignore[assignment]
    try:
        # ---- C1/C2/C3 observe
        observation: Optional[dict] = None
        try:
            observation = adapter.observe(now)
            rep = contracts.validate("Observation", observation)
            report.add("C1 observe-contract", rep.ok, "; ".join(rep.errors[:3]))
        except Exception as e:  # noqa: BLE001
            report.add("C1 observe-contract", False, f"observe raised {type(e).__name__}: {e}")
        if observation is not None and isinstance(observation, dict):
            try:
                top = parse_utc(observation["observed_at"])
                ok = top <= now
                detail = "" if ok else f"observed_at {observation['observed_at']} is after now"
                for key, f in observation.get("fields", {}).items():
                    if parse_utc(f["observed_at"]) > top:
                        ok, detail = False, f"field {key} observed_at after observation.observed_at"
                        break
                report.add("C2 observe-honest-time", ok, detail)
            except Exception as e:  # noqa: BLE001
                report.add("C2 observe-honest-time", False, f"unparseable timestamps: {e}")
            try:
                second = adapter.observe(now)
                ok = second.get("state_version", 0) >= observation.get("state_version", 0)
                report.add("C3 observe-stable", ok, "" if ok else "state_version decreased between calls")
            except Exception as e:  # noqa: BLE001
                report.add("C3 observe-stable", False, f"second observe raised {type(e).__name__}: {e}")
        # ---- C4/C5/C6 dispatch
        intent = probe_intent or _default_probe(now, observation or {})
        if intent.get("operation") not in SAFE_OPERATIONS:
            report.add("C0 probe-safe", False, f"probe operation {intent.get('operation')!r} is not in SAFE_OPERATIONS; refusing")
        else:
            rep = contracts.validate("CommandIntent", intent)
            if not rep.ok:
                report.add("C0 probe-valid", False, "; ".join(rep.errors[:3]))
            else:
                resp: Optional[AdapterResponse] = None
                try:
                    resp = adapter.dispatch(intent, deadline=now + timedelta(seconds=5), now=now)
                    report.add("C5 dispatch-no-leak", True)
                except AdapterFailure as e:
                    report.add("C5 dispatch-no-leak", True, f"AdapterFailure (allowed): {e}")
                except Exception as e:  # noqa: BLE001
                    report.add("C5 dispatch-no-leak", False, f"raised {type(e).__name__}: {e}")
                if resp is None:
                    report.add("C4 dispatch-type", True, "None (timeout) or failure")
                elif not isinstance(resp, AdapterResponse):
                    report.add("C4 dispatch-type", False, f"returned {type(resp).__name__}")
                else:
                    ok = resp.transport_status in TRANSPORT_STATUSES and resp.effect_status in EFFECT_STATUSES
                    report.add("C4 dispatch-type", ok, "" if ok else f"{resp.transport_status}/{resp.effect_status} not in enums")
                    claims_effect = resp.effect_status == "VERIFIED" and not resp.evidence_refs
                    report.add("C6 dispatch-noop-safe", not claims_effect,
                               "" if not claims_effect else "VERIFIED without evidence_refs")
    finally:
        socket.socket = real_socket  # type: ignore[misc]
    bad = [a for a in opened if (a[0] if isinstance(a, tuple) else str(a)) not in allowed_hosts]  # harness-blocked counts as bad
    report.add("C7 no-network", not bad, "" if not bad else f"connections outside allowlist: {bad[:3]}")
    return report
