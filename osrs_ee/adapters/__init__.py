"""S04a — adapter contract and local tooling that needs no game client.

Everything here runs offline. Nothing launches, attaches to, or talks to a
game client, JVM or GUI. Purpose: make the *shape* of a real adapter testable
before one exists (ROADMAP S04a), so that S04b (a read-only adapter on the
owner's machine) can be validated with the same conformance suite.

Exports:
* ``Adapter`` / ``AdapterResponse`` / ``AdapterFailure`` — re-exported from
  ``osrs_ee.worker`` (single source of truth; the worker keeps its aliases).
* ``RecordingAdapter`` — wraps any adapter, writes a redacted JSONL trace.
* ``ReplayAdapter`` — replays a JSONL trace without any client.
* ``run_conformance`` / ``ConformanceReport`` — contract checks for adapters.
* ``LoopbackReadOnlyAdapter`` (S04b-prep) — GET-only observe over a loopback
  endpoint; ``dispatch()`` always returns ``NEVER_DISPATCH`` (NOT_SENT).
"""
from __future__ import annotations

from osrs_ee.worker import Adapter, AdapterFailure, AdapterResponse, FakeAdapter

from .recording import RecordingAdapter, TraceWriter
from .replay import ReplayAdapter, ReplayExhausted, load_trace
from .conformance import ConformanceReport, run_conformance
from .loopback_readonly import EndpointError, LoopbackConfig, LoopbackReadOnlyAdapter, NEVER_DISPATCH

__all__ = [
    "Adapter", "AdapterFailure", "AdapterResponse", "FakeAdapter",
    "RecordingAdapter", "TraceWriter",
    "ReplayAdapter", "ReplayExhausted", "load_trace",
    "ConformanceReport", "run_conformance",
    "EndpointError", "LoopbackConfig", "LoopbackReadOnlyAdapter", "NEVER_DISPATCH",
]
