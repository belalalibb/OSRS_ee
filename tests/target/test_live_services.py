"""T02/T03 (Telegram) and T35 (AI provider) — LIVE, ready to run, never run here.

Owner preconditions: OSRS_EE_ALLOW_NETWORK=1 plus the secret in the env var
named by the ref (Telegram: OSRS_EE_TG_TOKEN + OSRS_EE_TG_CHAT_ID; AI:
OSRS_EE_AI_KEY). Each test does ONE bounded call and asserts transport-level
behaviour only. Secrets are resolved by the transport from ``ref:env:...``;
the tests never read them.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from osrs_ee.telegram import OutboundMessage, Redactor

pytestmark = pytest.mark.live


def _need(name):
    if not os.environ.get(name):
        pytest.skip(f"{name} not set (owner-provided; NOT_RUN here)")


def test_T02_telegram_send_one_message(allow_network_sockets):
    _need("OSRS_EE_TG_TOKEN"); _need("OSRS_EE_TG_CHAT_ID")
    from osrs_ee.transports import TelegramHttpTransport, TransportConfig
    t = TelegramHttpTransport("ref:env:OSRS_EE_TG_TOKEN", Redactor(), TransportConfig())
    res = t.send(OutboundMessage(int(os.environ["OSRS_EE_TG_CHAT_ID"]), "osrs-ee live check: transport OK (no account, no game)"),
                 now=datetime.now(timezone.utc))
    assert res.ok, t.last_error


def test_T03_telegram_poll_parses_updates(allow_network_sockets):
    _need("OSRS_EE_TG_TOKEN")
    from osrs_ee.transports import TelegramHttpTransport, TelegramPoller, TransportConfig
    t = TelegramHttpTransport("ref:env:OSRS_EE_TG_TOKEN", Redactor(), TransportConfig())
    res = TelegramPoller(t, poll_timeout_seconds=1).poll(now=datetime.now(timezone.utc))
    assert res is not None


def test_T35_ai_provider_one_bounded_completion(allow_network_sockets):
    _need("OSRS_EE_AI_KEY")
    from osrs_ee.providers import OpenAICompatProvider, ProviderConfig
    base = os.environ.get("OSRS_EE_AI_BASE_URL", "https://api.openai.com")
    host = base.split("://")[1].split("/")[0]
    p = OpenAICompatProvider("ref:env:OSRS_EE_AI_KEY", Redactor(),
                             ProviderConfig(base_url=base, model=os.environ.get("OSRS_EE_AI_MODEL", "gpt-4o-mini"),
                                            allowed_hosts=frozenset({host}), timeout_seconds=20.0, max_tokens=32))
    now = datetime.now(timezone.utc)
    text = p.complete(b'{"ping": true}', deadline=now + timedelta(seconds=20), now=now)
    assert isinstance(text, str) and text
