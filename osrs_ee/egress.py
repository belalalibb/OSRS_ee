"""S04b preparation — egress allowlist and a urllib opener that enforces it.

Policy, not a firewall: ``EgressPolicy.decide(host, port)`` is consulted by
``guarded_opener`` *before* any TCP connect; loopback is allowed by default and
every decision (allowed or denied) is appended to ``inventory`` so a target run
can produce the egress inventory required by docs/OUT_OF_SANDBOX.md (T33).

The real OS-level enforcement (firewall / network namespace) is a target-only
measure. This module provides the in-process part that can be tested locally:
a denied destination raises ``EgressDenied`` and no socket is ever opened.

Allowlist entries: ``"host:port"`` or ``"host:port:purpose"``; hosts are
compared case-insensitively and must be literal (no wildcards), ports 1..65535.
"""
from __future__ import annotations

import http.client
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from osrs_ee.guards import GuardDecision

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass(frozen=True)
class EgressRule:
    host: str
    ports: frozenset[int]
    purpose: str = ""


class EgressDenied(OSError):
    """Raised by the guarded opener before connecting to a non-allowlisted host."""


@dataclass
class EgressPolicy:
    rules: tuple[EgressRule, ...] = ()
    allow_loopback: bool = True
    inventory: list[tuple[str, str, int, bool, str]] = field(default_factory=list)

    @staticmethod
    def from_allowlist(entries: Iterable[str], *, allow_loopback: bool = True) -> "EgressPolicy":
        by_host: dict[str, tuple[set[int], str]] = {}
        for raw in entries:
            parts = str(raw).strip().split(":")
            if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
                raise ValueError(f"malformed egress entry {raw!r}; expected host:port[:purpose]")
            host = parts[0].lower()
            if "*" in host or " " in host:
                raise ValueError(f"egress host must be literal: {raw!r}")
            try:
                port = int(parts[1])
            except ValueError:
                raise ValueError(f"egress port not an integer: {raw!r}") from None
            if not (1 <= port <= 65535):
                raise ValueError(f"egress port out of range: {raw!r}")
            purpose = parts[2] if len(parts) == 3 else ""
            ports, prev_purpose = by_host.setdefault(host, (set(), purpose))
            ports.add(port)
            if purpose and not prev_purpose:
                by_host[host] = (ports, purpose)
        rules = tuple(EgressRule(h, frozenset(p), purpose) for h, (p, purpose) in sorted(by_host.items()))
        return EgressPolicy(rules=rules, allow_loopback=allow_loopback)

    def decide(self, host: str, port: int, *, now: Optional[datetime] = None) -> GuardDecision:
        h = str(host).lower().strip("[]")
        ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if h in LOOPBACK and self.allow_loopback:
            self.inventory.append((ts, h, int(port), True, "loopback"))
            return GuardDecision.ok()
        for rule in self.rules:
            if rule.host == h and int(port) in rule.ports:
                self.inventory.append((ts, h, int(port), True, rule.purpose))
                return GuardDecision.ok()
        self.inventory.append((ts, h, int(port), False, ""))
        return GuardDecision.deny("POLICY_DENIED", f"egress to {h}:{port} not in allowlist")

    def denied(self) -> list[tuple[str, str, int, bool, str]]:
        return [row for row in self.inventory if not row[3]]


def guarded_opener(policy: EgressPolicy, *, clock: Optional[Callable[[], datetime]] = None) -> urllib.request.OpenerDirector:
    """urllib opener (no env proxies) whose connections consult ``policy`` first."""

    def _check(host: str, port: int) -> None:
        d = policy.decide(host, port, now=clock() if clock else None)
        if not d.allowed:
            raise EgressDenied(d.detail)

    class _GuardedHTTPConnection(http.client.HTTPConnection):
        def connect(self):  # type: ignore[override]
            _check(self.host, self.port)
            return super().connect()

    class _GuardedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):  # type: ignore[override]
            _check(self.host, self.port)
            return super().connect()

    class _HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(_GuardedHTTPConnection, req)

    class _HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(_GuardedHTTPSConnection, req, context=self._context)

    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _HTTPHandler(), _HTTPSHandler())
