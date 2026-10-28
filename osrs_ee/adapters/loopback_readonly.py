"""S04b preparation — read-only adapter over a loopback HTTP state endpoint.

What this IS (local, testable now):
* ``observe()`` performs one bounded GET ``<endpoint>/observe`` against a
  loopback-only endpoint and returns the body only if it is strict JSON, valid
  against the Observation contract, and passes the honesty rules (no future
  timestamps, field timestamps <= observation timestamp, bank items UNKNOWN
  while the bank is not KNOWN-open, state_version never decreases).
* ``dispatch()`` NEVER sends anything. Every call returns ``NEVER_DISPATCH``
  (transport NOT_SENT / effect NOT_ATTEMPTED / reason POLICY_DENIED) and is
  counted in ``dispatch_refusals``. A worker journal using this adapter can
  therefore never contain DISPATCHING/ACKNOWLEDGED/UNKNOWN commands.

What this is NOT:
* It does not know how the endpoint is produced. On the target machine a
  read-only state exporter (ADR-007/008 — owner decision pending) would serve
  ``/observe``; here only ``tests/fake_http.FakeHttpServer`` ever serves it.
* Nothing here is evidence about a real game client. T06/T10/T30/T31/T33 stay
  NOT_RUN until executed on the target (docs/OUT_OF_SANDBOX.md).

Failure model: every network, size, parsing, contract or honesty problem is
surfaced as ``AdapterFailure`` (the only exception type the worker/conformance
suite accept) and summarised in ``last_error`` (never containing the body).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from osrs_ee import contracts
from osrs_ee.guards import parse_utc
from osrs_ee.worker import AdapterFailure, AdapterResponse

LOOPBACK_ENDPOINT = re.compile(
    r"^http://(127\.0\.0\.1|\[::1\]|localhost):[0-9]{2,5}(/[A-Za-z0-9_./-]*)?$")

NEVER_DISPATCH = AdapterResponse("NOT_SENT", "NOT_ATTEMPTED", (), "POLICY_DENIED")


class EndpointError(Exception):
    """Configuration rejected (fail closed): not loopback, bad bounds."""


@dataclass(frozen=True)
class LoopbackConfig:
    endpoint: str
    timeout_seconds: float = 2.0
    max_response_bytes: int = 256 * 1024
    max_observation_skew_seconds: int = 5

    def __post_init__(self) -> None:
        if not LOOPBACK_ENDPOINT.match(self.endpoint):
            raise EndpointError("endpoint must be http://127.0.0.1|[::1]|localhost:<port>[/path]")
        if not (0.2 <= float(self.timeout_seconds) <= 30.0):
            raise EndpointError("timeout_seconds must be within [0.2, 30]")
        if not (4096 <= int(self.max_response_bytes) <= 4 * 1024 * 1024):
            raise EndpointError("max_response_bytes must be within [4096, 4 MiB]")
        if not (0 <= int(self.max_observation_skew_seconds) <= 3600):
            raise EndpointError("max_observation_skew_seconds must be within [0, 3600]")


class LoopbackReadOnlyAdapter:
    def __init__(self, config: LoopbackConfig, *, opener: Optional[urllib.request.OpenerDirector] = None) -> None:
        self.config = config
        # No proxies: a loopback endpoint must never be routed through an env proxy.
        self._opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.observe_calls = 0
        self.dispatch_refusals = 0
        self.last_error: Optional[str] = None
        self._last_state_version: Optional[int] = None

    # -- observe -----------------------------------------------------------
    def _fail(self, msg: str) -> AdapterFailure:
        self.last_error = msg
        return AdapterFailure(msg)

    def _fetch(self) -> bytes:
        url = self.config.endpoint.rstrip("/") + "/observe"
        req = urllib.request.Request(url, method="GET", headers={
            "Accept": "application/json", "User-Agent": "osrs-ee/0 (read-only)"})
        try:
            with self._opener.open(req, timeout=self.config.timeout_seconds) as resp:
                raw = resp.read(self.config.max_response_bytes + 1)
        except urllib.error.HTTPError as e:
            raise self._fail(f"http {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise self._fail(f"network: {type(e).__name__}") from None
        if len(raw) > self.config.max_response_bytes:
            raise self._fail("response too large")
        return raw

    def observe(self, now: datetime) -> dict:
        self.observe_calls += 1
        raw = self._fetch()
        try:
            doc = contracts.loads_strict(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise self._fail(f"unparseable: not strict JSON ({type(e).__name__})") from None
        report = contracts.validate("Observation", doc)
        if not report.ok:
            first = report.errors[0] if report.errors else "invalid"
            raise self._fail(f"contract: {str(first)[:160]}")
        self._check_honesty(doc, now)
        self.last_error = None
        return doc

    def _check_honesty(self, obs: dict, now: datetime) -> None:
        skew = timedelta(seconds=self.config.max_observation_skew_seconds)
        observed_at = parse_utc(obs["observed_at"])
        if observed_at > now + skew:
            raise self._fail("honesty: observed_at in the future")
        for name, f in obs["fields"].items():
            if parse_utc(f["observed_at"]) > observed_at:
                raise self._fail(f"honesty: field {name} newer than observation")
        bank_open = obs["fields"].get("bank.open")
        bank_items = obs["fields"].get("bank.items")
        open_known_true = bool(bank_open) and bank_open.get("quality") == "KNOWN" and bank_open.get("value") is True
        if bank_items is not None and bank_items.get("quality") != "UNKNOWN" and not open_known_true:
            raise self._fail("honesty: bank.items claimed while bank not KNOWN open")
        sv = int(obs["state_version"])
        if self._last_state_version is not None and sv < self._last_state_version:
            raise self._fail(f"honesty: state_version decreased {self._last_state_version}->{sv}")
        self._last_state_version = sv

    # -- dispatch (never) --------------------------------------------------
    def dispatch(self, intent: dict, *, deadline: datetime, now: datetime) -> Optional[AdapterResponse]:
        self.dispatch_refusals += 1
        return NEVER_DISPATCH
