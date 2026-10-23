"""S03 — single-owner worker/scheduler over the Store, with a fake adapter.

Scope (pure/local parts of T16/T17/T21/T29):
* concurrency = 1: one worker, one account, one in-flight command at a time.
* Store is the only commit point (T21). The worker never writes state except
  through Store methods; the scheduler only decides *what to try next*.
* Every dispatch is preceded by a durable PREPARED journal row and a guard
  pass; a guard denial becomes a NOT_SENT event (T29: no dispatch without intent).
* After mark_dispatching, *any* failure is UNKNOWN (never NOT_SENT) (T16).
* Abort: no new dispatches; in-flight is never recalled; drain ends in
  RESTING only if nothing is UNKNOWN, else RECOVERY_REQUIRED (T16).
* Health: liveness ticks independent of movement (stationary != frozen);
  restart budget / circuit breaker bounds restart storms (T17).
* Budgets: bounded queue; no automatic retry of non-idempotent operations (T29).

No game I/O, no sockets, no threads, no sleeps: time is injected.
"""
from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Deque, Optional, Protocol

from osrs_ee import guards
from osrs_ee.guards import GuardDecision, SessionContext, parse_utc
from osrs_ee.store import LeaseConflict, Store, StoreError

__all__ = [
    "AdapterResponse", "Adapter", "FakeAdapter", "HealthMonitor", "WorkerConfig",
    "StepResult", "Worker", "AdapterFailure",
]

SAFE_OPERATIONS = frozenset({"NOOP", "OBSERVE"})  # idempotent, allowed while reconciling


class AdapterFailure(Exception):
    """Raised by an adapter when the transport broke after dispatch began."""


@dataclass(frozen=True)
class AdapterResponse:
    transport_status: str            # ACKNOWLEDGED | REJECTED | TIMEOUT | CONNECTION_LOST
    effect_status: str               # UNKNOWN | VERIFIED | FAILED_VERIFIED | NOT_ATTEMPTED
    evidence_refs: tuple[str, ...] = ()
    reason_code: str = "NONE"


class Adapter(Protocol):
    def observe(self, now: datetime) -> dict: ...
    def dispatch(self, intent: dict, *, deadline: datetime, now: datetime) -> Optional[AdapterResponse]: ...


@dataclass
class FakeAdapter:
    """Scripted adapter. `responses` are consumed in order; None = no reply by
    deadline (timeout); an Exception instance = transport failure mid-flight."""
    observation: dict
    responses: Deque[object] = field(default_factory=deque)
    dispatched: list[dict] = field(default_factory=list)
    observe_calls: int = 0

    def script(self, *items: object) -> "FakeAdapter":
        self.responses.extend(items)
        return self

    def observe(self, now: datetime) -> dict:
        self.observe_calls += 1
        return self.observation

    def dispatch(self, intent: dict, *, deadline: datetime, now: datetime) -> Optional[AdapterResponse]:
        self.dispatched.append(intent)
        if not self.responses:
            return None
        item = self.responses.popleft()
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


# ------------------------------------------------------------------ health
@dataclass
class HealthMonitor:
    """Liveness from client ticks, not from movement. Restart budget = circuit breaker."""
    freeze_after_seconds: int
    restart_budget: int
    restart_window_seconds: int
    last_tick: Optional[int] = None
    last_tick_at: Optional[datetime] = None
    last_position: Optional[tuple] = None
    stationary_since: Optional[datetime] = None
    restarts: list[datetime] = field(default_factory=list)
    circuit_open: bool = False

    def __post_init__(self) -> None:
        if self.freeze_after_seconds < 1 or self.restart_budget < 0 or self.restart_window_seconds < 1:
            raise ValueError("invalid health parameters")

    def observe_tick(self, tick: Optional[int], position: Optional[tuple], now: datetime) -> None:
        if tick is not None and (self.last_tick is None or tick > self.last_tick):
            self.last_tick, self.last_tick_at = tick, now
        if position != self.last_position:
            self.last_position, self.stationary_since = position, None
        elif self.stationary_since is None:
            self.stationary_since = now

    def status(self, now: datetime) -> str:
        """OK | FROZEN | UNKNOWN. Stationary player with live ticks is OK."""
        if self.last_tick_at is None:
            return "UNKNOWN"
        if (now - self.last_tick_at).total_seconds() > self.freeze_after_seconds:
            return "FROZEN"
        return "OK"

    def allow_restart(self, now: datetime) -> bool:
        """Consume one restart from the window budget; open the circuit when exhausted."""
        if self.circuit_open:
            return False
        window = now - timedelta(seconds=self.restart_window_seconds)
        self.restarts = [t for t in self.restarts if t > window]
        if len(self.restarts) >= self.restart_budget:
            self.circuit_open = True
            return False
        self.restarts.append(now)
        return True


# ------------------------------------------------------------------ worker
@dataclass(frozen=True)
class WorkerConfig:
    config_hash: str
    policy_version: int
    observation_max_age_seconds: int = 10
    dispatch_timeout_seconds: int = 30
    max_queue: int = 16


@dataclass(frozen=True)
class StepResult:
    command_id: Optional[str]
    outcome: str          # IDLE | DISPATCHED | DENIED | DROPPED | ABORTED
    phase: Optional[str]  # journal phase after the step, if journaled
    reason_code: str = "NONE"
    detail: str = ""


class Worker:
    """One account, one lease, one in-flight command. Clock is injected per call."""

    def __init__(self, store: Store, adapter: Adapter, account_id: str, config: WorkerConfig,
                 health: Optional[HealthMonitor] = None) -> None:
        self.store, self.adapter, self.account_id, self.config = store, adapter, account_id, config
        self.health = health or HealthMonitor(freeze_after_seconds=15, restart_budget=3, restart_window_seconds=600)
        self._queue: Deque[dict] = deque()
        self._abort_requested = False
        self._seq = 0

    # ---- context ---------------------------------------------------------
    def context(self) -> SessionContext:
        acc = self.store.get_account(self.account_id)
        lease = self.store.active_lease(self.account_id)
        if lease is None:
            raise LeaseConflict(f"{self.account_id}: no active lease")
        return SessionContext(
            account_id=acc.account_id, session_id=lease.session_id, client_instance_id=lease.client_instance_id,
            session_epoch=lease.session_epoch, lease_id=lease.lease_id, lease_expires_at=parse_utc(lease.expires_at),
            state_version=acc.state_version, config_hash=self.config.config_hash, policy_version=self.config.policy_version,
            abort_requested=self._abort_requested, unknown_commands_pending=self.store.unknown_pending(self.account_id))

    def start(self, *, now: datetime) -> SessionContext:
        """LEASED -> STARTING -> RUNNING (two CAS transitions through the Store)."""
        acc = self.store.get_account(self.account_id)
        acc = self.store.transition(self.account_id, "STARTING", expected_version=acc.state_version, reason="worker.start", now=now)
        self.store.transition(self.account_id, "RUNNING", expected_version=acc.state_version, reason="worker.start", now=now)
        return self.context()

    # ---- scheduling ------------------------------------------------------
    @property
    def queued(self) -> int:
        return len(self._queue)

    @property
    def abort_requested(self) -> bool:
        return self._abort_requested

    def enqueue(self, intent: dict) -> GuardDecision:
        """Bounded queue (T29). Rejections are decisions, not exceptions."""
        if self._abort_requested:
            return GuardDecision.deny("POLICY_DENIED", "abort requested; queue closed")
        if len(self._queue) >= self.config.max_queue:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "queue full")
        self._queue.append(intent)
        return GuardDecision.ok()

    def replan(self, reason: str) -> int:
        """Drop every queued (not yet journaled) intent; the planner must re-derive from the Store (T21)."""
        n = len(self._queue)
        self._queue.clear()
        return n

    def request_abort(self) -> None:
        self._abort_requested = True

    # ---- the single step -------------------------------------------------
    def step(self, *, now: datetime) -> StepResult:
        if not self._queue:
            return StepResult(None, "IDLE", None)
        intent = self._queue.popleft()
        cid = intent.get("command_id")
        # 1) durable PREPARED row before any evaluation that could lead to dispatch
        try:
            row, _created = self.store.prepare_command(intent, now=now)
        except LeaseConflict as e:
            return StepResult(cid, "DROPPED", None, "STALE_CONTEXT", str(e))
        except StoreError as e:
            return StepResult(cid, "DROPPED", None, "POLICY_DENIED", str(e))
        if row.phase != "PREPARED":
            return StepResult(cid, "DROPPED", row.phase, "POLICY_DENIED", "command already journaled past PREPARED")
        # 2) guards (deny-by-default) against the live context
        ctx = self.context()
        decision = guards.check_command_context(intent, ctx, now)
        if decision.allowed:
            observation = self.adapter.observe(now)
            decision = guards.check_observation_freshness(intent, observation, ctx, self.config.observation_max_age_seconds, now)
        if not decision.allowed:
            # The NOT_SENT ResultEvent is the single terminal write (PREPARED -> NOT_SENT via the journal).
            self._record(intent, ctx, now, "NOT_SENT", "NOT_ATTEMPTED", decision.reason_code)
            return StepResult(cid, "ABORTED" if self._abort_requested else "DENIED", "NOT_SENT", decision.reason_code, decision.detail)
        # 3) dispatch: DISPATCHING is durable strictly before the adapter call
        self.store.mark_dispatching(cid, now=now)
        deadline = min(parse_utc(intent["expires_at"]), now + timedelta(seconds=self.config.dispatch_timeout_seconds))
        try:
            resp = self.adapter.dispatch(intent, deadline=deadline, now=now)
        except Exception as e:  # noqa: BLE001 - any failure after dispatch began is UNKNOWN, never NOT_SENT
            self._record(intent, ctx, now, "CONNECTION_LOST", "UNKNOWN", "NONE")
            return StepResult(cid, "DISPATCHED", "UNKNOWN", "NONE", f"adapter failure: {e}")
        if resp is None:
            self._record(intent, ctx, now, "TIMEOUT", "UNKNOWN", "DEADLINE_EXCEEDED")
            return StepResult(cid, "DISPATCHED", "UNKNOWN", "DEADLINE_EXCEEDED", "no reply by deadline")
        self._record(intent, ctx, now, resp.transport_status, resp.effect_status, resp.reason_code, resp.evidence_refs)
        return StepResult(cid, "DISPATCHED", self.store.get_command(cid).phase, resp.reason_code)

    def _record(self, intent: dict, ctx: SessionContext, now: datetime, transport: str, effect: str,
                reason: str, evidence: tuple[str, ...] = ()) -> None:
        self._seq += 1
        digest = hashlib.sha256(f"{intent['command_id']}:{self._seq}:{transport}:{effect}".encode()).hexdigest()[:24]
        event = {
            "schema_version": "1.0", "event_id": f"evt_{digest}", "command_id": intent["command_id"],
            "session_id": intent["session_id"], "session_epoch": intent["session_epoch"], "state_version": ctx.state_version,
            "transport_status": transport, "effect_status": effect, "reason_code": reason,
            "evidence_refs": list(evidence), "occurred_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.store.record_event(event, now=now)

    # ---- abort / drain (T16) --------------------------------------------
    def drain(self, *, now: datetime, reason: str = "worker.drain") -> str:
        """After abort: release the lease and settle the account.

        Returns the final state: RESTING when no command is UNKNOWN/in-flight,
        otherwise RECOVERY_REQUIRED. Never READY. Queued intents are dropped
        (they were never journaled, so nothing is lost or hidden).
        """
        if not self._abort_requested:
            raise StoreError("drain() requires request_abort() first")
        self._queue.clear()
        acc = self.store.get_account(self.account_id)
        lease = self.store.active_lease(self.account_id)
        pending = self.store.unknown_pending(self.account_id)
        if acc.state == "RUNNING":
            acc = self.store.transition(self.account_id, "DRAINING", expected_version=acc.state_version, reason=reason, now=now)
        if lease is not None:
            self.store.release_lease(lease.lease_id, session_epoch=lease.session_epoch, reason=reason, now=now)
        target = "RECOVERY_REQUIRED" if pending > 0 else ("RESTING" if acc.state == "DRAINING" else "RECOVERY_REQUIRED")
        if acc.state not in ("DISABLED", target):
            acc = self.store.transition(self.account_id, target, expected_version=acc.state_version, reason=reason, now=now)
        return acc.state
