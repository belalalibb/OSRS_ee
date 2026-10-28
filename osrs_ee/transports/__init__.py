"""Real transports (S06b-local). Network-capable code lives ONLY here and in
``osrs_ee/providers``; everything else in the package is socket-free.

Both modules use stdlib ``urllib`` with an explicit allowlisted base URL, bounded
timeouts and no secrets in code: the bot token is resolved from an environment
variable named by a ``ref:env:<NAME>`` reference. Tests run against a local fake
HTTP server on 127.0.0.1 only; nothing here has been exercised against api.telegram.org.
"""
from .telegram_http import TelegramHttpTransport, TransportConfig, TransportError, resolve_secret_ref
from .telegram_poll import TelegramPoller, PollResult

__all__ = ["TelegramHttpTransport", "TransportConfig", "TransportError", "resolve_secret_ref",
           "TelegramPoller", "PollResult"]
