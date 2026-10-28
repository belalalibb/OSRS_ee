"""Command-line entry for the *local core only*.

What this CLI can do today (all offline, no game client, no Telegram, no AI provider):
  status      — report environment, schema/contract availability, store schema version
  validate    — validate a JSON document against a named contract
  store init  — create/open a SQLite store at a path and run recovery
  store show  — print accounts, active leases and journal phase counts
  demo        — run the end-to-end *simulated* loop (FakeAdapter/FakeTransport/FakeProvider)
                against a temporary store and print the journal; proves wiring, not the game
  target-check — inventory a candidate target machine (OS/Python/Java/client path/display/disk);
                launches nothing; lists what is still missing for S04b
  conformance — run the adapter conformance suite against the built-in FakeAdapter (or a
                recorded trace via --trace); the real S04b adapter will be run through the same suite
  replay      — replay a redacted JSONL adapter trace through the worker on a temp store;
                exercises worker logic on captured data without any client
  service     — run the supervised Service loop from a TOML config (S04c-local). Only
                target.mode="simulated" is accepted: FakeSupervisor + FakeAdapter, bounded by
                --max-ticks; mode="device" is refused (no real supervisor/adapter exists yet)

  config-check — load + validate a TOML config and print a redacted summary with the
                mode per component (SIMULATED / REAL / FAKE / DISABLED); exit 2 on refusal
  doctor      — component readiness: python/sqlite/jsonschema, /proc measurement, store
                path writable, which ref:env secrets are PRESENT (as booleans only), java,
                display; states what is SIMULATED vs real; launches nothing

What it deliberately does NOT do: launch a JVM/GUI/game client, log into any account.
Telegram/AI REAL components exist (S06b/S07b) but the `service` command builds them only
through osrs_ee.wiring with explicit opt-in (--allow-real-network + OSRS_EE_ALLOW_NETWORK=1
+ egress allowlist); by default everything network-facing is FAKE.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from osrs_ee import contracts

EXIT_OK, EXIT_INVALID, EXIT_ERROR = 0, 2, 1


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def cmd_status(_args: argparse.Namespace) -> int:
    import sqlite3
    info = {
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "contracts": sorted(contracts.CONTRACTS),
        "schema_dir": str(contracts.SCHEMA_DIR),
        "schema_dir_present": contracts.SCHEMA_DIR.is_dir(),
        "components": {
            "contracts/guards/canonical": "REAL (offline)",
            "store (SQLite)": "REAL (local file)",
            "worker/scheduler": "REAL logic; adapter is FAKE only",
            "telegram control plane": "REAL logic; transport is FAKE only",
            "ai advisor": "REAL logic; provider is FAKE only",
            "release/cache/admission/network policy": "REAL logic; measurements are injected",
            "adapter tooling (recording/replay/conformance/target-check)": "REAL (offline; S04a)",
            "service loop / config / supervisor boundary": "REAL logic (S04c-local); supervisor is FAKE only (launches nothing)",
            "game client adapter / JVM / GUI supervisor": "NOT IMPLEMENTED (S04b/S04c/S05; needs target machine + ADR-007/008)",
        },
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8") if args.file != "-" else sys.stdin.read()
    try:
        doc = contracts.loads_strict(text)
    except ValueError as e:
        print(f"INVALID JSON: {e}", file=sys.stderr)
        return EXIT_INVALID
    report = contracts.validate(args.contract, doc)
    if report.ok:
        print(f"VALID {args.contract}")
        return EXIT_OK
    for err in report.errors:
        print(f"INVALID {args.contract}: {err}", file=sys.stderr)
    return EXIT_INVALID


def cmd_store_init(args: argparse.Namespace) -> int:
    from osrs_ee.store import Store
    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with Store.open(path, now=_now()) as s:
        affected = s.recover(now=_now())
        print(json.dumps({"path": str(path), "integrity_ok": s.integrity_ok(), "recovered_accounts": affected}, ensure_ascii=False))
    return EXIT_OK


def cmd_store_show(args: argparse.Namespace) -> int:
    import sqlite3
    path = Path(args.path)
    if not path.exists():
        print(f"no store at {path}", file=sys.stderr)
        return EXIT_ERROR
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    out = {
        "schema_version": conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0],
        "accounts": [dict(r) for r in conn.execute("SELECT account_id, alias, auth_mode, state, state_version, session_epoch FROM accounts ORDER BY account_id")],
        "active_leases": [dict(r) for r in conn.execute("SELECT lease_id, account_id, session_epoch, expires_at FROM leases WHERE released_at IS NULL")],
        "journal_phases": {r["phase"]: r["n"] for r in conn.execute("SELECT phase, COUNT(*) n FROM commands GROUP BY phase")},
    }
    conn.close()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_demo(_args: argparse.Namespace) -> int:
    """Simulated end-to-end: Store + Worker(FakeAdapter) + Telegram(FakeTransport) + Advisor(FakeProvider)."""
    import tempfile
    from osrs_ee import advisor, telegram, worker
    from osrs_ee.store import Store

    t0 = _now()
    fixtures = contracts.SCHEMA_DIR.parent / "fixtures" / "valid"
    obs = json.loads((fixtures / "Observation" / "basic.json").read_text())
    intent = json.loads((fixtures / "CommandIntent" / "bank_withdraw.json").read_text())
    with tempfile.TemporaryDirectory() as d:
        s = Store.open(Path(d) / "demo.sqlite", now=t0)
        acc = "acc_demo001"
        s.create_account(acc, "demo", "UNKNOWN", "ref:vault:demo", now=t0)
        v = 0
        for state in ("PENDING_DISCOVERY", "DISCOVERING", "READY"):
            s.transition(acc, state, expected_version=v, reason="demo", now=t0)
            v += 1
        s.acquire_lease(acc, lease_id="lease_demo001", session_id="sess_demo001", client_instance_id="client_demo001",
                        expected_version=v, ttl_seconds=3600, now=t0)
        cfg_hash = "c" * 64
        obs.update(session_epoch=1, state_version=6, observed_at=t0.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for f in obs["fields"].values():
            f["observed_at"] = obs["observed_at"]
        intent.update(session_epoch=1, expected_state_version=6, config_hash=cfg_hash,
                      issued_at=t0.strftime("%Y-%m-%dT%H:%M:%SZ"), expires_at=(t0 + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        adapter = worker.FakeAdapter(obs).script(worker.AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_demo002",)))
        w = worker.Worker(s, adapter, acc, worker.WorkerConfig(config_hash=cfg_hash, policy_version=1))
        ctx = w.start(now=t0)
        w.enqueue(intent)
        step = w.step(now=t0 + timedelta(seconds=1))

        red = telegram.Redactor(aliases={acc: "alias:demo"})
        outbox = telegram.Outbox(telegram.FakeTransport(), red)
        outbox.enqueue(telegram.OutboundMessage(1, red.render("{a} step={o}", a=acc, o=step.outcome), "STATE"))
        delivered = outbox.flush(now=t0)

        adv = advisor.Advisor(advisor.FakeProvider().plan(json.loads((fixtures / "AIProposal" / "review.json").read_text()) | {
            "session_epoch": 1, "observed_state_version": 6}), red, advisor.Budget(max_calls=2, max_bytes=20000))
        advice = adv.advise(incident_id="incident_demo001", observation=obs, ctx=w.context(), consent=True, now=t0)

        w.request_abort()
        final = w.drain(now=t0 + timedelta(seconds=2))
        print(json.dumps({
            "mode": "SIMULATED (FakeAdapter/FakeTransport/FakeProvider) — proves wiring, not game behaviour",
            "worker_step": {"outcome": step.outcome, "phase": step.phase, "reason": step.reason_code},
            "telegram_delivered": delivered,
            "advice": {"accepted": advice.accepted, "action": advice.proposal["suggested_action"] if advice.proposal else None},
            "final_account_state": final,
            "journal": {r.command_id: r.phase for r in s.commands_in_phase(acc, ["VERIFIED", "UNKNOWN", "NOT_SENT", "REJECTED", "FAILED_VERIFIED"])},
        }, indent=2, ensure_ascii=False))
        s.close()
    return EXIT_OK


def cmd_target_check(args: argparse.Namespace) -> int:
    from osrs_ee.target_check import run_target_check
    rep = run_target_check(client_path=args.client, data_dir=args.data_dir, run_java_probe=not args.no_java_probe)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return EXIT_OK if rep.ready_for_s04b else EXIT_INVALID


def _demo_fixtures() -> tuple[dict, dict]:
    fixtures = contracts.SCHEMA_DIR.parent / "fixtures" / "valid"
    obs = json.loads((fixtures / "Observation" / "basic.json").read_text())
    intent = json.loads((fixtures / "CommandIntent" / "bank_withdraw.json").read_text())
    return obs, intent


def cmd_conformance(args: argparse.Namespace) -> int:
    from osrs_ee import worker
    from osrs_ee.adapters import ReplayAdapter, run_conformance
    t0 = _now()
    if args.trace:
        adapter = ReplayAdapter.from_file(Path(args.trace), strict=False)
        name = f"ReplayAdapter({args.trace})"
    else:
        obs, _ = _demo_fixtures()
        obs["observed_at"] = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
        for f in obs["fields"].values():
            f["observed_at"] = obs["observed_at"]
        adapter = worker.FakeAdapter(obs).script(worker.AdapterResponse("ACKNOWLEDGED", "VERIFIED", ("obs_probe",)))
        name = "FakeAdapter (built-in; proves the suite, not a client)"
    rep = run_conformance(adapter, now=t0, name=name)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return EXIT_OK if rep.passed else EXIT_INVALID


def cmd_replay(args: argparse.Namespace) -> int:
    """Drive the worker with a ReplayAdapter on a temporary store. The trace must be
    redacted (header.redacted == true); intents are rebuilt from the trace's dispatch records."""
    import tempfile
    from osrs_ee import worker
    from osrs_ee.adapters import ReplayAdapter, load_trace
    from osrs_ee.store import Store
    records = load_trace(Path(args.trace))
    adapter = ReplayAdapter(records, strict=True)
    first_obs = next(r for r in records if r["t"] == "observe")["observation"]
    dispatches = [r for r in records if r["t"] == "dispatch"]
    t0 = _now()
    acc = first_obs["account_id"]
    with tempfile.TemporaryDirectory() as d:
        s = Store.open(Path(d) / "replay.sqlite", now=t0)
        s.create_account(acc, "replay", "UNKNOWN", "ref:vault:replay", now=t0)
        v = 0
        for state in ("PENDING_DISCOVERY", "DISCOVERING", "READY"):
            s.transition(acc, state, expected_version=v, reason="replay", now=t0); v += 1
        lease_id = dispatches[0]["intent"]["lease_id"] if dispatches else "lease_replay01"
        session_id = dispatches[0]["intent"]["session_id"] if dispatches else "sess_replay01"
        s.acquire_lease(acc, lease_id=lease_id, session_id=session_id, client_instance_id=first_obs["client_instance_id"],
                        expected_version=v, ttl_seconds=3600, now=t0)
        cfg_hash = dispatches[0]["intent"]["config_hash"] if dispatches else "0" * 64
        w = worker.Worker(s, adapter, acc, worker.WorkerConfig(config_hash=cfg_hash, policy_version=1,
                                                               observation_max_age_seconds=10 ** 9))
        ctx = w.start(now=t0)
        results = []
        for rec in dispatches:
            intent = dict(rec["intent"])
            intent.update(session_epoch=ctx.session_epoch, expected_state_version=ctx.state_version,
                          issued_at=t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          expires_at=(t0 + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            w.enqueue(intent)
            step = w.step(now=t0 + timedelta(seconds=1))
            results.append({"command_id": step.command_id, "outcome": step.outcome, "phase": step.phase, "reason": step.reason_code})
            ctx = w.context()
        w.request_abort()
        final = w.drain(now=t0 + timedelta(seconds=2))
        print(json.dumps({"mode": "REPLAY (recorded, redacted trace; no client)", "trace": args.trace,
                          "served": {"observes": adapter.served_observes, "dispatches": adapter.served_dispatches},
                          "steps": results, "final_account_state": final}, indent=2, ensure_ascii=False))
        s.close()
    return EXIT_OK


def _redacted_config_summary(cfg) -> dict:
    """Summary safe to print: refs are shown as refs; no values of env vars ever appear."""
    return {
        "mode": "SIMULATED" if cfg.target.mode == "simulated" else cfg.target.mode.upper(),
        "config_hash": cfg.config_hash[:12] + "…", "policy_version": cfg.policy_version,
        "target": {"mode": cfg.target.mode, "client_path": cfg.target.client_path, "data_dir": cfg.target.data_dir,
                   "display_required": cfg.target.display_required},
        "worker": {"observation_max_age_seconds": cfg.worker.observation_max_age_seconds,
                   "dispatch_timeout_seconds": cfg.worker.dispatch_timeout_seconds, "max_queue": cfg.worker.max_queue,
                   "tick_seconds": cfg.worker.tick_seconds, "max_ticks": cfg.worker.max_ticks},
        "health": {"freeze_after_seconds": cfg.health.freeze_after_seconds, "restart_budget": cfg.health.restart_budget,
                   "restart_window_seconds": cfg.health.restart_window_seconds, "ready_timeout_seconds": cfg.health.ready_timeout_seconds},
        "resources": {"rss_limit_bytes": cfg.resources.rss_limit_bytes, "disk_reserve_bytes": cfg.resources.disk_reserve_bytes,
                      "fd_limit": cfg.resources.fd_limit, "cpu_limit_percent": cfg.resources.cpu_limit_percent},
        "network": {"required_route": cfg.network.required_route, "egress_allowlist": list(cfg.network.egress_allowlist)},
        "telegram": {"enabled": cfg.telegram.enabled, "bot_token_ref": cfg.telegram.bot_token_ref, "base_url": cfg.telegram.base_url,
                     "chat_ids": len(cfg.telegram.chat_ids), "approver_user_ids": len(cfg.telegram.approver_user_ids)},
        "ai": {"enabled": cfg.ai.enabled, "api_key_ref": cfg.ai.api_key_ref, "base_url": cfg.ai.base_url, "model": cfg.ai.model,
               "max_calls": cfg.ai.max_calls, "max_bytes": cfg.ai.max_bytes},
        "account": {"account_id": cfg.account.account_id, "alias": cfg.account.alias, "credential_ref": cfg.account.credential_ref,
                    "auth_mode": cfg.account.auth_mode},
    }


def _env_ref_present(ref, env) -> dict:
    """Never prints the value: only whether the referenced env var is set and non-empty."""
    if not ref:
        return {"ref": None, "present": False, "note": "no reference configured"}
    if not str(ref).startswith("ref:env:"):
        return {"ref": ref, "present": None, "note": "not an env ref; cannot be resolved by this build (ref:env:NAME only)"}
    name = str(ref)[len("ref:env:"):]
    return {"ref": ref, "present": bool(env.get(name))}


def cmd_config_check(args: argparse.Namespace) -> int:
    """Load, validate and summarise a config; build components in dry-run and report their modes."""
    import os
    from osrs_ee import wiring
    from osrs_ee.config import ConfigError, load_config
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"CONFIG REFUSED: {e}", file=sys.stderr)
        return EXIT_INVALID
    out = {"config": args.config, "status": "VALID", "summary": _redacted_config_summary(cfg),
           "secrets": {"telegram.bot_token_ref": _env_ref_present(cfg.telegram.bot_token_ref, os.environ),
                       "ai.api_key_ref": _env_ref_present(cfg.ai.api_key_ref, os.environ)},
           "components": None, "wiring_refusal": None,
           "runnable_by_service": cfg.target.mode == "simulated",
           "note": ("SIMULATED: supervisor/adapter are fakes; nothing is launched" if cfg.target.mode == "simulated"
                    else "mode=device is NOT runnable in this build (ADR-007/ADR-008 open)")}
    try:
        wd = wiring.build(cfg, allow_real_network=args.allow_real_network)
        out["components"] = wd.report()
    except wiring.WiringError as e:
        out["wiring_refusal"] = str(e)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return EXIT_OK if out["wiring_refusal"] is None else EXIT_INVALID


def cmd_doctor(args: argparse.Namespace) -> int:
    """Component readiness. Everything measured here is about THIS machine, not a target."""
    import os
    import shutil
    import sqlite3
    from osrs_ee import measure
    from osrs_ee.config import ConfigError, load_config
    checks: list[dict] = []

    def add(name, ok, detail, kind="REAL"):
        checks.append({"check": name, "ok": ok, "kind": kind, "detail": detail})

    add("python>=3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    add("sqlite3", True, sqlite3.sqlite_version)
    try:
        from importlib.metadata import version as _pkg_version
        add("jsonschema", True, _pkg_version("jsonschema"))
    except Exception:  # noqa: BLE001 - PackageNotFoundError or missing metadata
        add("jsonschema", False, "missing: pip install -e '.[dev]' / requirements.txt")
    add("contracts", contracts.SCHEMA_DIR.is_dir(), f"{len(contracts.CONTRACTS)} schemas at {contracts.SCHEMA_DIR}")
    add("/proc measurement", measure.proc_available(), "rss/fds/cpu/disk measurable" if measure.proc_available()
        else "not available: ResourceSnapshot cannot be measured on this host (Linux /proc required)")
    java = shutil.which("java")
    add("java on PATH", java is not None, java or "absent (needed only for a JVM client — ADR-007 pending)", kind="TARGET_ONLY")
    add("display", bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "DISPLAY/WAYLAND_DISPLAY set" if (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) else "no display (GUI client cannot run here)",
        kind="TARGET_ONLY")
    cfg = None
    if args.config:
        try:
            cfg = load_config(args.config)
            add("config", True, f"{args.config} valid; target.mode={cfg.target.mode}")
            data_dir = Path(cfg.target.data_dir)
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                probe = data_dir / ".doctor_write_probe"
                probe.write_text("ok"); probe.unlink()
                add("data_dir writable", True, str(data_dir))
            except OSError as e:
                add("data_dir writable", False, f"{data_dir}: {e}")
            free = measure.disk_free_bytes(str(data_dir))
            add("disk reserve", free is not None and free >= cfg.resources.disk_reserve_bytes,
                f"free={free} reserve={cfg.resources.disk_reserve_bytes}" if free is not None else "unmeasurable")
            add("secret telegram.bot_token_ref", True, _env_ref_present(cfg.telegram.bot_token_ref, os.environ), kind="PRESENCE_ONLY")
            add("secret ai.api_key_ref", True, _env_ref_present(cfg.ai.api_key_ref, os.environ), kind="PRESENCE_ONLY")
        except ConfigError as e:
            add("config", False, f"REFUSED: {e}")
    add("supervisor", True, "FakeSupervisor (simulated) + generic ProcessSupervisor (tested with a python child only); "
        "no game-client supervisor (ADR-007)", kind="SIMULATED")
    add("adapter", True, "FakeAdapter (simulated) + LoopbackReadOnlyAdapter (read-only, loopback endpoint, never dispatches); "
        "no real client adapter", kind="SIMULATED")
    add("telegram", True, "REAL transport exists (S06b-local, tested on 127.0.0.1 only); FAKE unless [telegram].enabled + opt-in flags",
        kind="REAL_UNVERIFIED_LIVE")
    add("ai", True, "REAL provider exists (S07b-local, tested on 127.0.0.1 only); FAKE unless [ai].enabled + opt-in flags",
        kind="REAL_UNVERIFIED_LIVE")
    required_ok = all(c["ok"] for c in checks if c["kind"] == "REAL")
    print(json.dumps({"host": "THIS machine (sandbox/dev), not a target", "ready_local": required_ok, "checks": checks,
                      "target_only_note": "java/display/client inventory belong to `osrs-ee target-check` on the owner's machine"},
                     indent=2, ensure_ascii=False, default=str))
    return EXIT_OK if required_ok else EXIT_INVALID


def cmd_service(args: argparse.Namespace) -> int:
    """Supervised loop from config. Simulated mode only; device mode is refused honestly."""
    import time
    from osrs_ee import service as sv
    from osrs_ee.config import ConfigError, load_config
    from osrs_ee.store import Store
    from osrs_ee.supervisor import FakeSupervisor
    from osrs_ee.worker import FakeAdapter
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"CONFIG REFUSED: {e}", file=sys.stderr)
        return EXIT_INVALID
    if cfg.target.mode != "simulated":
        print(f"REFUSED: target.mode={cfg.target.mode!r} is not runnable: no real client supervisor/adapter exists "
              "(S04b not implemented; ADR-007/ADR-008 open). Only mode='simulated' runs.", file=sys.stderr)
        return EXIT_INVALID
    from osrs_ee import wiring
    try:
        wd = wiring.build(cfg, allow_real_network=args.allow_real_network)
    except wiring.WiringError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_INVALID
    max_ticks = args.max_ticks if args.max_ticks is not None else cfg.worker.max_ticks
    if max_ticks is None:
        print("REFUSED: simulated service requires a bound: pass --max-ticks or set [worker].max_ticks (no unattended runs).",
              file=sys.stderr)
        return EXIT_INVALID
    Path(cfg.target.data_dir).mkdir(parents=True, exist_ok=True)
    from osrs_ee.lock import LockHeld, ServiceLock
    lock = ServiceLock(cfg.target.data_dir)
    try:
        lock.acquire()
    except LockHeld as e:
        print(f"REFUSED: {e}. One service per data_dir; stop the other instance first (never run two).", file=sys.stderr)
        return EXIT_INVALID
    t0 = _now()
    store = Store.open(cfg.store_path, now=t0)
    try:
        recovered = store.recover(now=t0)
        # Holding the exclusive lock proves no other service process is alive: any account
        # still in a session state with an active lease is an orphan of a dead process.
        orphaned = store.reconcile_orphaned_sessions(now=t0)
        state0 = sv.bootstrap_account(store, cfg, t0)
        obs = {
            "schema_version": "1.0", "observation_id": "obs_service001", "account_id": cfg.account.account_id,
            "client_instance_id": "client_service01", "session_epoch": 0, "observed_at": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state_version": 0, "consistency": "BEST_EFFORT", "fields": {},
        }
        tick = timedelta(seconds=cfg.worker.tick_seconds)
        clock_state = {"now": t0}

        def clock() -> datetime:
            clock_state["now"] += tick
            if not args.fast:
                time.sleep(cfg.worker.tick_seconds)
            return clock_state["now"]

        alert_chat = cfg.telegram.chat_ids[0] if cfg.telegram.chat_ids else 0
        svc = sv.Service(store, cfg, FakeAdapter(obs), FakeSupervisor(), wd.outbox, clock=clock, alert_chat_id=alert_chat)
        svc.install_signal_handlers()
        res = svc.run(max_ticks=max_ticks)
        print(json.dumps({
            "mode": "SIMULATED (FakeSupervisor/FakeAdapter; no client, no account)",
            "components": wd.report(),
            "egress_denied": wd.egress.denied(),
            "config": args.config, "store": str(cfg.store_path), "recovered_accounts": recovered,
            "orphaned_sessions_reconciled": orphaned, "lock": str(lock.path),
            "state_before": state0, "final_state": res.final_state, "ticks": res.ticks, "restarts": res.restarts,
            "stop_reason": res.stop_reason, "events": [{"tick": e.tick, "kind": e.kind, "detail": e.detail} for e in res.events],
        }, indent=2, ensure_ascii=False))
    finally:
        store.close()
        lock.release()
    return EXIT_OK


def cmd_secret_scan(args: argparse.Namespace) -> int:
    """Metadata-only secret-shape scan of a tree (default: cwd). Exit 2 when findings exist."""
    from osrs_ee import secret_scan as ss
    root = Path(args.path or ".")
    if not root.exists():
        print(f"no such path: {root}", file=sys.stderr)
        return EXIT_ERROR
    findings, n = ss.scan_path(root)
    perms: list[dict] = []
    if args.config:
        from osrs_ee.config import ConfigError, load_config
        try:
            cfg = load_config(args.config)
        except ConfigError as e:
            print(f"CONFIG REFUSED: {e}", file=sys.stderr)
            return EXIT_INVALID
        data = Path(cfg.target.data_dir)
        perms = ss.check_private_permissions(p for p in (data, cfg.store_path, data / "service.lock") if p.exists())
    print(json.dumps({
        "mode": "metadata-only (matched text is never printed)", "root": str(root), "files_scanned": n,
        "findings": [f.to_dict() for f in findings], "permission_issues": perms,
        "verdict": "CLEAN" if not findings and not perms else "REVIEW_REQUIRED",
    }, indent=2, ensure_ascii=False))
    return EXIT_OK if not findings and not perms else EXIT_INVALID


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="osrs-ee", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="environment and component status").set_defaults(fn=cmd_status)
    v = sub.add_parser("validate", help="validate a JSON file against a contract")
    v.add_argument("contract", choices=sorted(contracts.CONTRACTS))
    v.add_argument("file", help="path or - for stdin")
    v.set_defaults(fn=cmd_validate)
    st = sub.add_parser("store", help="local SQLite store operations").add_subparsers(dest="store_cmd", required=True)
    i = st.add_parser("init", help="create/open store and run recovery"); i.add_argument("path"); i.set_defaults(fn=cmd_store_init)
    sh = st.add_parser("show", help="print accounts/leases/journal"); sh.add_argument("path"); sh.set_defaults(fn=cmd_store_show)
    sub.add_parser("demo", help="simulated end-to-end loop on a temp store (no game, no network)").set_defaults(fn=cmd_demo)
    tc = sub.add_parser("target-check", help="inventory a target machine for S04b; launches nothing")
    tc.add_argument("--client", help="path to the game client (ADR-007)")
    tc.add_argument("--data-dir", help="directory for store/logs (disk check)")
    tc.add_argument("--no-java-probe", action="store_true", help="do not run `java -version`")
    tc.set_defaults(fn=cmd_target_check)
    cf = sub.add_parser("conformance", help="adapter conformance suite (FakeAdapter or --trace)")
    cf.add_argument("--trace", help="redacted JSONL trace to run the suite against")
    cf.set_defaults(fn=cmd_conformance)
    rp = sub.add_parser("replay", help="replay a redacted adapter trace through the worker (temp store)")
    rp.add_argument("trace")
    rp.set_defaults(fn=cmd_replay)
    se = sub.add_parser("service", help="supervised loop from TOML config; simulated mode only (S04c-local)")
    se.add_argument("--config", required=True, help="path to config.toml (see config.example.toml)")
    se.add_argument("--max-ticks", type=int, help="bound the run (required unless [worker].max_ticks is set)")
    se.add_argument("--fast", action="store_true", help="do not sleep between ticks (tests/demos)")
    se.add_argument("--allow-real-network", action="store_true",
                    help="permit REAL Telegram/AI components (also needs OSRS_EE_ALLOW_NETWORK=1 and egress allowlist)")
    se.set_defaults(fn=cmd_service)
    cc = sub.add_parser("config-check", help="validate a TOML config; print redacted summary and component modes")
    cc.add_argument("--config", required=True)
    cc.add_argument("--allow-real-network", action="store_true", help="evaluate wiring as if the service were run with this flag")
    cc.set_defaults(fn=cmd_config_check)
    dr = sub.add_parser("doctor", help="component readiness on THIS machine (SIMULATED vs real stated per item)")
    dr.add_argument("--config", help="optional config.toml to check data_dir/disk/secret presence")
    dr.set_defaults(fn=cmd_doctor)
    sc = sub.add_parser("secret-scan", help="metadata-only secret-shape scan of a tree (never prints values); exit 2 on findings")
    sc.add_argument("path", nargs="?", default=".", help="directory or file (default: .)")
    sc.add_argument("--config", help="also check data_dir/store/lock permissions (POSIX)")
    sc.set_defaults(fn=cmd_secret_scan)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
