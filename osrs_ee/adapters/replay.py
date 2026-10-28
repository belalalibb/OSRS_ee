"""ReplayAdapter — replay a recorded JSONL trace with no client at all.

Allows the worker (and future supervisor) logic to be exercised against
*real, redacted* observations captured on a target machine (S04b) while
running in any environment. Replay is strict by default: the intents the
worker dispatches must match the recorded ones (by ``command_id`` and
``operation``), otherwise the trace is not evidence for this code path and a
``ReplayMismatch`` is raised. ``strict=False`` only relaxes the intent match
(responses are still consumed in order).
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque, Optional

from osrs_ee.worker import AdapterFailure, AdapterResponse

from .recording import TRACE_SCHEMA_VERSION


class ReplayError(Exception):
    """Trace malformed or unusable."""


class ReplayExhausted(ReplayError):
    """More calls were made than the trace contains."""


class ReplayMismatch(ReplayError):
    """Worker behaviour diverged from the recorded session."""


def load_trace(path: Path) -> list[dict]:
    """Parse and sanity-check a trace file. Returns the records (header excluded)."""
    records: list[dict] = []
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ReplayError(f"line {n}: invalid JSON: {e}") from None
            if not isinstance(rec, dict) or "t" not in rec:
                raise ReplayError(f"line {n}: not a trace record")
            records.append(rec)
    if not records or records[0].get("t") != "header":
        raise ReplayError("trace has no header")
    header = records[0]
    if header.get("schema_version") != TRACE_SCHEMA_VERSION:
        raise ReplayError(f"unsupported trace schema_version {header.get('schema_version')!r}")
    if header.get("redacted") is not True:
        raise ReplayError("trace not marked redacted; refusing to use")
    body = records[1:]
    for i, rec in enumerate(body, 1):
        if rec["t"] not in ("observe", "dispatch"):
            raise ReplayError(f"record {i}: unknown type {rec['t']!r}")
        if rec.get("seq") != i:
            raise ReplayError(f"record {i}: seq gap or reorder (got {rec.get('seq')})")
    return body


@dataclass
class ReplayAdapter:
    """Serve observations and dispatch results from a trace, in order."""
    records: list[dict]
    strict: bool = True
    _observes: Deque[dict] = field(default_factory=deque, init=False, repr=False)
    _dispatches: Deque[dict] = field(default_factory=deque, init=False, repr=False)
    served_observes: int = field(default=0, init=False)
    served_dispatches: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for rec in self.records:
            (self._observes if rec["t"] == "observe" else self._dispatches).append(rec)
        if not self._observes:
            raise ReplayError("trace contains no observation; cannot serve observe()")

    @classmethod
    def from_file(cls, path: Path, *, strict: bool = True) -> "ReplayAdapter":
        return cls(load_trace(path), strict=strict)

    @property
    def remaining(self) -> tuple[int, int]:
        return len(self._observes), len(self._dispatches)

    def observe(self, now: datetime) -> dict:
        # Observations are served in order; the last one is held (a real client
        # keeps answering the same state when nothing changes).
        if len(self._observes) > 1:
            rec = self._observes.popleft()
        else:
            rec = self._observes[0]
        self.served_observes += 1
        return rec["observation"]

    def dispatch(self, intent: dict, *, deadline: datetime, now: datetime) -> Optional[AdapterResponse]:
        if not self._dispatches:
            raise ReplayExhausted("trace has no further dispatch record")
        rec = self._dispatches.popleft()
        self.served_dispatches += 1
        recorded = rec.get("intent", {})
        if self.strict and (recorded.get("command_id") != intent.get("command_id")
                            or recorded.get("operation") != intent.get("operation")):
            raise ReplayMismatch(
                f"recorded {recorded.get('operation')}/{recorded.get('command_id')} "
                f"!= dispatched {intent.get('operation')}/{intent.get('command_id')}")
        result = rec.get("result", {})
        kind = result.get("kind")
        if kind == "timeout":
            return None
        if kind == "failure":
            raise AdapterFailure(f"replayed failure: {result.get('error_type')}: {result.get('message')}")
        if kind == "response":
            r = result["response"]
            return AdapterResponse(r["transport_status"], r["effect_status"], tuple(r.get("evidence_refs", ())),
                                   r.get("reason_code", "NONE"))
        raise ReplayError(f"dispatch record has unknown result kind {kind!r}")
