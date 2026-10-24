"""S06b-local — Telegram Bot API ``Transport`` over stdlib ``urllib``.

Safety properties (all tested against a local fake server, never the real API):
- the token is never in code/config/logs: ``bot_token_ref = "ref:env:NAME"`` → ``os.environ[NAME]``;
  the token is registered as a Redactor canary so it can never be rendered into any sink;
- base URL must be in the explicit allowlist (default: api.telegram.org, or a 127.0.0.1 test server);
- every request has a bounded timeout; 429 honours ``retry_after``; 5xx = retry; 4xx = permanent;
- error text from the server is truncated and scanned before it is kept.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from osrs_ee.telegram import OutboundMessage, Redactor, SendResult

DEFAULT_ALLOWED_HOSTS = frozenset({"api.telegram.org"})


class TransportError(Exception):
    """Configuration refused; nothing was sent."""


def resolve_secret_ref(ref: Optional[str], *, env=os.environ) -> str:
    """``ref:env:NAME`` → value of the environment variable. Any other shape is refused.

    The *value* is never logged; callers must register it as a canary.
    """
    if not isinstance(ref, str) or not ref.startswith("ref:env:"):
        raise TransportError("secret reference must be 'ref:env:<VARIABLE>' (never the secret itself)")
    name = ref[len("ref:env:"):]
    if not name or not name.replace("_", "").isalnum():
        raise TransportError("invalid environment variable name in secret reference")
    value = env.get(name)
    if not value or len(value) < 8:
        raise TransportError(f"environment variable {name} is unset or too short; refusing to start")
    return value


@dataclass(frozen=True)
class TransportConfig:
    base_url: str = "https://api.telegram.org"
    timeout_seconds: float = 10.0
    allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_HOSTS
    max_error_chars: int = 200

    def __post_init__(self) -> None:
        u = urllib.parse.urlsplit(self.base_url)
        if u.scheme not in ("https", "http") or not u.hostname:
            raise TransportError("base_url must be an absolute http(s) URL")
        if u.scheme == "http" and u.hostname not in ("127.0.0.1", "localhost"):
            raise TransportError("plain http is only allowed for loopback test servers")
        if u.hostname not in self.allowed_hosts:
            raise TransportError(f"host {u.hostname} is not in the transport allowlist")
        if not (0.5 <= self.timeout_seconds <= 60):
            raise TransportError("timeout_seconds must be in [0.5, 60]")


class TelegramHttpTransport:
    """Implements ``osrs_ee.telegram.Transport``; one bounded POST per send()."""

    def __init__(self, token_ref: str, redactor: Redactor, config: TransportConfig = TransportConfig(), *,
                 env=os.environ, opener: Optional[urllib.request.OpenerDirector] = None) -> None:
        self._token = resolve_secret_ref(token_ref, env=env)
        redactor.register_canary(self._token)
        self.redactor, self.config = redactor, config
        self._opener = opener or urllib.request.build_opener()
        self.requests = 0
        self.last_error: Optional[str] = None

    def _url(self, method: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/bot{self._token}/{method}"

    def _safe_text(self, raw: bytes) -> str:
        text = raw[: self.config.max_error_chars * 4].decode("utf-8", "replace")[: self.config.max_error_chars]
        text = text.replace(self._token, "<token>")
        return text if self.redactor.scan(text) is None else "<redacted>"

    def call(self, method: str, payload: dict) -> tuple[int, dict]:
        """POST JSON; returns (http_status, parsed_body_or_{}). Never raises for HTTP errors."""
        self.requests += 1
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url(method), data=data, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "osrs-ee/0 (S06b-local)"})
        try:
            with self._opener.open(req, timeout=self.config.timeout_seconds) as resp:
                status, body = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            self.last_error = f"network: {type(e).__name__}"
            return 0, {}
        try:
            parsed = json.loads(body.decode("utf-8")) if body else {}
            if not isinstance(parsed, dict):
                parsed = {}
        except (ValueError, UnicodeDecodeError):
            parsed = {}
        if status != 200:
            self.last_error = f"http {status}: {self._safe_text(body)}"
        return status, parsed

    def send(self, message: OutboundMessage, *, now: datetime) -> SendResult:
        # Fail-closed: the Outbox already scanned, but the transport is the last line.
        if self.redactor.scan(message.text) is not None:
            return SendResult(False, permanent=True)
        status, body = self.call("sendMessage", {"chat_id": message.chat_id, "text": message.text,
                                                 "disable_web_page_preview": True})
        if status == 200 and body.get("ok") is True:
            return SendResult(True)
        if status == 429:
            retry = body.get("parameters", {}).get("retry_after", 0) if isinstance(body.get("parameters"), dict) else 0
            return SendResult(False, retry_after_seconds=int(retry) if isinstance(retry, (int, float)) else 0)
        if status == 0 or status >= 500:
            return SendResult(False)                 # transient; Outbox backs off and retries
        return SendResult(False, permanent=True)     # 4xx, or 200 with ok=false: do not retry
