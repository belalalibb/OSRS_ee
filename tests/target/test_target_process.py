"""T10 / T30 / T06 / T31 — target-only: supervise the REAL client process (ADR-007).

Acceptance steps from docs/OUT_OF_SANDBOX.md §3.2 as code. SKIPPED everywhere
except the owner's machine with OSRS_EE_TARGET=1, OSRS_EE_TARGET_CONFIG (device
config with [target].client_path) and OSRS_EE_TARGET_READY_FILE (the client's
readiness proof — defined by ADR-007). No account login: start, observe, stop.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest

from osrs_ee import measure as ms
from osrs_ee.config import load_config
from osrs_ee.supervisor import ProcessSpec, ProcessSupervisor

pytestmark = pytest.mark.target


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def client_spec(target_cfg_path, tmp_path):
    cfg = load_config(target_cfg_path)
    if cfg.target.mode != "device" or not cfg.target.client_path:
        pytest.skip("device config with target.client_path required (ADR-007 decision pending)")
    ready = os.environ.get("OSRS_EE_TARGET_READY_FILE")
    if not ready:
        pytest.skip("OSRS_EE_TARGET_READY_FILE: client readiness proof path not defined yet (ADR-007)")
    return ProcessSpec(argv=(cfg.target.client_path,), ready_file=ready, stop_grace_seconds=15.0, cwd=str(tmp_path)), cfg


def test_T10_client_starts_becomes_ready_and_stops_cleanly(client_spec, tmp_path):
    spec, cfg = client_spec
    sup = ProcessSupervisor(spec, log_path=str(tmp_path / "client.log"), data_dir=cfg.target.data_dir)
    sup.start(_now())
    deadline = time.monotonic() + cfg.health.ready_timeout_seconds
    while time.monotonic() < deadline and not sup.ready(_now()):
        assert not sup.exited(_now()), f"client exited before readiness (code {sup.last_exit_code})"
        time.sleep(0.5)
    assert sup.ready(_now()), "no readiness proof within health.ready_timeout_seconds"
    sup.stop(_now())
    assert sup.exited(_now()), "no exit proof after SIGTERM/SIGKILL"
    assert sup.last_stop_method == "SIGTERM", "client needed SIGKILL: orderly stop not honoured"


def test_T30_kill_minus_9_is_detected_as_crash_not_stop(client_spec):
    spec, cfg = client_spec
    sup = ProcessSupervisor(spec, data_dir=cfg.target.data_dir)
    sup.start(_now())
    time.sleep(2)
    os.kill(sup.pid, 9)
    time.sleep(1)
    assert sup.exited(_now()) and not sup.stop_requested
    assert sup.last_exit_code not in (0, None)


def test_T06_T31_resource_snapshot_is_measured_not_estimated(client_spec):
    spec, cfg = client_spec
    sup = ProcessSupervisor(spec, data_dir=cfg.target.data_dir)
    sup.start(_now())
    try:
        time.sleep(2)
        assert sup.measure(_now()) is None  # first CPU sample
        time.sleep(1)
        snap = sup.measure(_now())
        assert snap is not None and snap["rss_bytes"] > 0 and snap["open_fds"] > 0
        assert ms.disk_free_bytes(cfg.target.data_dir) is not None
    finally:
        sup.stop(_now())
