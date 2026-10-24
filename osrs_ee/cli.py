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

What it deliberately does NOT do: launch a JVM/GUI/game client, log into any account,
talk to Telegram or an AI provider. Those components do not exist yet (see docs/ROADMAP.md,
docs/RUNBOOK.md §3). Any such subcommand would be a fake; none is provided.
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
    if cfg.telegram.enabled:
        print("REFUSED: telegram.enabled=true but no real transport exists in this build (S06b not implemented).", file=sys.stderr)
        return EXIT_INVALID
    max_ticks = args.max_ticks if args.max_ticks is not None else cfg.worker.max_ticks
    if max_ticks is None:
        print("REFUSED: simulated service requires a bound: pass --max-ticks or set [worker].max_ticks (no unattended runs).",
              file=sys.stderr)
        return EXIT_INVALID
    Path(cfg.target.data_dir).mkdir(parents=True, exist_ok=True)
    t0 = _now()
    store = Store.open(cfg.store_path, now=t0)
    try:
        recovered = store.recover(now=t0)
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

        svc = sv.Service(store, cfg, FakeAdapter(obs), FakeSupervisor(), None, clock=clock)
        svc.install_signal_handlers()
        res = svc.run(max_ticks=max_ticks)
        print(json.dumps({
            "mode": "SIMULATED (FakeSupervisor/FakeAdapter; no client, no account, no network)",
            "config": args.config, "store": str(cfg.store_path), "recovered_accounts": recovered,
            "state_before": state0, "final_state": res.final_state, "ticks": res.ticks, "restarts": res.restarts,
            "stop_reason": res.stop_reason, "events": [{"tick": e.tick, "kind": e.kind, "detail": e.detail} for e in res.events],
        }, indent=2, ensure_ascii=False))
    finally:
        store.close()
    return EXIT_OK


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
    se.set_defaults(fn=cmd_service)
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
