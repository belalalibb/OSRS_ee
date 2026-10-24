"""S04c-local — typed, fail-closed service configuration (TOML via stdlib ``tomllib``).

Rules enforced here (all local, no network):
- unknown sections or keys are errors (typos never silently become defaults);
- secret-shaped literals are refused anywhere in the file; credentials are *references*
  (``ref:...``) that the Store resolves later — never the secret itself;
- ``target.mode = "device"`` requires ``client_path``; ``auth_mode`` is locked to
  ``UNKNOWN`` until ADR-008 is decided by the owner;
- every numeric limit has a bound; ``config_hash`` must be 64 hex chars.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, Optional

from .telegram import _SECRET_PATTERNS

HEX64 = 64
MODES = ("simulated", "device")
ROUTES = ("DIRECT", "PROXY")


class ConfigError(Exception):
    """Configuration refused; nothing was started."""


@dataclass(frozen=True)
class TargetConfig:
    mode: str = "simulated"
    client_path: Optional[str] = None
    data_dir: str = "data"
    display_required: bool = True


@dataclass(frozen=True)
class WorkerLimits:
    observation_max_age_seconds: int = 10
    dispatch_timeout_seconds: int = 30
    max_queue: int = 16
    tick_seconds: float = 1.0
    max_ticks: Optional[int] = None


@dataclass(frozen=True)
class HealthLimits:
    freeze_after_seconds: int = 30
    restart_budget: int = 3
    restart_window_seconds: int = 900
    ready_timeout_seconds: int = 60


@dataclass(frozen=True)
class ResourceLimits:
    rss_limit_bytes: int = 2 * 1024 ** 3
    disk_reserve_bytes: int = 1024 ** 3
    fd_limit: int = 2048
    cpu_limit_percent: float = 90.0
    snapshot_max_age_seconds: int = 30


@dataclass(frozen=True)
class NetworkConfig:
    required_route: str = "DIRECT"
    allow_direct_fallback: bool = False
    egress_allowlist: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token_ref: Optional[str] = None
    chat_ids: tuple[int, ...] = ()
    outbox_capacity: int = 32
    base_url: str = "https://api.telegram.org"
    allowed_hosts: tuple[str, ...] = ("api.telegram.org",)
    timeout_seconds: float = 10.0
    poll_timeout_seconds: int = 0
    approver_user_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class AIConfig:
    """Advisory-only provider (S07). ``enabled=false`` → FakeProvider / no calls."""
    enabled: bool = False
    api_key_ref: Optional[str] = None
    base_url: str = "https://api.openai.com"
    model: str = "gpt-4o-mini"
    allowed_hosts: tuple[str, ...] = ("api.openai.com",)
    timeout_seconds: float = 15.0
    max_calls: int = 20
    max_bytes: int = 200_000


@dataclass(frozen=True)
class AccountConfig:
    account_id: str = "acc_local001"
    alias: str = "alias:local"
    credential_ref: str = "ref:vault:acc_local001"
    auth_mode: str = "UNKNOWN"


@dataclass(frozen=True)
class ServiceConfig:
    config_hash: str
    policy_version: int = 1
    target: TargetConfig = field(default_factory=TargetConfig)
    worker: WorkerLimits = field(default_factory=WorkerLimits)
    health: HealthLimits = field(default_factory=HealthLimits)
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    account: AccountConfig = field(default_factory=AccountConfig)

    @property
    def store_path(self) -> Path:
        return Path(self.target.data_dir) / "store.sqlite"


# ------------------------------------------------------------------ helpers
def _scan_secrets(obj: Any, path: str = "") -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            _scan_secrets(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _scan_secrets(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if obj.startswith("ref:"):
            return
        for pat in _SECRET_PATTERNS:
            if pat.search(obj):
                raise ConfigError(f"{path}: secret-shaped literal refused; use a ref:... reference")
        # key=value style literals handled by the patterns; also refuse obvious raw-credential keys
    if isinstance(path, str) and path.rsplit(".", 1)[-1] in ("password", "passwd", "pin", "token", "secret", "bot_token"):
        raise ConfigError(f"{path}: raw credential keys are not allowed; use *_ref references")


def _section(raw: Mapping[str, Any], name: str, cls):
    data = raw.get(name, {})
    if not isinstance(data, Mapping):
        raise ConfigError(f"[{name}] must be a table")
    allowed = {f.name: f for f in fields(cls)}
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ConfigError(f"[{name}]: unknown keys {unknown}")
    kwargs = {}
    for key, value in data.items():
        if isinstance(value, list):
            value = tuple(value)
        kwargs[key] = value
    try:
        return cls(**kwargs)
    except TypeError as e:
        raise ConfigError(f"[{name}]: {e}") from e


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _validate(cfg: ServiceConfig) -> None:
    h = cfg.config_hash
    _require(isinstance(h, str) and len(h) == HEX64 and all(c in "0123456789abcdef" for c in h),
             "config_hash must be 64 lowercase hex characters")
    _require(_is_int(cfg.policy_version) and cfg.policy_version >= 1, "policy_version must be an integer >= 1")

    t = cfg.target
    _require(t.mode in MODES, f"target.mode must be one of {MODES}")
    _require(isinstance(t.data_dir, str) and t.data_dir.strip() != "", "target.data_dir must be a non-empty string")
    _require(isinstance(t.display_required, bool), "target.display_required must be a boolean")
    if t.mode == "device":
        _require(isinstance(t.client_path, str) and t.client_path.strip() != "",
                 "target.mode='device' requires target.client_path (ADR-007 pending; device mode is not runnable yet)")
    elif t.client_path is not None:
        _require(isinstance(t.client_path, str), "target.client_path must be a string")

    w = cfg.worker
    _require(_is_int(w.observation_max_age_seconds) and 1 <= w.observation_max_age_seconds <= 3600,
             "worker.observation_max_age_seconds must be in [1, 3600]")
    _require(_is_int(w.dispatch_timeout_seconds) and 1 <= w.dispatch_timeout_seconds <= 600,
             "worker.dispatch_timeout_seconds must be in [1, 600]")
    _require(_is_int(w.max_queue) and 1 <= w.max_queue <= 1024, "worker.max_queue must be in [1, 1024]")
    _require(isinstance(w.tick_seconds, (int, float)) and not isinstance(w.tick_seconds, bool)
             and 0.05 <= float(w.tick_seconds) <= 60.0, "worker.tick_seconds must be in [0.05, 60]")
    _require(w.max_ticks is None or (_is_int(w.max_ticks) and w.max_ticks >= 1), "worker.max_ticks must be >= 1 or absent")

    hl = cfg.health
    _require(_is_int(hl.freeze_after_seconds) and 1 <= hl.freeze_after_seconds <= 3600, "health.freeze_after_seconds in [1, 3600]")
    _require(_is_int(hl.restart_budget) and 0 <= hl.restart_budget <= 100, "health.restart_budget in [0, 100]")
    _require(_is_int(hl.restart_window_seconds) and 1 <= hl.restart_window_seconds <= 86400, "health.restart_window_seconds in [1, 86400]")
    _require(_is_int(hl.ready_timeout_seconds) and 1 <= hl.ready_timeout_seconds <= 3600, "health.ready_timeout_seconds in [1, 3600]")

    r = cfg.resources
    _require(_is_int(r.rss_limit_bytes) and r.rss_limit_bytes >= 64 * 1024 ** 2, "resources.rss_limit_bytes must be >= 64 MiB")
    _require(_is_int(r.disk_reserve_bytes) and r.disk_reserve_bytes >= 0, "resources.disk_reserve_bytes must be >= 0")
    _require(_is_int(r.fd_limit) and 16 <= r.fd_limit <= 1_000_000, "resources.fd_limit in [16, 1000000]")
    _require(isinstance(r.cpu_limit_percent, (int, float)) and not isinstance(r.cpu_limit_percent, bool)
             and 1.0 <= float(r.cpu_limit_percent) <= 100.0, "resources.cpu_limit_percent in [1, 100]")
    _require(_is_int(r.snapshot_max_age_seconds) and 1 <= r.snapshot_max_age_seconds <= 3600, "resources.snapshot_max_age_seconds in [1, 3600]")

    n = cfg.network
    _require(n.required_route in ROUTES, f"network.required_route must be one of {ROUTES}")
    _require(isinstance(n.allow_direct_fallback, bool), "network.allow_direct_fallback must be a boolean")
    _require(all(isinstance(x, str) and x for x in n.egress_allowlist), "network.egress_allowlist must be non-empty strings")

    tg = cfg.telegram
    _require(isinstance(tg.enabled, bool), "telegram.enabled must be a boolean")
    _require(_is_int(tg.outbox_capacity) and 1 <= tg.outbox_capacity <= 1024, "telegram.outbox_capacity in [1, 1024]")
    _require(all(_is_int(c) for c in tg.chat_ids), "telegram.chat_ids must be integers")
    if tg.enabled:
        _require(isinstance(tg.bot_token_ref, str) and tg.bot_token_ref.startswith("ref:"),
                 "telegram.enabled requires telegram.bot_token_ref = 'ref:...' (never the token)")
        _require(len(tg.chat_ids) >= 1, "telegram.enabled requires at least one chat id")
    elif tg.bot_token_ref is not None:
        _require(isinstance(tg.bot_token_ref, str) and tg.bot_token_ref.startswith("ref:"), "telegram.bot_token_ref must be a ref:...")
    _require(isinstance(tg.base_url, str) and tg.base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")),
             "telegram.base_url must be https:// (or a loopback http:// test server)")
    _require(all(isinstance(h, str) and h for h in tg.allowed_hosts) and len(tg.allowed_hosts) >= 1,
             "telegram.allowed_hosts must be a non-empty list of host names")
    _require(isinstance(tg.timeout_seconds, (int, float)) and not isinstance(tg.timeout_seconds, bool)
             and 1.0 <= float(tg.timeout_seconds) <= 60.0, "telegram.timeout_seconds in [1, 60]")
    _require(_is_int(tg.poll_timeout_seconds) and 0 <= tg.poll_timeout_seconds <= 50, "telegram.poll_timeout_seconds in [0, 50]")
    _require(all(_is_int(u) for u in tg.approver_user_ids), "telegram.approver_user_ids must be integers")

    ai = cfg.ai
    _require(isinstance(ai.enabled, bool), "ai.enabled must be a boolean")
    if ai.enabled:
        _require(isinstance(ai.api_key_ref, str) and ai.api_key_ref.startswith("ref:"),
                 "ai.enabled requires ai.api_key_ref = 'ref:...' (never the key)")
    elif ai.api_key_ref is not None:
        _require(isinstance(ai.api_key_ref, str) and ai.api_key_ref.startswith("ref:"), "ai.api_key_ref must be a ref:...")
    _require(isinstance(ai.base_url, str) and ai.base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")),
             "ai.base_url must be https:// (or a loopback http:// test server)")
    _require(isinstance(ai.model, str) and 1 <= len(ai.model) <= 128, "ai.model must be a short non-empty string")
    _require(all(isinstance(h, str) and h for h in ai.allowed_hosts) and len(ai.allowed_hosts) >= 1,
             "ai.allowed_hosts must be a non-empty list of host names")
    _require(isinstance(ai.timeout_seconds, (int, float)) and not isinstance(ai.timeout_seconds, bool)
             and 0.5 <= float(ai.timeout_seconds) <= 120.0, "ai.timeout_seconds in [0.5, 120]")
    _require(_is_int(ai.max_calls) and 0 <= ai.max_calls <= 10_000, "ai.max_calls in [0, 10000]")
    _require(_is_int(ai.max_bytes) and 0 <= ai.max_bytes <= 100_000_000, "ai.max_bytes in [0, 1e8]")

    a = cfg.account
    _require(isinstance(a.account_id, str) and a.account_id.startswith("acc_") and len(a.account_id) >= 7,
             "account.account_id must look like acc_<id>")
    _require(isinstance(a.alias, str) and a.alias.strip() != "", "account.alias must be a non-empty string")
    _require(isinstance(a.credential_ref, str) and a.credential_ref.startswith("ref:"),
             "account.credential_ref must be a ref:... reference (never a credential)")
    _require(a.auth_mode == "UNKNOWN", "account.auth_mode must remain 'UNKNOWN' until ADR-008 is decided by the owner")


# ------------------------------------------------------------------- public
def load_config_text(text: str) -> ServiceConfig:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML: {e}") from e
    _scan_secrets(raw)
    known = {"config_hash", "policy_version", "target", "worker", "health", "resources", "network", "telegram", "ai", "account"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"unknown top-level keys {unknown}")
    if "config_hash" not in raw:
        raise ConfigError("config_hash is required")
    cfg = ServiceConfig(
        config_hash=raw["config_hash"],
        policy_version=raw.get("policy_version", 1),
        target=_section(raw, "target", TargetConfig),
        worker=_section(raw, "worker", WorkerLimits),
        health=_section(raw, "health", HealthLimits),
        resources=_section(raw, "resources", ResourceLimits),
        network=_section(raw, "network", NetworkConfig),
        telegram=_section(raw, "telegram", TelegramConfig),
        ai=_section(raw, "ai", AIConfig),
        account=_section(raw, "account", AccountConfig),
    )
    _validate(cfg)
    return cfg


def load_config(path: str | Path) -> ServiceConfig:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read {p}: {e}") from e
    return load_config_text(text)


def example_toml() -> str:
    """The checked-in example (kept in one place so tests and docs agree)."""
    return (Path(__file__).resolve().parent.parent / "config.example.toml").read_text(encoding="utf-8")
