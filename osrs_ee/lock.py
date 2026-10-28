"""SUP-04 — exclusive service lock per data directory.

One ``osrs-ee service`` per ``data_dir``: a second instance must fail closed
instead of racing the first for the same account/store. The lock also tells a
*starting* service something the Store alone cannot: if we hold the lock, no
other service process is alive, so any LEASED/STARTING/RUNNING/DRAINING account
in the store is an orphan of a dead process (see ``Store.reconcile_orphaned_sessions``).

POSIX: ``fcntl.flock(LOCK_EX | LOCK_NB)`` on ``<data_dir>/service.lock``; the
kernel releases it when the holder dies, so a crash never leaves a stale lock.
The pid is written for diagnostics only — never trusted for liveness.

Non-POSIX (Windows): ``fcntl`` is absent; ``ServiceLock`` falls back to
``msvcrt.locking`` on the same file. That branch is NOT tested here (Linux
sandbox) and is labelled TARGET_TEST_NOT_RUN in docs.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class LockHeld(RuntimeError):
    """Another live process holds the service lock."""

    def __init__(self, path: Path, holder_pid: Optional[int]):
        self.path, self.holder_pid = path, holder_pid
        who = f"pid {holder_pid}" if holder_pid else "unknown pid"
        super().__init__(f"service lock {path} is held by another instance ({who})")


class ServiceLock:
    """Context manager; ``acquire()`` raises ``LockHeld`` if taken."""

    def __init__(self, data_dir: str | Path, name: str = "service.lock") -> None:
        self.path = Path(data_dir) / name
        self._fh = None

    @property
    def held(self) -> bool:
        return self._fh is not None

    def _read_pid(self) -> Optional[int]:
        try:
            txt = self.path.read_text(encoding="ascii", errors="replace").strip()
            return int(txt) if txt else None
        except (OSError, ValueError):
            return None

    def acquire(self) -> "ServiceLock":
        if self._fh is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="ascii")
        try:
            try:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:  # pragma: no cover - Windows, not verified here
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            holder = self._read_pid()
            fh.close()
            raise LockHeld(self.path, holder) from None
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        if os.name == "posix":  # SEC-04: lock file is owner-only (holds our pid; lives in private data_dir)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        self._fh = fh
        return self

    def release(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            try:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            fh.close()

    def __enter__(self) -> "ServiceLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
