"""target-check — inventory of a candidate target machine (S04a).

Collects facts needed before S04b can start and lists what is missing. It
**never launches a game client, JVM or GUI**; the only subprocess it may run
is ``java -version`` (and only when a `java` binary is on PATH), which prints
version text and exits. Everything else is file-system and OS introspection.

Output is a JSON document meant to be saved under ``evidence/target/`` by the
owner; the ``missing`` list is the gate for S04b (see OUT_OF_SANDBOX §3.1).
"""
from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MIN_PYTHON = (3, 11)
MIN_FREE_DISK_MB = 2048
MIN_RAM_MB = 4096           # advisory; JVM client + core
MIN_FD_SOFT_LIMIT = 4096    # advisory; long-lived process with sqlite/wal/logs


@dataclass
class TargetReport:
    facts: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ready_for_s04b(self) -> bool:
        return not self.missing

    def to_dict(self) -> dict:
        return {"facts": self.facts, "missing": self.missing, "warnings": self.warnings,
                "ready_for_s04b": self.ready_for_s04b,
                "note": "inventory only; nothing was launched. S04b additionally needs ADR-007/008 and explicit owner permission."}


def _java_version(java: str, timeout: float) -> Optional[str]:
    try:
        proc = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stderr or proc.stdout or "").strip().splitlines()
    return text[0] if text else None


def _ram_mb() -> Optional[int]:
    try:
        pages = os.sysconf("SC_PHYS_PAGES"); size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * size / (1024 * 1024))
    except (ValueError, OSError, AttributeError):
        return None


def _fd_limit() -> Optional[int]:
    try:
        import resource
        return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except Exception:  # noqa: BLE001 - not available on all platforms
        return None


def _display() -> dict:
    env = os.environ
    return {"DISPLAY": env.get("DISPLAY"), "WAYLAND_DISPLAY": env.get("WAYLAND_DISPLAY"),
            "windows_session": platform.system() == "Windows"}


def run_target_check(*, client_path: Optional[str] = None, data_dir: Optional[str] = None,
                     run_java_probe: bool = True, java_timeout: float = 5.0) -> TargetReport:
    rep = TargetReport()
    f = rep.facts
    f["os"] = {"system": platform.system(), "release": platform.release(), "machine": platform.machine()}
    f["python"] = {"version": platform.python_version(), "executable": sys.executable}
    if sys.version_info < MIN_PYTHON:
        rep.missing.append(f"python>={'.'.join(map(str, MIN_PYTHON))} (found {platform.python_version()})")
    f["sqlite"] = sqlite3.sqlite_version
    try:
        from importlib.metadata import version as _pkg_version
        f["jsonschema"] = _pkg_version("jsonschema")
    except Exception:  # noqa: BLE001 - PackageNotFoundError or metadata missing
        f["jsonschema"] = None
        rep.missing.append("python package jsonschema (pip install -e .)")

    java = shutil.which("java")
    f["java"] = {"path": java, "version": None}
    if java is None:
        rep.missing.append("java runtime on PATH (ADR-007 decides the JVM; required by S04b)")
    elif run_java_probe:
        f["java"]["version"] = _java_version(java, java_timeout)
        if f["java"]["version"] is None:
            rep.warnings.append("java found but `java -version` produced no output")

    f["client"] = {"path": client_path, "present": bool(client_path) and Path(client_path).exists()}
    if not client_path:
        rep.missing.append("game client path (pass --client PATH; ADR-007 decides which client)")
    elif not f["client"]["present"]:
        rep.missing.append(f"game client not found at {client_path}")

    disp = _display(); f["display"] = disp
    if not (disp["DISPLAY"] or disp["WAYLAND_DISPLAY"] or disp["windows_session"]):
        rep.missing.append("graphical session (DISPLAY/WAYLAND_DISPLAY or Windows desktop; Xvfb acceptable for headless)")

    target_dir = Path(data_dir or os.getcwd())
    try:
        usage = shutil.disk_usage(target_dir)
        free_mb = usage.free // (1024 * 1024)
    except OSError:
        free_mb = None
    f["disk"] = {"path": str(target_dir), "free_mb": free_mb}
    if free_mb is not None and free_mb < MIN_FREE_DISK_MB:
        rep.missing.append(f"free disk >= {MIN_FREE_DISK_MB} MB at {target_dir} (found {free_mb})")

    ram = _ram_mb(); f["ram_mb"] = ram
    if ram is not None and ram < MIN_RAM_MB:
        rep.warnings.append(f"RAM {ram} MB below advisory minimum {MIN_RAM_MB} MB")
    fd = _fd_limit(); f["fd_soft_limit"] = fd
    if fd is not None and fd < MIN_FD_SOFT_LIMIT:
        rep.warnings.append(f"fd soft limit {fd} below advisory {MIN_FD_SOFT_LIMIT}")

    f["decisions"] = {"ADR-007": "owner must record (OS/JVM/client)", "ADR-008": "owner must record (auth_mode after V05)"}
    rep.missing.append("ADR-007 and ADR-008 recorded as ACCEPTED in docs/FOUNDATION.md (owner)")
    return rep
