"""S04c-local — client process supervision boundary.

``Supervisor`` is the *only* place where a client process would be started or
stopped. In this baseline only ``FakeSupervisor`` exists: it launches nothing and
simulates liveness (ticks/position), crashes, freezes, exit proof and resource
measurements so the Service loop can be tested end-to-end offline.

A real JVM supervisor (S04b) is NOT implemented: ADR-007 (client target) is still
open and the real client has never been inventoried on the owner's machine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol


class Supervisor(Protocol):
    def start(self, now: datetime) -> None: ...
    def ready(self, now: datetime) -> bool: ...
    def tick(self, now: datetime) -> Optional[int]: ...
    def position(self, now: datetime) -> Optional[tuple]: ...
    def stop(self, now: datetime) -> None: ...
    def exited(self, now: datetime) -> bool: ...
    def measure(self, now: datetime) -> Optional[dict]: ...


@dataclass
class FakeSupervisor:
    """Deterministic stand-in for a client process. Launches nothing.

    - ``ready_after_calls``: how many ``ready()`` polls return False before True.
    - ``freeze_at_tick``: from this tick on, ``tick()`` stops advancing (client frozen).
    - ``crash_at_tick``: at this tick the process "dies": ``tick()`` returns None and
      ``exited()`` becomes True without a stop request.
    - ``exit_on_stop``: whether ``stop()`` yields exit proof; False models a hung
      process (the Service must then settle to RECOVERY_REQUIRED, never READY).
    """
    ready_after_calls: int = 1
    freeze_at_tick: Optional[int] = None
    crash_at_tick: Optional[int] = None
    exit_on_stop: bool = True
    rss_bytes: int = 512 * 1024 ** 2
    disk_free_bytes: int = 50 * 1024 ** 3
    open_fds: int = 64
    cpu_percent: float = 20.0

    started: bool = field(default=False, init=False)
    stop_requested: bool = field(default=False, init=False)
    starts: int = field(default=0, init=False)
    stops: int = field(default=0, init=False)
    _ready_polls: int = field(default=0, init=False)
    _tick: int = field(default=0, init=False)
    _exited: bool = field(default=False, init=False)

    def start(self, now: datetime) -> None:
        self.started, self.stop_requested, self._exited = True, False, False
        self._ready_polls, self._tick = 0, 0
        self.starts += 1

    def ready(self, now: datetime) -> bool:
        if not self.started or self._exited:
            return False
        self._ready_polls += 1
        return self._ready_polls >= self.ready_after_calls

    def tick(self, now: datetime) -> Optional[int]:
        if not self.started or self._exited:
            return None
        if self.crash_at_tick is not None and self._tick + 1 >= self.crash_at_tick:
            self._exited = True
            return None
        if self.freeze_at_tick is not None and self._tick >= self.freeze_at_tick:
            return self._tick
        self._tick += 1
        return self._tick

    def position(self, now: datetime) -> Optional[tuple]:
        if not self.started or self._exited:
            return None
        return (3222, 3218, 0)

    def stop(self, now: datetime) -> None:
        self.stop_requested = True
        self.stops += 1
        if self.exit_on_stop:
            self._exited = True
            self.started = False

    def exited(self, now: datetime) -> bool:
        return self._exited

    def measure(self, now: datetime) -> Optional[dict]:
        return {"rss_bytes": self.rss_bytes, "disk_free_bytes": self.disk_free_bytes,
                "open_fds": self.open_fds, "cpu_percent": self.cpu_percent}
