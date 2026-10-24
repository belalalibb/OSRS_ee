"""T33 / S04b acceptance — target-only: the read-only adapter against the REAL
client state endpoint (ADR-008 decides how that endpoint is produced).

Skipped unless OSRS_EE_TARGET=1 and OSRS_EE_TARGET_ENDPOINT (loopback URL) are
set on the owner's machine. Dispatch is never attempted (the adapter refuses).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from osrs_ee.adapters import LoopbackConfig, LoopbackReadOnlyAdapter, run_conformance

pytestmark = pytest.mark.target


@pytest.fixture
def endpoint():
    url = os.environ.get("OSRS_EE_TARGET_ENDPOINT")
    if not url:
        pytest.skip("OSRS_EE_TARGET_ENDPOINT (http://127.0.0.1:<port>/...) not set — ADR-008 pending")
    return url


def test_S04b_readonly_adapter_passes_conformance_against_real_endpoint(endpoint, allow_network_sockets):
    adapter = LoopbackReadOnlyAdapter(LoopbackConfig(endpoint=endpoint, timeout_seconds=5.0))
    report = run_conformance(adapter, now=datetime.now(timezone.utc), allowed_hosts=frozenset({"127.0.0.1", "localhost", "::1"}))
    assert report.passed, [f for f in report.findings if not f.passed]
    assert adapter.dispatch_refusals >= 1  # the suite's probe intent was refused, never sent


def test_T33_egress_inventory_contains_only_loopback(endpoint, allow_network_sockets):
    from osrs_ee.egress import EgressPolicy, guarded_opener
    policy = EgressPolicy(allow_loopback=True)
    adapter = LoopbackReadOnlyAdapter(LoopbackConfig(endpoint=endpoint), opener=guarded_opener(policy))
    adapter.observe(datetime.now(timezone.utc))
    assert policy.denied() == []
    assert all(row[1] in ("127.0.0.1", "localhost", "::1") for row in policy.inventory)
