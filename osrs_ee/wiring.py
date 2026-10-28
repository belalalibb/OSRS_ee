"""WIRE-01 — build the Telegram / AI / egress components from ``ServiceConfig``.

One place decides, per component, whether the *real* implementation or the
*fake* is used, and says so in a ``Wiring.report()`` that the CLI prints
verbatim (``REAL`` / ``FAKE`` / ``DISABLED``). Nothing here opens a socket:
constructing a transport/provider only resolves ``ref:env:NAME`` secrets and
validates hosts; the first network call happens later, through an opener that
is guarded by the egress policy built from ``[network].egress_allowlist``.

Rules enforced here (fail closed):
* ``telegram.enabled`` → ``TelegramHttpTransport`` + ``TelegramPoller`` +
  ``AccessPolicy``; the bot token must be ``ref:env:<NAME>`` and present in the
  environment, otherwise ``WiringError`` (never a silent fallback to fake).
* ``ai.enabled`` → ``OpenAICompatProvider`` + ``Budget`` from ``[ai]``;
  same secret rule.
* Every real component's HTTP host:port must be present in
  ``network.egress_allowlist`` — the guarded opener refuses otherwise, and we
  refuse *before* building so the operator sees the exact entry to add.
* ``allow_real_network`` (CLI flag) AND env ``OSRS_EE_ALLOW_NETWORK=1`` are both
  required for any REAL non-loopback component; otherwise ``WiringError``.
  Loopback base URLs (fake servers) do not need them.
"""
from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .advisor import Advisor, AdvisorConfig, Budget, FakeProvider
from .config import ServiceConfig
from .egress import EgressPolicy, LOOPBACK, guarded_opener
from .telegram import AccessPolicy, FakeTransport, Outbox, Redactor

ALLOW_NETWORK_ENV = "OSRS_EE_ALLOW_NETWORK"


class WiringError(Exception):
    """Configuration says REAL but the preconditions are not met; nothing was built."""


@dataclass
class Component:
    name: str
    mode: str                 # REAL | FAKE | DISABLED | LOOPBACK_ONLY
    detail: str = ""
    obj: Any = None


@dataclass
class Wiring:
    redactor: Redactor
    egress: EgressPolicy
    outbox: Outbox
    transport: Component
    poller: Component
    access: Optional[AccessPolicy]
    advisor: Component
    provider: Component
    components: list[Component] = field(default_factory=list)

    def report(self) -> list[dict]:
        return [{"component": c.name, "mode": c.mode, "detail": c.detail} for c in self.components]

    @property
    def any_real(self) -> bool:
        return any(c.mode == "REAL" for c in self.components)


def _host_port(url: str) -> tuple[str, int]:
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    port = u.port or (443 if u.scheme == "https" else 80)
    return host, port


def _require_egress(policy: EgressPolicy, url: str, purpose: str) -> None:
    host, port = _host_port(url)
    if host in LOOPBACK:
        return
    rows_before = len(policy.inventory)
    d = policy.decide(host, port)
    del policy.inventory[rows_before:]  # a pre-check is not an egress event
    if not d.allowed:
        raise WiringError(f"{purpose}: add \"{host}:{port}:{purpose}\" to [network].egress_allowlist (currently refused)")


def build(cfg: ServiceConfig, *, env: Mapping[str, str] = os.environ, allow_real_network: bool = False,
          clock=None) -> Wiring:
    allow_real = allow_real_network and env.get(ALLOW_NETWORK_ENV) == "1"
    redactor = Redactor(aliases={cfg.account.account_id: cfg.account.alias})
    egress = EgressPolicy.from_allowlist(cfg.network.egress_allowlist, allow_loopback=True)
    opener = guarded_opener(egress, clock=clock)
    components: list[Component] = []

    # ---- Telegram
    tg = cfg.telegram
    access: Optional[AccessPolicy] = None
    if not tg.enabled:
        transport = Component("telegram.transport", "FAKE", "telegram.enabled=false → FakeTransport (nothing is sent)", FakeTransport())
        poller = Component("telegram.poller", "DISABLED", "no inbound commands without a real transport")
    else:
        from .transports import TelegramHttpTransport, TelegramPoller, TransportConfig, TransportError
        loopback = _host_port(tg.base_url)[0] in LOOPBACK
        if not (allow_real or loopback):
            raise WiringError(f"telegram.enabled=true needs --allow-real-network and {ALLOW_NETWORK_ENV}=1 (refused; nothing built)")
        _require_egress(egress, tg.base_url, "telegram")
        try:
            t = TelegramHttpTransport(tg.bot_token_ref or "", redactor,
                                      TransportConfig(base_url=tg.base_url, timeout_seconds=float(tg.timeout_seconds),
                                                      allowed_hosts=frozenset(tg.allowed_hosts)),
                                      env=env, opener=opener)
        except TransportError as e:
            raise WiringError(f"telegram: {e}") from None
        transport = Component("telegram.transport", "REAL",
                              f"TelegramHttpTransport → {_host_port(tg.base_url)[0]} (token via {tg.bot_token_ref})", t)
        poller = Component("telegram.poller", "REAL", f"TelegramPoller poll_timeout={tg.poll_timeout_seconds}s",
                           TelegramPoller(t, poll_timeout_seconds=tg.poll_timeout_seconds))
        access = AccessPolicy(chat_ids=frozenset(tg.chat_ids), users={u: "OPERATOR" for u in tg.approver_user_ids})
    outbox = Outbox(transport.obj, redactor, capacity=tg.outbox_capacity)
    components += [transport, poller]

    # ---- AI (advisory only)
    ai = cfg.ai
    budget = Budget(max_calls=ai.max_calls, max_bytes=ai.max_bytes)
    if not ai.enabled:
        provider = Component("ai.provider", "FAKE", "ai.enabled=false → FakeProvider (no calls)", FakeProvider())
    else:
        from .providers import OpenAICompatProvider, ProviderConfig, ProviderError
        loopback = _host_port(ai.base_url)[0] in LOOPBACK
        if not (allow_real or loopback):
            raise WiringError(f"ai.enabled=true needs --allow-real-network and {ALLOW_NETWORK_ENV}=1 (refused; nothing built)")
        _require_egress(egress, ai.base_url, "ai")
        try:
            p = OpenAICompatProvider(ai.api_key_ref or "", redactor,
                                     ProviderConfig(base_url=ai.base_url, model=ai.model, allowed_hosts=frozenset(ai.allowed_hosts),
                                                    timeout_seconds=float(ai.timeout_seconds)),
                                     env=env, opener=opener)
        except ProviderError as e:
            raise WiringError(f"ai: {e}") from None
        provider = Component("ai.provider", "REAL",
                             f"OpenAICompatProvider → {_host_port(ai.base_url)[0]} model={ai.model} (key via {ai.api_key_ref})", p)
    advisor = Component("ai.advisor", "REAL" if ai.enabled else "FAKE",
                        f"Advisor budget calls={ai.max_calls} bytes={ai.max_bytes}; advisory only, never executes",
                        Advisor(provider.obj, redactor, budget, AdvisorConfig()))
    components += [provider, advisor]
    components.append(Component("network.egress", "REAL" if egress.rules else "LOOPBACK_ONLY",
                                f"{len(egress.rules)} allowlist rule(s); loopback allowed; every decision inventoried"))
    return Wiring(redactor, egress, outbox, transport, poller, access, advisor, provider, components)
