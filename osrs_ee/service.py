"""S04c-local — the long-running Service loop (offline; FakeSupervisor/FakeAdapter only).

Composes Store + Worker + HealthMonitor + Admission + Supervisor + optional Outbox
into one supervised session per account. The loop is deterministic: the clock is
injected, nothing sleeps here, and every state change is a Store transition.

Guarantees exercised by tests/test_service.py:
- start requires READY and an admitted (fresh, in-limit) resource snapshot;
- stop → abort → drain → supervisor stop; final state is RESTING, or
  RECOVERY_REQUIRED when a command is UNKNOWN or the process gives no exit proof;
  the loop never writes READY except for a budgeted restart from RESTING;
- crash/freeze → bounded restarts (HealthMonitor budget) → CIRCUIT_OPEN;
- resource pressure on a running session → orderly stop (state first);
- alerts go through the Redactor; a message that fails redaction is never sent.
"""
from __future__ import annotations

import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Iterable, Optional

from .config import ServiceConfig
from .release import Admission, ResourceSnapshot
from .store import Store, StoreError
from .supervisor import Supervisor
from .telegram import Outbox, OutboundMessage, RedactionError
from .worker import Adapter, HealthMonitor, Worker, WorkerConfig

BOOTSTRAP_PATH = ("PENDING_DISCOVERY", "DISCOVERING", "READY")
UNTOUCHABLE = frozenset({"RECOVERY_REQUIRED", "BLOCKED", "DISABLED", "RECONCILING"})


@dataclass(frozen=True)
class ServiceEvent:
    tick: int
    kind: str
    detail: str = ""


@dataclass
class ServiceResult:
    final_state: str
    ticks: int
    stop_reason: Optional[str]
    events: list[ServiceEvent] = field(default_factory=list)
    restarts: int = 0

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]


def bootstrap_account(store: Store, cfg: ServiceConfig, now: datetime) -> str:
    """Create the configured account if absent and walk NEW→…→READY.

    Idempotent. Never touches RECOVERY_REQUIRED/BLOCKED/DISABLED/RECONCILING
    accounts: those need the owner (RECON path), not a restart.
    """
    a = cfg.account
    try:
        acc = store.get_account(a.account_id)
    except StoreError:
        acc = store.create_account(a.account_id, a.alias, a.auth_mode, a.credential_ref, now=now)
    if acc.state in UNTOUCHABLE or acc.state == "READY":
        return acc.state
    if acc.state == "RESTING":
        acc = store.transition(a.account_id, "READY", expected_version=acc.state_version, reason="service.bootstrap", now=now)
        return acc.state
    if acc.state != "NEW" and acc.state not in BOOTSTRAP_PATH:
        return acc.state  # LEASED/STARTING/RUNNING/DRAINING: a live session exists; never reset it here
    start = BOOTSTRAP_PATH.index(acc.state) + 1 if acc.state in BOOTSTRAP_PATH else 0  # NEW -> 0
    for state in BOOTSTRAP_PATH[start:]:
        acc = store.transition(a.account_id, state, expected_version=acc.state_version, reason="service.bootstrap", now=now)
    return acc.state


class Service:
    """One account, one supervised session at a time. ``clock`` is injected."""

    def __init__(self, store: Store, cfg: ServiceConfig, adapter: Adapter, supervisor: Supervisor,
                 outbox: Optional[Outbox] = None, *, clock: Callable[[], datetime], intents: Iterable[dict] = (),
                 session_id: str = "sess_service", client_instance_id: str = "client_service01",
                 lease_ttl_seconds: int = 3600, alert_chat_id: int = 0) -> None:
        self.store, self.cfg, self.adapter, self.sup, self.outbox = store, cfg, adapter, supervisor, outbox
        self.clock = clock
        self.session_id, self.client_instance_id = session_id, client_instance_id
        self.lease_ttl_seconds, self.alert_chat_id = lease_ttl_seconds, alert_chat_id
        self.account_id = cfg.account.account_id
        self.admission = Admission(cfg.resources.rss_limit_bytes, cfg.resources.disk_reserve_bytes, cfg.resources.fd_limit,
                                   cfg.resources.cpu_limit_percent, cfg.resources.snapshot_max_age_seconds)
        self.health = HealthMonitor(cfg.health.freeze_after_seconds, cfg.health.restart_budget, cfg.health.restart_window_seconds)
        self.worker_config = WorkerConfig(cfg.config_hash, cfg.policy_version, cfg.worker.observation_max_age_seconds,
                                          cfg.worker.dispatch_timeout_seconds, cfg.worker.max_queue)
        self.worker: Optional[Worker] = None
        self.pending_intents: list[dict] = list(intents)
        self.events: list[ServiceEvent] = []
        self.ticks = 0
        self.restarts = 0
        self.stop_reason: Optional[str] = None
        self._circuit_open = False

    # ---- control -----------------------------------------------------------
    def request_stop(self, reason: str = "operator.stop") -> None:
        if self.stop_reason is None:
            self.stop_reason = reason

    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda s, _f: self.request_stop(f"signal.{s}"))

    # ---- events / alerts ---------------------------------------------------
    def _emit(self, kind: str, detail: str = "", *, alert: bool = False) -> None:
        self.events.append(ServiceEvent(self.ticks, kind, detail))
        if alert and self.outbox is not None:
            try:
                text = self.outbox.redactor.render("[{kind}] {acc}: {detail}", kind=kind, acc=self.account_id, detail=detail)
            except RedactionError as e:
                self.events.append(ServiceEvent(self.ticks, "alert.redaction_refused", str(e)))
                return
            self.outbox.enqueue(OutboundMessage(self.alert_chat_id, text, "ALERT", dedupe_key=f"{kind}:{self.ticks}"))

    def _snapshot(self, now: datetime) -> Optional[ResourceSnapshot]:
        m = self.sup.measure(now)
        if m is None:
            return None
        return ResourceSnapshot(m["rss_bytes"], m["disk_free_bytes"], m["open_fds"], m["cpu_percent"], now)

    # ---- session lifecycle -------------------------------------------------
    def _start_session(self, now: datetime) -> bool:
        acc = self.store.get_account(self.account_id)
        if acc.state != "READY":
            self._emit("start.refused", f"state {acc.state} is not READY")
            return False
        snap = self._snapshot(now)
        if snap is None:
            self._emit("start.refused", "no resource measurement")
            return False
        decision = self.admission.decide(snap, running_sessions=0, now=now)
        if not decision.allowed:
            self._emit("start.denied", f"{decision.reason_code}: {decision.detail}", alert=True)
            return False
        epoch = acc.session_epoch + 1
        # lease_id and session_id are unique per epoch (leases.session_id is UNIQUE in the Store).
        self.store.acquire_lease(self.account_id, lease_id=f"lease_service{epoch:03d}", session_id=f"{self.session_id}_{epoch:03d}",
                                 client_instance_id=self.client_instance_id, expected_version=acc.state_version,
                                 ttl_seconds=self.lease_ttl_seconds, now=now)
        self.sup.start(now)
        self.worker = Worker(self.store, self.adapter, self.account_id, self.worker_config, health=self.health)
        self.worker.start(now=now)
        for intent in self.pending_intents:
            self.worker.enqueue(intent)
        self.pending_intents = []
        self._emit("session.started", f"epoch {epoch}")
        return True

    def _settle(self, now: datetime, reason: str) -> str:
        """abort → drain → supervisor stop. RESTING only with exit proof and no UNKNOWN."""
        assert self.worker is not None
        self.worker.request_abort()
        state = self.worker.drain(now=now, reason=reason)
        self.sup.stop(now)
        if not self.sup.exited(now):
            self._emit("supervisor.no_exit_proof", "process did not exit on stop", alert=True)
            if state == "RESTING":
                acc = self.store.get_account(self.account_id)
                state = self.store.transition(self.account_id, "RECOVERY_REQUIRED", expected_version=acc.state_version,
                                              reason="supervisor.no_exit_proof", now=now).state
        self.worker = None
        self._emit("session.settled", f"{reason} -> {state}", alert=(state != "RESTING"))
        return state

    def _try_restart(self, now: datetime, cause: str) -> bool:
        acc = self.store.get_account(self.account_id)
        if acc.state != "RESTING":
            self._emit("restart.refused", f"state {acc.state}; owner reconciliation required", alert=True)
            return False
        if not self.health.allow_restart(now):
            self._circuit_open = True
            self._emit("CIRCUIT_OPEN", f"restart budget exhausted after {cause}", alert=True)
            return False
        self.store.transition(self.account_id, "READY", expected_version=acc.state_version, reason="service.restart", now=now)
        self.restarts += 1
        self._emit("restart", cause)
        return True

    # ---- loop ----------------------------------------------------------------
    def run_once(self) -> bool:
        """One tick. Returns False when the loop should end."""
        now = self.clock()
        self.ticks += 1
        if self._circuit_open:
            return False
        if self.worker is None:
            if self.stop_reason is not None:
                return False
            if not self._start_session(now):
                return False
            return True
        # running session
        if self.stop_reason is not None:
            self._settle(now, self.stop_reason)
            return False
        tick = self.sup.tick(now)
        self.health.observe_tick(tick, self.sup.position(now), now)
        if self.sup.exited(now):
            self._emit("client.crashed", "process exited without stop", alert=True)
            self._settle(now, "client.crash")
            return self._try_restart(now, "crash")
        if self.health.status(now) == "FROZEN":
            self._emit("client.frozen", f"no tick for > {self.cfg.health.freeze_after_seconds}s", alert=True)
            self._settle(now, "client.freeze")
            return self._try_restart(now, "freeze")
        snap = self._snapshot(now)
        if snap is not None and self.admission.must_stop(snap):
            self._emit("resources.pressure", "disk/RSS limit reached; orderly stop", alert=True)
            self.request_stop("resources.pressure")
            self._settle(now, "resources.pressure")
            return False
        result = self.worker.step(now=now)
        if result.outcome != "IDLE":
            self._emit(f"command.{result.outcome.lower()}", f"{result.command_id} {result.phase or ''} {result.reason_code}".strip())
        if result.phase == "UNKNOWN":
            self._emit("command.unknown", str(result.command_id), alert=True)
            self._settle(now, "command.unknown")
            return False
        if self.outbox is not None:
            self.outbox.flush(now=now)
        return True

    def run(self, max_ticks: Optional[int] = None) -> ServiceResult:
        limit = max_ticks if max_ticks is not None else self.cfg.worker.max_ticks
        while True:
            if limit is not None and self.ticks >= limit:
                if self.worker is not None:
                    self.request_stop("max_ticks")
                    self._settle(self.clock(), "max_ticks")
                break
            if not self.run_once():
                break
        if self.outbox is not None:
            self.outbox.flush(now=self.clock())
        final = self.store.get_account(self.account_id).state
        return ServiceResult(final, self.ticks, self.stop_reason, list(self.events), self.restarts)
