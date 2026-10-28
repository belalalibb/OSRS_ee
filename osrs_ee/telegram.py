"""S06 — Telegram control plane, fake-first (no network).

Pure/local parts of T02/T03/T29:
* RBAC: every inbound message/callback is checked for (chat, user, role);
  default deny; roles are explicit allow-lists (FOUNDATION §: "كل message/callback
  يفحص user+chat+role، default deny").
* Approvals: a callback can only *consume* a Store approval whose bound context
  (incident, account, epoch, plan_hash, state_version) matches the live request
  and whose approver matches the Store row; single-use is enforced by the Store.
* Redaction: outbound text may only carry aliases/refs. A sink scanner rejects
  any registered canary/secret before it reaches the transport (T02).
* Outbox: bounded, deduplicated, priority-ordered (state/stop before
  notifications), bounded retries honouring retry_after (T29). Delivery is
  through a Transport protocol; `FakeTransport` is scripted. No sockets here.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Iterable, Mapping, Optional, Protocol
from collections import deque

from osrs_ee.guards import GuardDecision
from osrs_ee.store import ApprovalError, Store

__all__ = [
    "Role", "AccessPolicy", "Redactor", "RedactionError", "InboundMessage", "InboundCallback",
    "OutboundMessage", "SendResult", "Transport", "FakeTransport", "Outbox", "ControlPlane",
]

Role = str  # "OWNER" | "OPERATOR" | "VIEWER"
ROLES: frozenset[str] = frozenset({"OWNER", "OPERATOR", "VIEWER"})

# Command -> minimum role set that may issue it. Anything absent is denied.
COMMAND_ROLES: Mapping[str, frozenset[str]] = {
    "/status": frozenset({"OWNER", "OPERATOR", "VIEWER"}),
    "/stop": frozenset({"OWNER", "OPERATOR"}),
    "/approve": frozenset({"OWNER"}),
    "/disable": frozenset({"OWNER"}),
}
PRIORITY: Mapping[str, int] = {"STATE": 0, "STOP": 0, "APPROVAL": 1, "ALERT": 2, "INFO": 3}


# ------------------------------------------------------------------ RBAC
@dataclass(frozen=True)
class AccessPolicy:
    """Explicit allow-lists. chat_ids: chats where the bot may act at all.
    users: user_id -> role. A user in a non-allowed chat is denied."""
    chat_ids: frozenset[int]
    users: Mapping[int, Role]

    def __post_init__(self) -> None:
        bad = {r for r in self.users.values() if r not in ROLES}
        if bad:
            raise ValueError(f"unknown roles: {sorted(bad)}")

    def role_of(self, chat_id: int, user_id: int) -> Optional[Role]:
        if chat_id not in self.chat_ids:
            return None
        return self.users.get(user_id)

    def authorize(self, chat_id: int, user_id: int, command: str) -> GuardDecision:
        role = self.role_of(chat_id, user_id)
        if role is None:
            return GuardDecision.deny("IDENTITY_UNVERIFIED", "chat or user not allow-listed")
        allowed = COMMAND_ROLES.get(command)
        if allowed is None:
            return GuardDecision.deny("POLICY_DENIED", f"unknown command {command!r}")
        if role not in allowed:
            return GuardDecision.deny("POLICY_DENIED", f"role {role} may not {command}")
        return GuardDecision.ok()


# -------------------------------------------------------------- redaction
class RedactionError(Exception):
    """Outbound text contained a secret/canary; nothing was sent."""


_SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"), re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b[0-9]{5,10}:[A-Za-z0-9_-]{30,}\b"),   # Telegram bot token shape
    re.compile(r"(?i)(password|passwd|pin|token|secret)\s*[:=]\s*\S+"),
)


@dataclass
class Redactor:
    """Registered canaries (synthetic secrets) must never appear in any sink."""
    canaries: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(default_factory=dict)  # account_id -> alias

    def register_canary(self, value: str) -> None:
        if len(value) < 8:
            raise ValueError("canary too short to be meaningful")
        self.canaries.add(value)

    def scan(self, text: str) -> Optional[str]:
        """Return a reason if text is unsafe for a sink, else None."""
        for c in self.canaries:
            if c in text:
                return "canary present"
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                return f"secret-shaped content ({pat.pattern[:20]}...)"
        return None

    def render(self, template: str, **values: object) -> str:
        """Substitute only aliases/refs; account ids are replaced by their alias."""
        text = template.format(**values)
        for account_id, alias in self.aliases.items():
            text = text.replace(account_id, alias)
        reason = self.scan(text)
        if reason:
            raise RedactionError(reason)
        return text


# -------------------------------------------------------------- messages
@dataclass(frozen=True)
class InboundMessage:
    chat_id: int
    user_id: int
    text: str
    message_id: int


@dataclass(frozen=True)
class InboundCallback:
    chat_id: int
    user_id: int
    callback_id: str
    approval_id: str
    incident_id: str
    account_id: str
    session_epoch: int
    plan_hash: str
    state_version: int


@dataclass(frozen=True)
class OutboundMessage:
    chat_id: int
    text: str
    kind: str = "INFO"          # STATE|STOP|APPROVAL|ALERT|INFO
    dedupe_key: Optional[str] = None

    def key(self) -> str:
        if self.dedupe_key:
            return self.dedupe_key
        return hashlib.sha256(f"{self.chat_id}|{self.kind}|{self.text}".encode()).hexdigest()


@dataclass(frozen=True)
class SendResult:
    ok: bool
    retry_after_seconds: int = 0
    permanent: bool = False


class Transport(Protocol):
    def send(self, message: OutboundMessage, *, now: datetime) -> SendResult: ...


@dataclass
class FakeTransport:
    """Scripted: pop a SendResult per send; empty script = success."""
    script: Deque[SendResult] = field(default_factory=deque)
    sent: list[OutboundMessage] = field(default_factory=list)
    attempts: int = 0

    def plan(self, *results: SendResult) -> "FakeTransport":
        self.script.extend(results)
        return self

    def send(self, message: OutboundMessage, *, now: datetime) -> SendResult:
        self.attempts += 1
        r = self.script.popleft() if self.script else SendResult(True)
        if r.ok:
            self.sent.append(message)
        return r


# ----------------------------------------------------------------- outbox
@dataclass
class _Entry:
    message: OutboundMessage
    seq: int
    attempts: int = 0
    not_before: Optional[datetime] = None


class Outbox:
    """Bounded, deduplicated, priority outbox with bounded retries (T29).

    Dropping policy when full: the lowest-priority (highest PRIORITY number),
    newest entry is dropped first; STATE/STOP are never dropped for INFO.
    """

    def __init__(self, transport: Transport, redactor: Redactor, *, capacity: int = 32, max_attempts: int = 3) -> None:
        if capacity < 1 or max_attempts < 1:
            raise ValueError("capacity and max_attempts must be >= 1")
        self.transport, self.redactor = transport, redactor
        self.capacity, self.max_attempts = capacity, max_attempts
        self._entries: list[_Entry] = []
        self._seen: set[str] = set()
        self._seq = 0
        self.dropped: list[OutboundMessage] = []
        self.dead: list[OutboundMessage] = []

    def __len__(self) -> int:
        return len(self._entries)

    def enqueue(self, message: OutboundMessage) -> GuardDecision:
        if message.kind not in PRIORITY:
            return GuardDecision.deny("POLICY_DENIED", f"unknown kind {message.kind}")
        reason = self.redactor.scan(message.text)
        if reason:
            return GuardDecision.deny("POLICY_DENIED", f"redaction: {reason}")
        k = message.key()
        if k in self._seen:
            return GuardDecision.deny("POLICY_DENIED", "duplicate suppressed")
        if len(self._entries) >= self.capacity:
            victim = max(self._entries, key=lambda e: (PRIORITY[e.message.kind], e.seq))
            if PRIORITY[victim.message.kind] <= PRIORITY[message.kind]:
                self.dropped.append(message)
                return GuardDecision.deny("INSUFFICIENT_RESOURCES", "outbox full; lower/equal priority dropped")
            self._entries.remove(victim)
            self._seen.discard(victim.message.key())
            self.dropped.append(victim.message)
        self._seq += 1
        self._entries.append(_Entry(message, self._seq))
        self._seen.add(k)
        return GuardDecision.ok()

    def _ready(self, now: datetime) -> list[_Entry]:
        ready = [e for e in self._entries if e.not_before is None or e.not_before <= now]
        return sorted(ready, key=lambda e: (PRIORITY[e.message.kind], e.seq))

    def flush(self, *, now: datetime, budget: int = 8) -> int:
        """Attempt up to `budget` sends; returns the number delivered."""
        if budget < 1:
            raise ValueError("budget must be >= 1")
        delivered = 0
        for e in self._ready(now)[:budget]:
            e.attempts += 1
            r = self.transport.send(e.message, now=now)
            if r.ok:
                self._entries.remove(e)
                delivered += 1
                continue
            if r.permanent or e.attempts >= self.max_attempts:
                self._entries.remove(e)
                self.dead.append(e.message)
                continue
            backoff = max(r.retry_after_seconds, 2 ** e.attempts)
            e.not_before = now + timedelta(seconds=backoff)
        return delivered

    def pending(self) -> list[OutboundMessage]:
        return [e.message for e in sorted(self._entries, key=lambda e: (PRIORITY[e.message.kind], e.seq))]


# ---------------------------------------------------------- control plane
@dataclass(frozen=True)
class Handled:
    accepted: bool
    action: str          # STATUS|STOP|APPROVE|DISABLE|DENIED
    reason_code: str = "NONE"
    detail: str = ""


class ControlPlane:
    """Turns authorized inbound traffic into *requests*; executes nothing on the game.

    on_stop/on_disable are callbacks owned by the supervisor layer; the control
    plane only verifies authority and context, then delegates. Approvals are
    consumed in the Store (single-use, context-bound)."""

    def __init__(self, store: Store, policy: AccessPolicy, outbox: Outbox, redactor: Redactor, *,
                 approver_refs: Mapping[int, str], on_stop=None, on_disable=None) -> None:
        self.store, self.policy, self.outbox, self.redactor = store, policy, outbox, redactor
        self.approver_refs = dict(approver_refs)  # user_id -> "ref:tg:<alias>"
        self.on_stop, self.on_disable = on_stop, on_disable
        self._seen_callbacks: set[str] = set()
        self.audit: list[tuple[str, int, int, str, str]] = []  # (kind, chat, user, action, reason)

    def _log(self, kind: str, chat: int, user: int, action: str, reason: str) -> None:
        self.audit.append((kind, chat, user, action, reason))

    def handle_message(self, msg: InboundMessage, *, now: datetime) -> Handled:
        command = msg.text.split()[0] if msg.text.strip() else ""
        d = self.policy.authorize(msg.chat_id, msg.user_id, command)
        if not d.allowed:
            self._log("message", msg.chat_id, msg.user_id, "DENIED", d.reason_code)
            return Handled(False, "DENIED", d.reason_code, d.detail)
        if command == "/status":
            self._log("message", msg.chat_id, msg.user_id, "STATUS", "NONE")
            return Handled(True, "STATUS")
        if command == "/stop":
            if self.on_stop is not None:
                self.on_stop(now=now)
            self.outbox.enqueue(OutboundMessage(msg.chat_id, "stop requested", "STOP", dedupe_key=f"stop:{msg.message_id}"))
            self._log("message", msg.chat_id, msg.user_id, "STOP", "NONE")
            return Handled(True, "STOP")
        if command == "/disable":
            if self.on_disable is not None:
                self.on_disable(now=now)
            self._log("message", msg.chat_id, msg.user_id, "DISABLE", "NONE")
            return Handled(True, "DISABLE")
        # /approve by text is refused: approvals go through bound callbacks only.
        self._log("message", msg.chat_id, msg.user_id, "DENIED", "POLICY_DENIED")
        return Handled(False, "DENIED", "POLICY_DENIED", "approvals require a bound callback")

    def handle_callback(self, cb: InboundCallback, *, now: datetime) -> Handled:
        d = self.policy.authorize(cb.chat_id, cb.user_id, "/approve")
        if not d.allowed:
            self._log("callback", cb.chat_id, cb.user_id, "DENIED", d.reason_code)
            return Handled(False, "DENIED", d.reason_code, d.detail)
        if cb.callback_id in self._seen_callbacks:
            self._log("callback", cb.chat_id, cb.user_id, "DENIED", "STALE_CONTEXT")
            return Handled(False, "DENIED", "STALE_CONTEXT", "callback replay")
        self._seen_callbacks.add(cb.callback_id)
        approver = self.approver_refs.get(cb.user_id)
        if approver is None:
            self._log("callback", cb.chat_id, cb.user_id, "DENIED", "IDENTITY_UNVERIFIED")
            return Handled(False, "DENIED", "IDENTITY_UNVERIFIED", "no approver ref for user")
        row = self.store.get_approval(cb.approval_id)
        if row is None or row.approver_ref != approver:
            self._log("callback", cb.chat_id, cb.user_id, "DENIED", "IDENTITY_UNVERIFIED")
            return Handled(False, "DENIED", "IDENTITY_UNVERIFIED", "approval not issued to this approver")
        try:
            self.store.consume_approval(cb.approval_id, incident_id=cb.incident_id, account_id=cb.account_id,
                                        session_epoch=cb.session_epoch, plan_hash=cb.plan_hash,
                                        state_version=cb.state_version, now=now)
        except ApprovalError as e:
            self._log("callback", cb.chat_id, cb.user_id, "DENIED", "STALE_CONTEXT")
            return Handled(False, "DENIED", "STALE_CONTEXT", str(e))
        self._log("callback", cb.chat_id, cb.user_id, "APPROVE", "NONE")
        return Handled(True, "APPROVE")
