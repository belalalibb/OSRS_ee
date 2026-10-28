"""S06b-local — ``getUpdates`` polling → ``InboundMessage`` / ``InboundCallback``.

Every update is parsed strictly; anything malformed is dropped (counted, never
raised). The poller performs **no authorization itself**: it hands typed inbound
objects to ``ControlPlane`` which applies ``AccessPolicy`` (default deny) per
chat+user. Offsets are acknowledged only after the batch was handed over.

Callback payloads are the JSON ``callback_data`` the approval prompt attached:
``{"a": approval_id, "i": incident_id, "acc": account_id, "e": epoch, "p": plan_hash, "v": state_version}``.
An approval cannot be issued by text, only by such a bound callback (ControlPlane rule).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from osrs_ee.telegram import InboundCallback, InboundMessage

from .telegram_http import TelegramHttpTransport

MAX_TEXT_CHARS = 512
MAX_UPDATES = 100


@dataclass
class PollResult:
    messages: list[InboundMessage] = field(default_factory=list)
    callbacks: list[InboundCallback] = field(default_factory=list)
    dropped: int = 0
    http_status: int = 0
    next_offset: Optional[int] = None


def _int(v) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def parse_update(update: dict) -> tuple[Optional[InboundMessage], Optional[InboundCallback]]:
    """Strict parse of one Telegram update. Returns (message, callback) with at most one set."""
    if not isinstance(update, dict) or _int(update.get("update_id")) is None:
        return None, None
    msg = update.get("message")
    if isinstance(msg, dict):
        chat, user = msg.get("chat"), msg.get("from")
        text, mid = msg.get("text"), _int(msg.get("message_id"))
        if not (isinstance(chat, dict) and isinstance(user, dict) and isinstance(text, str) and mid is not None):
            return None, None
        cid, uid = _int(chat.get("id")), _int(user.get("id"))
        if cid is None or uid is None or user.get("is_bot") is True:
            return None, None
        return InboundMessage(cid, uid, text[:MAX_TEXT_CHARS], mid), None
    cq = update.get("callback_query")
    if isinstance(cq, dict):
        user, data, cb_id = cq.get("from"), cq.get("data"), cq.get("id")
        origin = cq.get("message")
        if not (isinstance(user, dict) and isinstance(data, str) and isinstance(cb_id, str) and isinstance(origin, dict)):
            return None, None
        chat = origin.get("chat")
        cid, uid = (_int(chat.get("id")) if isinstance(chat, dict) else None), _int(user.get("id"))
        if cid is None or uid is None or user.get("is_bot") is True:
            return None, None
        try:
            p = json.loads(data)
        except ValueError:
            return None, None
        if not isinstance(p, dict) or set(p) != {"a", "i", "acc", "e", "p", "v"}:
            return None, None
        if not all(isinstance(p[k], str) and p[k] for k in ("a", "i", "acc", "p")):
            return None, None
        if _int(p["e"]) is None or _int(p["v"]) is None:
            return None, None
        return None, InboundCallback(cid, uid, cb_id, p["a"], p["i"], p["acc"], p["e"], p["p"], p["v"])
    return None, None


class TelegramPoller:
    """Long-poll wrapper around the transport's ``call``; bounded per poll."""

    def __init__(self, transport: TelegramHttpTransport, *, poll_timeout_seconds: int = 0, limit: int = MAX_UPDATES) -> None:
        if not (0 <= poll_timeout_seconds <= 50) or not (1 <= limit <= MAX_UPDATES):
            raise ValueError("poll_timeout_seconds in [0, 50]; limit in [1, 100]")
        self.transport, self.poll_timeout_seconds, self.limit = transport, poll_timeout_seconds, limit
        self.offset: Optional[int] = None
        self.polls = 0

    def poll(self, *, now: datetime) -> PollResult:
        self.polls += 1
        payload: dict = {"limit": self.limit, "timeout": self.poll_timeout_seconds,
                         "allowed_updates": ["message", "callback_query"]}
        if self.offset is not None:
            payload["offset"] = self.offset
        status, body = self.transport.call("getUpdates", payload)
        res = PollResult(http_status=status)
        if status != 200 or body.get("ok") is not True or not isinstance(body.get("result"), list):
            return res
        for upd in body["result"][: self.limit]:
            uid = _int(upd.get("update_id")) if isinstance(upd, dict) else None
            if uid is not None:
                res.next_offset = max(res.next_offset or 0, uid + 1)
            m, c = parse_update(upd)
            if m is not None:
                res.messages.append(m)
            elif c is not None:
                res.callbacks.append(c)
            else:
                res.dropped += 1
        if res.next_offset is not None:
            self.offset = res.next_offset  # acknowledge only what we handed over
        return res
