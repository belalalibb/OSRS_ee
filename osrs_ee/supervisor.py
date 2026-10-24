"""S04c-local — client process supervision boundary.

``Supervisor`` is the *only* place where a client process would be started or
stopped. In this baseline only ``FakeSupervisor`` exists: it launches nothing and
simulates liveness (ticks/position), crashes, freezes, exit proof and resource
measurements so the Service loop can be tested end-to-end offline.

A real JVM supervisor (S04b) is NOT implemented: ADR-007 (client target) is still
open and the real client has never been inventoried on the owner's machine.

``ProcessSupervisor`` (S04b-prep) is the *generic* child-process half of that
work: spawn / readiness proof / SIGTERM→SIGKILL stop / exit proof / /proc
measurement for an arbitrary executable. It is tested only with a harmless
Python child. It never knows what a game client is.
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


# ----------------------------------------------------------------- generic process
@dataclass(frozen=True)
class ProcessSpec:
    """What to supervise. ``argv[0]`` must be an absolute path to an existing,
    executable file (fail closed: no PATH lookup, no shell). ``ready_file`` is the
    readiness proof: the child creates it when it is actually ready; its first
    line, if an integer, is the child's tick counter (re-read on every ``tick()``).
    """
    argv: tuple[str, ...]
    cwd: Optional[str] = None
    ready_file: Optional[str] = None
    stop_grace_seconds: float = 5.0
    env: Optional[dict] = None

    def __post_init__(self) -> None:
        import os
        if not self.argv or not isinstance(self.argv[0], str):
            raise ValueError("argv must be a non-empty tuple")
        exe = self.argv[0]
        if not os.path.isabs(exe) or not os.path.isfile(exe) or not os.access(exe, os.X_OK):
            raise ValueError("argv[0] must be an absolute path to an existing executable file")
        if not (0.1 <= float(self.stop_grace_seconds) <= 300.0):
            raise ValueError("stop_grace_seconds must be within [0.1, 300]")
        if self.cwd is not None and not os.path.isdir(self.cwd):
            raise ValueError("cwd must be an existing directory")


class ProcessSupervisor:
    """Generic child-process supervisor (stdlib ``subprocess``; no shell, no PTY).

    General logic — testable locally with a harmless Python child:
    * ``start``: spawn in its own session (``start_new_session=True``) so a stop
      never signals the service itself; stdout/stderr go to a log file or
      DEVNULL (never inherited: a child must not write to the operator's TTY).
    * ``ready``: True only when ``ready_file`` exists (the child's proof), never
      "process is alive".
    * ``tick``: integer from the ready file's first line (None when absent).
    * ``stop``: SIGTERM → wait ``stop_grace_seconds`` → SIGKILL → wait; exit proof
      is ``poll()`` returning a code. ``exited()`` stays False if the process
      survives SIGKILL (zombie/D state), so the Service settles to
      RECOVERY_REQUIRED instead of claiming RESTING.
    * ``measure``: ``osrs_ee.measure`` over the child's pid (/proc; None when not
      measurable — admission then refuses, it never guesses).

    Target-only (NOT verified here): launching the actual client (ADR-007), what
    constitutes its readiness proof, its ticks, and resource limits on the owner's
    machine. Nothing in this class knows anything about a game.
    """

    def __init__(self, spec: ProcessSpec, *, log_path: Optional[str] = None, data_dir: str = ".") -> None:
        import subprocess
        self.spec, self.log_path, self.data_dir = spec, log_path, data_dir
        self._subprocess = subprocess
        self._proc: Optional[subprocess.Popen] = None
        self._log = None
        self._cpu = None
        self.starts = self.stops = 0
        self.stop_requested = False
        self.last_exit_code: Optional[int] = None
        self.last_stop_method: Optional[str] = None   # "SIGTERM" | "SIGKILL" | None

    def start(self, now: datetime) -> None:
        import os
        from osrs_ee.measure import CpuSampler
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError("already running")
        if self.spec.ready_file and os.path.exists(self.spec.ready_file):
            os.unlink(self.spec.ready_file)  # stale proof from a previous run is not proof
        sink = self._subprocess.DEVNULL
        if self.log_path:
            self._log = open(self.log_path, "ab", buffering=0)
            sink = self._log
        self._proc = self._subprocess.Popen(
            list(self.spec.argv), cwd=self.spec.cwd, env=self.spec.env, stdin=self._subprocess.DEVNULL,
            stdout=sink, stderr=self._subprocess.STDOUT, start_new_session=True, close_fds=True)
        self._cpu = CpuSampler(self._proc.pid)
        self.starts += 1
        self.stop_requested = False
        self.last_exit_code = None
        self.last_stop_method = None

    def ready(self, now: datetime) -> bool:
        import os
        if self._proc is None or self._proc.poll() is not None:
            return False
        return bool(self.spec.ready_file) and os.path.exists(self.spec.ready_file)

    def tick(self, now: datetime) -> Optional[int]:
        if self._proc is None or self._proc.poll() is not None or not self.spec.ready_file:
            return None
        try:
            with open(self.spec.ready_file, encoding="ascii", errors="replace") as fh:
                return int(fh.readline().strip())
        except (OSError, ValueError):
            return None

    def position(self, now: datetime) -> Optional[tuple]:
        return None  # a generic process has no position

    def stop(self, now: datetime) -> None:
        import signal
        self.stops += 1
        self.stop_requested = True
        p = self._proc
        if p is None:
            return
        if p.poll() is None:
            try:
                p.send_signal(signal.SIGTERM)
                self.last_stop_method = "SIGTERM"
                p.wait(timeout=self.spec.stop_grace_seconds)
            except self._subprocess.TimeoutExpired:
                try:
                    p.kill()
                    self.last_stop_method = "SIGKILL"
                    p.wait(timeout=self.spec.stop_grace_seconds)
                except (self._subprocess.TimeoutExpired, OSError):
                    pass
            except OSError:
                pass
        self.last_exit_code = p.poll()
        if self._log is not None:
            self._log.close()
            self._log = None

    def exited(self, now: datetime) -> bool:
        if self._proc is None:
            return False
        code = self._proc.poll()
        if code is not None:
            self.last_exit_code = code
            return True
        return False

    def measure(self, now: datetime) -> Optional[dict]:
        from osrs_ee.measure import measure_dict
        if self._proc is None or self._proc.poll() is not None:
            return None
        return measure_dict(self._proc.pid, self.data_dir, now, cpu=self._cpu)

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None
