"""Target/live test gating (honest skips, never paper passes).

* ``@pytest.mark.target`` tests run ONLY when ``OSRS_EE_TARGET=1`` is set on the
  owner's machine. Elsewhere they are reported as skipped (`s`).
* ``@pytest.mark.live`` tests run ONLY when ``OSRS_EE_ALLOW_NETWORK=1`` and the
  referenced env var(s) exist. The tests never read secret values themselves;
  transports resolve ``ref:env:NAME``.

How to run them: docs/RUNBOOK.md §4.
"""
from __future__ import annotations

import os

import pytest

TARGET_ENV = "OSRS_EE_TARGET"
NETWORK_ENV = "OSRS_EE_ALLOW_NETWORK"


def pytest_collection_modifyitems(config, items):
    on_target = os.environ.get(TARGET_ENV) == "1"
    network = os.environ.get(NETWORK_ENV) == "1"
    for item in items:
        marks = {m.name for m in item.iter_markers()}  # explicit markers only (the directory is also named "target")
        if "target" in marks and not on_target:
            item.add_marker(pytest.mark.skip(reason=f"TARGET-ONLY: set {TARGET_ENV}=1 on the owner's machine (NOT_RUN here)"))
        if "live" in marks and not network:
            item.add_marker(pytest.mark.skip(reason=f"LIVE: set {NETWORK_ENV}=1 and the ref:env secret (NOT_RUN here)"))


@pytest.fixture
def target_cfg_path():
    p = os.environ.get("OSRS_EE_TARGET_CONFIG")
    if not p or not os.path.isfile(p):
        pytest.skip("OSRS_EE_TARGET_CONFIG must point at the device config.toml (target machine only)")
    return p


@pytest.fixture
def allow_network_sockets():
    """tests/conftest.py forbids sockets; target/live tests restore the real socket for their duration."""
    import socket
    from tests import conftest as root
    socket.socket = root._REAL_SOCKET  # type: ignore[attr-defined]
    socket.create_connection = root._REAL_CREATE_CONNECTION  # type: ignore[attr-defined]
    try:
        yield
    finally:
        socket.socket = root._forbidden  # type: ignore[attr-defined]
        socket.create_connection = root._forbidden  # type: ignore[attr-defined]
