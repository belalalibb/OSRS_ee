"""S04b preparation — honest resource measurement from ``/proc`` (Linux only).

Every reader returns ``None`` when the value cannot be *measured* (no /proc,
process gone, permission denied). Nothing is estimated or defaulted: a
``ResourceSnapshot`` is only produced when all four values were read, which
is what ``osrs_ee.release.Admission`` expects ("measured on the target, never
estimated").

CPU percent needs two samples; ``CpuSampler.sample()`` returns ``None`` until
the second call. ``measure()`` therefore returns ``None`` on its first call.

This module measures *a pid*. Which pid (the game client / JVM) is a target
concern (ROADMAP S04b, T30/T31) — in the sandbox tests only measure the test
process itself.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from osrs_ee.release import ResourceSnapshot

PROC = "/proc"


def proc_available() -> bool:
    return os.path.isdir(PROC) and os.path.exists(os.path.join(PROC, "self", "status"))


def rss_bytes(pid: int) -> Optional[int]:
    try:
        with open(f"{PROC}/{pid}/status", encoding="ascii", errors="replace") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == "kB":
                        return int(parts[1]) * 1024
                    return None
    except (OSError, ValueError):
        return None
    return None


def open_fds(pid: int) -> Optional[int]:
    try:
        return len(os.listdir(f"{PROC}/{pid}/fd"))
    except OSError:
        return None


def disk_free_bytes(path: str) -> Optional[int]:
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def _cpu_ticks(pid: int) -> Optional[int]:
    try:
        with open(f"{PROC}/{pid}/stat", encoding="ascii", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    # comm may contain spaces/parens: split after the last ')'
    tail = text.rsplit(")", 1)
    if len(tail) != 2:
        return None
    fields = tail[1].split()
    # fields[0] is state (field 3); utime=field 14 -> index 11, stime=15 -> index 12
    try:
        return int(fields[11]) + int(fields[12])
    except (IndexError, ValueError):
        return None


@dataclass
class CpuSampler:
    pid: int
    clk_tck: int = 0
    _last: Optional[tuple[datetime, int]] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.clk_tck <= 0:
            try:
                self.clk_tck = int(os.sysconf("SC_CLK_TCK"))
            except (ValueError, OSError, AttributeError):
                self.clk_tck = 100

    def sample(self, now: datetime) -> Optional[float]:
        ticks = _cpu_ticks(self.pid)
        if ticks is None:
            self._last = None
            return None
        prev, self._last = self._last, (now, ticks)
        if prev is None:
            return None
        elapsed = (now - prev[0]).total_seconds()
        if elapsed <= 0:
            return None
        pct = (ticks - prev[1]) / self.clk_tck / elapsed * 100.0
        return max(0.0, min(pct, 10000.0))


def measure(pid: int, data_dir: str, now: datetime, *, cpu: Optional[CpuSampler] = None) -> Optional[ResourceSnapshot]:
    """All-or-nothing snapshot. ``cpu`` must be the sampler reused across calls."""
    sampler = cpu or CpuSampler(pid)
    rss, fds, free, pct = rss_bytes(pid), open_fds(pid), disk_free_bytes(data_dir), sampler.sample(now)
    if rss is None or fds is None or free is None or pct is None:
        return None
    return ResourceSnapshot(rss_bytes=rss, disk_free_bytes=free, open_fds=fds, cpu_percent=pct, measured_at=now)


def measure_dict(pid: int, data_dir: str, now: datetime, *, cpu: Optional[CpuSampler] = None) -> Optional[dict]:
    """Same as ``measure`` but in the ``Supervisor.measure()`` dict shape."""
    snap = measure(pid, data_dir, now, cpu=cpu)
    if snap is None:
        return None
    return {"rss_bytes": snap.rss_bytes, "disk_free_bytes": snap.disk_free_bytes,
            "open_fds": snap.open_fds, "cpu_percent": snap.cpu_percent}


def host_measurer(data_dir: str, now: datetime, *, pid: Optional[int] = None):
    """Callable ``now -> measure_dict`` for the *service host* (pre-start admission).

    Takes the first CPU sample immediately so the first real call can already
    yield a snapshot (still None if anything is unmeasurable)."""
    target = os.getpid() if pid is None else pid
    sampler = CpuSampler(target)
    sampler.sample(now)
    return lambda at: measure_dict(target, data_dir, at, cpu=sampler)
