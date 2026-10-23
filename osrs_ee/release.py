"""S08 — release / cache / resource admission / network policy, pure parts.

Covers the local, deterministic rules of T14/T15/T18/T19/T32 (FOUNDATION §:
"release: DETECTED→DOWNLOADED→BUILT→CONTRACT_TESTED→APPROVED→DRAINING→CANARY→ACTIVE؛
hash/evidence لكل خطوة؛ rollback غير متوافق→stop"; "logs/photos/outbox bounded
count/bytes/age"; "admission/reserve"; "no forbidden fallback").

* Registry: artifacts are admitted only if (name, sha256) is on the reviewed
  allow-list and the path is safe; anything else is QUARANTINED before load (T14).
* Release: immutable manifest hash; a strict forward state machine with evidence
  per step; a failed step rolls back to the last compatible ACTIVE release or
  STOPs when none is compatible (T15). Live canary is *not* modelled (needs owner).
* BoundedCache: count/bytes/age bounds with eviction; writes isolated per owner;
  identity-bearing paths are never cached (T32/V08 scope only, no anti-ban claim).
* Admission: measured resource snapshot (never a heap estimate) vs reserve; a
  disk/RSS/FD shortfall denies new sessions and asks the running one to stop (T18).
* NetworkPolicy: a route must match the declared policy; outage/expiry never
  falls back to a forbidden route; no renew while an UNKNOWN command is pending (T19).

No I/O here: hashes are over bytes passed in; "measurements" are injected.
"""
from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Optional

from osrs_ee import canonical
from osrs_ee.guards import GuardDecision

__all__ = ["Registry", "ReleaseManifest", "Release", "ReleaseError", "BoundedCache", "ResourceSnapshot",
           "Admission", "NetworkPolicy"]


# ---------------------------------------------------------------- registry
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relpath(path: str) -> bool:
    if not path or path.startswith(("/", "\\")) or "\\" in path or "\x00" in path:
        return False
    norm = posixpath.normpath(path)
    return norm == path and not norm.startswith("..") and "/../" not in f"/{norm}/"


@dataclass
class Registry:
    """Reviewed allow-list: name -> (sha256, license). Unknown/mismatched -> QUARANTINE (T14)."""
    allowed: dict[str, tuple[str, str]] = field(default_factory=dict)
    quarantine: list[tuple[str, str, str]] = field(default_factory=list)  # (name, sha, reason)

    def allow(self, name: str, sha256: str, license_id: str) -> None:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise ValueError("sha256 must be 64 lowercase hex chars")
        self.allowed[name] = (sha256, license_id)

    def admit(self, name: str, data: bytes, *, path: str) -> GuardDecision:
        sha = sha256_hex(data)
        if not _safe_relpath(path):
            self.quarantine.append((name, sha, "unsafe path"))
            return GuardDecision.deny("POLICY_DENIED", "unsafe artifact path")
        entry = self.allowed.get(name)
        if entry is None:
            self.quarantine.append((name, sha, "not on allow-list"))
            return GuardDecision.deny("POLICY_DENIED", "artifact not reviewed")
        if entry[0] != sha:
            self.quarantine.append((name, sha, "hash mismatch"))
            return GuardDecision.deny("IDENTITY_UNVERIFIED", "artifact hash mismatch")
        return GuardDecision.ok()


# ----------------------------------------------------------------- release
class ReleaseError(Exception):
    pass


RELEASE_STATES = ("DETECTED", "DOWNLOADED", "BUILT", "CONTRACT_TESTED", "APPROVED", "DRAINING", "CANARY", "ACTIVE")
TERMINAL_RELEASE = frozenset({"ROLLED_BACK", "STOPPED"})


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    artifacts: Mapping[str, str]        # name -> sha256
    contract_version: str                # must match the running Store/contracts to be compatible
    store_schema_version: str

    def hash(self) -> str:
        return canonical.content_hash({"version": self.version, "artifacts": dict(self.artifacts),
                                       "contract_version": self.contract_version, "store_schema_version": self.store_schema_version})

    def compatible_with(self, other: "ReleaseManifest") -> bool:
        return self.contract_version == other.contract_version and self.store_schema_version == other.store_schema_version


class Release:
    """Strict forward pipeline with evidence per step; failure -> rollback or STOP (T15)."""

    def __init__(self, manifest: ReleaseManifest, registry: Registry) -> None:
        self.manifest, self.registry = manifest, registry
        self.manifest_hash = manifest.hash()
        self.state = "DETECTED"
        self.evidence: list[tuple[str, str, str]] = []  # (step, evidence_ref, at)
        self.failure: Optional[str] = None

    def advance(self, to_state: str, *, evidence_ref: str, now: datetime) -> str:
        if self.state in TERMINAL_RELEASE:
            raise ReleaseError(f"release is terminal ({self.state})")
        idx = RELEASE_STATES.index(self.state)
        if to_state not in RELEASE_STATES or RELEASE_STATES.index(to_state) != idx + 1:
            raise ReleaseError(f"{self.state} -> {to_state} is not the next step")
        if not evidence_ref.startswith("ref:"):
            raise ReleaseError("each step requires an evidence ref")
        if to_state == "DOWNLOADED":
            # every artifact must have been admitted by the registry (hash on allow-list)
            for name, sha in self.manifest.artifacts.items():
                entry = self.registry.allowed.get(name)
                if entry is None or entry[0] != sha:
                    return self.fail("artifact not admitted", active=None)
        self.state = to_state
        self.evidence.append((to_state, evidence_ref, now.strftime("%Y-%m-%dT%H:%M:%SZ")))
        return self.state

    def fail(self, reason: str, *, active: Optional["Release"]) -> str:
        """Roll back to the compatible ACTIVE release, else STOP. Never leaves a mixed version live."""
        self.failure = reason
        if active is not None and active.state == "ACTIVE" and active.manifest.compatible_with(self.manifest):
            self.state = "ROLLED_BACK"
        else:
            self.state = "STOPPED"
        return self.state


# ------------------------------------------------------------------- cache
IDENTITY_MARKERS = ("hwid", "identity", "machine-id", "jagex_session", "credentials", "cookies")


class BoundedCache:
    """Count/bytes/age bounded cache with LRU eviction; isolated per owner; no identity paths (T32)."""

    def __init__(self, *, max_entries: int, max_bytes: int, max_age_seconds: int) -> None:
        if max_entries < 1 or max_bytes < 1 or max_age_seconds < 1:
            raise ValueError("cache bounds must be >= 1")
        self.max_entries, self.max_bytes, self.max_age = max_entries, max_bytes, timedelta(seconds=max_age_seconds)
        self._items: dict[tuple[str, str], tuple[bytes, datetime, datetime]] = {}  # (owner,key)->(data, written, last_used)
        self.evicted: list[tuple[str, str, str]] = []

    @property
    def bytes_used(self) -> int:
        return sum(len(v[0]) for v in self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def put(self, owner: str, key: str, data: bytes, *, now: datetime) -> GuardDecision:
        low = key.lower()
        if any(m in low for m in IDENTITY_MARKERS):
            return GuardDecision.deny("POLICY_DENIED", "identity-bearing content is never cached")
        if not _safe_relpath(key):
            return GuardDecision.deny("POLICY_DENIED", "unsafe cache key")
        if len(data) > self.max_bytes:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "entry larger than cache")
        self.expire(now=now)
        self._items[(owner, key)] = (data, now, now)
        while len(self._items) > self.max_entries or self.bytes_used > self.max_bytes:
            victim = min((k for k in self._items if k != (owner, key)), key=lambda k: self._items[k][2], default=None)
            if victim is None:
                break
            del self._items[victim]
            self.evicted.append((*victim, "capacity"))
        return GuardDecision.ok()

    def get(self, owner: str, key: str, *, now: datetime) -> Optional[bytes]:
        self.expire(now=now)
        v = self._items.get((owner, key))
        if v is None:
            return None
        self._items[(owner, key)] = (v[0], v[1], now)
        return v[0]

    def expire(self, *, now: datetime) -> int:
        old = [k for k, v in self._items.items() if now - v[1] > self.max_age]
        for k in old:
            del self._items[k]
            self.evicted.append((*k, "age"))
        return len(old)


# --------------------------------------------------------------- admission
@dataclass(frozen=True)
class ResourceSnapshot:
    """Measured on the target (never estimated). Units: bytes / count / percent."""
    rss_bytes: int
    disk_free_bytes: int
    open_fds: int
    cpu_percent: float
    measured_at: datetime


@dataclass(frozen=True)
class Admission:
    rss_limit_bytes: int
    disk_reserve_bytes: int
    fd_limit: int
    cpu_limit_percent: float
    snapshot_max_age_seconds: int = 30

    def decide(self, snap: ResourceSnapshot, *, running_sessions: int, now: datetime) -> GuardDecision:
        """Admit a *new* session only with a fresh snapshot inside every limit (T18)."""
        if (now - snap.measured_at).total_seconds() > self.snapshot_max_age_seconds:
            return GuardDecision.deny("STALE_CONTEXT", "resource snapshot too old")
        if running_sessions >= 1:
            return GuardDecision.deny("POLICY_DENIED", "concurrency is 1 in this baseline")
        if snap.disk_free_bytes < self.disk_reserve_bytes:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "disk below reserve")
        if snap.rss_bytes >= self.rss_limit_bytes:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "RSS at limit")
        if snap.open_fds >= self.fd_limit:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "FD at limit")
        if snap.cpu_percent >= self.cpu_limit_percent:
            return GuardDecision.deny("INSUFFICIENT_RESOURCES", "CPU at limit")
        return GuardDecision.ok()

    def must_stop(self, snap: ResourceSnapshot) -> bool:
        """Pressure on a running session: disk below reserve or RSS over limit → stop (state first)."""
        return snap.disk_free_bytes < self.disk_reserve_bytes or snap.rss_bytes >= self.rss_limit_bytes


# ----------------------------------------------------------------- network
@dataclass(frozen=True)
class NetworkPolicy:
    """Declared route per account; no silent fallback (T19)."""
    required_route: str                 # "PROXY" | "DIRECT"
    allow_direct_fallback: bool = False
    sticky_ttl_seconds: int = 3600

    def check_route(self, actual_route: str, *, proxy_healthy: bool, sticky_since: Optional[datetime],
                    unknown_pending: int, now: datetime) -> GuardDecision:
        if actual_route not in ("PROXY", "DIRECT"):
            return GuardDecision.deny("POLICY_DENIED", "unknown route")
        if self.required_route == "PROXY":
            if actual_route == "DIRECT" and not self.allow_direct_fallback:
                return GuardDecision.deny("POLICY_DENIED", "direct fallback forbidden by policy")
            if actual_route == "PROXY" and not proxy_healthy:
                return GuardDecision.deny("PROXY_UNAVAILABLE", "proxy outage; no fallback")
            if sticky_since is not None and (now - sticky_since).total_seconds() > self.sticky_ttl_seconds:
                if unknown_pending > 0:
                    return GuardDecision.deny("STALE_CONTEXT", "sticky expired but UNKNOWN pending; no renew")
                return GuardDecision.deny("PROXY_UNAVAILABLE", "sticky session expired; renew required")
        elif actual_route != "DIRECT":
            return GuardDecision.deny("POLICY_DENIED", "policy requires DIRECT")
        return GuardDecision.ok()
