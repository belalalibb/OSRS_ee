"""RecordingAdapter — wrap any adapter and persist a redacted JSONL trace.

Trace format (one JSON object per line, ``schema_version`` "trace/1"):

    {"t": "header", "schema_version": "trace/1", "started_at": "...", "redacted": true}
    {"t": "observe",  "seq": 1, "now": "...", "observation": {...}}
    {"t": "dispatch", "seq": 2, "now": "...", "deadline": "...", "intent": {...},
     "result": {"kind": "response", "response": {...}} |
               {"kind": "timeout"} |
               {"kind": "failure", "error_type": "AdapterFailure", "message": "..."}}

Redaction rules (fail-closed): every record is serialised; every account id
known to the ``Redactor`` (its ``aliases`` keys) is replaced by a *contract-valid*
pseudonym ``acc_r<sha256(id|salt)[:20]>`` (so replayed observations still
validate against the Observation contract; the human alias is not used because
aliases are free text); then the text is passed through ``Redactor.scan``; if
any canary or secret-shaped text survives, the record is **not written** and a
``RedactionError`` is raised *after* the underlying adapter call has already
been forwarded (recording never changes the worker's behaviour, it only adds a
side channel). Failures raised by the wrapped adapter are re-raised unchanged.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Optional

from osrs_ee.telegram import RedactionError, Redactor
from osrs_ee.worker import Adapter, AdapterResponse

TRACE_SCHEMA_VERSION = "trace/1"


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TraceWriter:
    """Append-only JSONL sink with mandatory redaction."""
    path: Path
    redactor: Redactor
    salt: str = "osrs-ee-trace"
    _fh: Optional[IO[str]] = field(default=None, init=False, repr=False)
    records_written: int = field(default=0, init=False)
    records_rejected: int = field(default=0, init=False)

    def open(self, *, now: datetime) -> "TraceWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        self.write({"t": "header", "schema_version": TRACE_SCHEMA_VERSION, "started_at": _ts(now), "redacted": True})
        return self

    def pseudonym(self, account_id: str) -> str:
        """Deterministic, contract-shaped, non-reversible without the salt."""
        return "acc_r" + hashlib.sha256(f"{account_id}|{self.salt}".encode()).hexdigest()[:20]

    def write(self, record: dict) -> None:
        if self._fh is None:
            raise RuntimeError("trace not open")
        text = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for account_id in self.redactor.aliases:
            text = text.replace(account_id, self.pseudonym(account_id))
        reason = self.redactor.scan(text)
        if reason:
            self.records_rejected += 1
            raise RedactionError(f"trace record withheld: {reason}")
        self._fh.write(text + "\n")
        self._fh.flush()
        self.records_written += 1

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


@dataclass
class RecordingAdapter:
    """Forward every call to ``inner`` and record it. Behaviour-preserving."""
    inner: Adapter
    writer: TraceWriter
    seq: int = 0

    def observe(self, now: datetime) -> dict:
        observation = self.inner.observe(now)
        self.seq += 1
        self.writer.write({"t": "observe", "seq": self.seq, "now": _ts(now), "observation": observation})
        return observation

    def dispatch(self, intent: dict, *, deadline: datetime, now: datetime) -> Optional[AdapterResponse]:
        self.seq += 1
        base = {"t": "dispatch", "seq": self.seq, "now": _ts(now), "deadline": _ts(deadline), "intent": intent}
        try:
            resp = self.inner.dispatch(intent, deadline=deadline, now=now)
        except Exception as e:  # noqa: BLE001 - recorded then re-raised unchanged
            self.writer.write(base | {"result": {"kind": "failure", "error_type": type(e).__name__, "message": str(e)}})
            raise
        if resp is None:
            self.writer.write(base | {"result": {"kind": "timeout"}})
        else:
            self.writer.write(base | {"result": {"kind": "response", "response": {
                "transport_status": resp.transport_status, "effect_status": resp.effect_status,
                "evidence_refs": list(resp.evidence_refs), "reason_code": resp.reason_code}}})
        return resp
