"""`hipstraw-mm` command line (contracts/cli.md, Constitution II).

Every step is its own subcommand. Errors always go to stderr with the exit codes from the contract;
with `--json`, stdout also carries one JSON object including an `error` field.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn, TextIO

from dotenv import load_dotenv

from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient, LLMSchemaError
from hipstraw_mm.adapters.replay import ReplayMissingError, ReplayStore, mode_from_env
from hipstraw_mm.adapters.search import BraveSearch
from hipstraw_mm.config import LoadedConfig, load_config
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.errors import ExternalServiceError, HipstrawError, PreconditionError, UsageError
from hipstraw_mm.logging_setup import EventLog, scrub
from hipstraw_mm.steps.candidates import candidates
from hipstraw_mm.steps.discover import discover
from hipstraw_mm.steps.intake import intake
from hipstraw_mm.steps.position import position
from hipstraw_mm.steps.report import report
from hipstraw_mm.steps.review import review
from hipstraw_mm.steps.verify import verify
from hipstraw_mm.store.base import InvalidTransitionError, NotFoundError

COMMANDS = ("intake", "candidates", "position", "discover", "verify", "review", "report", "run", "show")
MARKET_COMMANDS = (
    "start", "vichara", "meaning", "graph", "validate", "links",
    "beam", "assess", "companies", "buyers", "decide", "report", "run", "show",
)


def build_context(config: LoadedConfig) -> Context:
    """The real context: emulator-only Firestore, live (or recorded) adapters."""
    from hipstraw_mm.store.firestore import FirestoreStore, check_emulator_preconditions, check_emulator_reachable

    project_id = os.environ.get("HIPSTRAW_PROJECT_ID") or config.run.projectId
    check_emulator_preconditions(project_id)
    check_emulator_reachable()
    mode = mode_from_env()
    replay_dir = os.environ.get("HIPSTRAW_REPLAY_DIR")
    if mode != "off" and not replay_dir:
        raise PreconditionError("HIPSTRAW_REPLAY_DIR must be set when HIPSTRAW_REPLAY is 'replay' or 'record'")
    replay = ReplayStore(Path(replay_dir) if replay_dir else None, mode=mode)
    log = EventLog(runs_dir=Path(".runs"))
    policy = config.source_policy
    fetch = config.run.fetch

    def new_fetcher() -> Fetcher:
        return Fetcher(
            replay_store=replay,
            denylist_domains=policy.denylistDomains,
            user_agent=policy.userAgent,
            timeout_seconds=fetch.timeoutSeconds,
            max_bytes=fetch.maxBytes,
            per_host_delay_seconds=fetch.perHostDelaySeconds,
        )

    return Context(
        config=config,
        store=FirestoreStore(project_id),
        log=log,
        llm=LLMClient(model=config.run.model.name, replay=replay, log=log),
        search=BraveSearch(replay, denylist_domains=policy.denylistDomains, timeout_seconds=fetch.timeoutSeconds),
        new_fetcher=new_fetcher,
    )


def build_memory_context(config: LoadedConfig) -> Context:
    """In-memory context: no Firestore emulator needed, data lives only for this process."""
    from hipstraw_mm.store.memory import MemoryStore

    mode = mode_from_env()
    replay_dir = os.environ.get("HIPSTRAW_REPLAY_DIR")
    if mode != "off" and not replay_dir:
        raise PreconditionError("HIPSTRAW_REPLAY_DIR must be set when HIPSTRAW_REPLAY is 'replay' or 'record'")
    replay = ReplayStore(Path(replay_dir) if replay_dir else None, mode=mode)
    log = EventLog(runs_dir=Path(".runs"))
    policy = config.source_policy
    fetch = config.run.fetch

    def new_fetcher() -> Fetcher:
        return Fetcher(
            replay_store=replay,
            denylist_domains=policy.denylistDomains,
            user_agent=policy.userAgent,
            timeout_seconds=fetch.timeoutSeconds,
            max_bytes=fetch.maxBytes,
            per_host_delay_seconds=fetch.perHostDelaySeconds,
        )

    return Context(
        config=config,
        store=MemoryStore(),
        log=log,
        llm=LLMClient(model=config.run.model.name, replay=replay, log=log),
        search=BraveSearch(replay, denylist_domains=policy.denylistDomains, timeout_seconds=fetch.timeoutSeconds),
        new_fetcher=new_fetcher,
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.prog}: {message}")


def build_parser() -> argparse.ArgumentParser:
    common = _Parser(add_help=False)
    common.add_argument("--config-dir", default="config", help="config directory (default: ./config)")
    common.add_argument("--json", action="store_true", help="print one JSON object on stdout")
    common.add_argument("--memory", action="store_true", help="use in-memory store (no Firestore emulator needed)")

    # The same flags again for `market <stage>`; SUPPRESS keeps a value given before `market` from being reset.
    common_after = _Parser(add_help=False)
    common_after.add_argument("--config-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common_after.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common_after.add_argument("--memory", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    parser = _Parser(prog="hipstraw-mm", description="Find and review target companies for one micro-market.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    p = sub.add_parser("intake", parents=[common], help="load a program config into the store")
    p.add_argument("--program", default="invoice_alpha")

    p = sub.add_parser("candidates", parents=[common], help="copy the program's experiment contexts")
    p.add_argument("--program", required=True, help="program ID, e.g. invoice_alpha_genesis")

    p = sub.add_parser("position", parents=[common], help="create a run from a first-position file")
    p.add_argument("--candidate", required=True)
    p.add_argument("--file", required=True)

    for name, help_text in [
        ("discover", "find companies for a run"),
        ("verify", "check websites and extract cited evidence"),
        ("review", "Market Manager Review: dispositions and baseline"),
        ("show", "print a run's status, counts, and dispositions"),
    ]:
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.add_argument("--run", required=True)

    p = sub.add_parser("report", parents=[common], help="write the markdown demo report")
    p.add_argument("--run", required=True)
    p.add_argument("--out", default=None, help="output directory (default: reports/)")

    p = sub.add_parser("run", parents=[common], help="position, discover, verify, review, report")
    p.add_argument("--candidate", required=True)
    p.add_argument("--file", required=True)

    # --- feature 003: market command group ---
    market = sub.add_parser("market", parents=[common], help="traced market discovery pipeline")
    msub = market.add_subparsers(dest="market_command", required=True, parser_class=_Parser)

    p = msub.add_parser("start", parents=[common_after], help="open a market run from a program")
    p.add_argument("--program", required=True, help="program ID")
    p.add_argument(
        "--objective-pdf", action="append", default=[], metavar="PATH",
        help="objective document (PDF) to add to the run's objective; repeat for several",
    )

    for name, help_text in [
        ("vichara", "deliberate dimensions"),
        ("meaning", "record graph meaning"),
        ("graph", "generate seed graph"),
        ("validate", "validate seed graph"),
        ("links", "verify links"),
        ("beam", "beam search"),
        ("assess", "assess paths"),
        ("companies", "discover companies per path"),
        ("buyers", "identify buyer roles"),
        ("decide", "market manager decisions"),
    ]:
        p = msub.add_parser(name, parents=[common_after], help=help_text)
        p.add_argument("--run", required=True)

    p = msub.add_parser("report", parents=[common_after], help="render market report")
    p.add_argument("--run", required=True)
    p.add_argument("--out", default=None)

    p = msub.add_parser("run", parents=[common_after], help="start through report")
    p.add_argument("--program", required=True)
    p.add_argument(
        "--objective-pdf", action="append", default=[], metavar="PATH",
        help="objective document (PDF) to add to the run's objective; repeat for several",
    )
    p.add_argument("--serve", action="store_true", help="serve the viewer from this process while the run goes")
    p.add_argument("--port", type=int, default=8765, help="viewer port for --serve")

    p = msub.add_parser("show", parents=[common_after], help="print run status and counts")
    p.add_argument("--run", required=True)

    # --- feature 003: view command ---
    p = sub.add_parser("view", parents=[common], help="start the read-only trace viewer")
    p.add_argument("--port", type=int, default=8765)

    return parser


def _not_implemented(ctx: Context, args: argparse.Namespace) -> CommandResult:
    raise UsageError(f"'{args.command}' is not implemented yet")


def _market_not_implemented(ctx: Context, args: argparse.Namespace) -> CommandResult:
    raise UsageError(f"'market {args.market_command}' is not implemented yet")


def _run(ctx: Context, args: argparse.Namespace) -> CommandResult:
    """position, discover, verify, review, report; the first failure stops it with the run marked failed."""
    created = position(ctx, args.candidate, args.file)
    run_id = str(created.runId)
    results = [
        discover(ctx, run_id),
        verify(ctx, run_id),
        review(ctx, run_id),
        report(ctx, run_id),
    ]
    last = results[-1]
    warnings = list(dict.fromkeys(w for r in results for w in r.warnings))
    return CommandResult(
        "run", message=last.message, runId=run_id, status=last.status, counts=last.counts, warnings=warnings
    )


def _market_start(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.market.objective import resolve_pdf_paths
    from hipstraw_mm.market.start import market_start

    run_id = market_start(ctx, args.program, resolve_pdf_paths(args.objective_pdf))
    run = ctx.store.get_market_run(run_id)
    return CommandResult(
        "market start",
        message=f"opened {run_id}",
        runId=run_id,
        status=run["status"] if run else "opened",
        counts=run.get("counts") if run else None,
    )


def _market_show(ctx: Context, args: argparse.Namespace) -> CommandResult:
    run = ctx.store.get_market_run(args.run)
    if run is None:
        raise PreconditionError(f"market run {args.run!r} not found")
    return CommandResult(
        "market show",
        message=f"{run['marketRunId']}  status={run['status']}  steps={run.get('lastSeq', 0)}",
        runId=run["marketRunId"],
        status=run["status"],
        counts=run.get("counts"),
    )


def _market_dispatch(ctx: Context, args: argparse.Namespace) -> CommandResult:
    handler = MARKET_HANDLERS.get(args.market_command, _market_not_implemented)
    return handler(ctx, args)


def _view(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.viewer.server import ViewerServer, as_read_store

    store = as_read_store(ctx.store)
    server = ViewerServer(store, port=args.port)
    host, port = str(server.server_address[0]), server.server_address[1]
    print(f"viewer: http://{host}:{port}/", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return CommandResult("view", message="viewer stopped")


def _market_meaning(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.market.meaning import record_meaning
    from hipstraw_mm.market.stages import load_run, make_tracer

    run_id = args.run
    load_run(ctx, run_id, "deliberated")
    record_meaning(ctx.store, make_tracer(ctx, run_id, Path(args.config_dir)), run_id)
    ctx.store.transition_market_run(run_id, "deliberated", "defined")
    return CommandResult("market meaning", message="graph meaning recorded", runId=run_id, status="defined")


def _market_validate(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.market.layers import load_layers
    from hipstraw_mm.market.meaning import load_graph_meaning
    from hipstraw_mm.market.settings import load_pipeline_settings
    from hipstraw_mm.market.trace import Tracer
    from hipstraw_mm.market.validate import validate_graph_structure

    run_id = args.run
    run = ctx.store.get_market_run(run_id)
    if run is None:
        raise PreconditionError(f"market run {run_id!r} not found")
    if run.get("status") != "graphed":
        raise PreconditionError(f"market run {run_id!r} is '{run.get('status')}', expected 'graphed'")
    graphs = ctx.store.list_seed_graphs(run_id)
    if not graphs:
        raise PreconditionError(f"market run {run_id!r} has no seed graph")
    graph = graphs[-1]
    config_dir = Path(args.config_dir)
    meaning = load_graph_meaning(config_dir)
    layers = load_layers(config_dir)
    settings = load_pipeline_settings(config_dir)
    tracer = Tracer(store=ctx.store, layers=layers, settings=settings, run_id=run_id)
    with tracer.step("search_research", "graph_validator", "validate_graph") as step_ctx:
        step_ctx.set_inputs({"graphId": graph.get("graphId"), "version": graph.get("version")})
        violations = validate_graph_structure(graph, meaning)
        step_ctx.set_outputs({"violationCount": len(violations), "violations": violations})
        step_ctx.set_decision("valid" if not violations else "violations_found")
    if violations:
        return CommandResult(
            "market validate",
            message=f"{len(violations)} structural violation(s) in {run_id}",
            runId=run_id,
            status=run["status"],
            warnings=[f"{v['rule']}: {v['reason']}" for v in violations],
        )
    ctx.store.transition_market_run(run_id, "graphed", "validated")
    return CommandResult("market validate", message=f"graph valid for {run_id}", runId=run_id, status="validated")


def _stage_handler(
    name: str, status: str, summary: Callable[[dict[str, Any]], str]
) -> Callable[[Context, argparse.Namespace], CommandResult]:
    def handler(ctx: Context, args: argparse.Namespace) -> CommandResult:
        from hipstraw_mm.market import stages

        result = getattr(stages, f"stage_{name}")(ctx, args.run, Path(args.config_dir))
        return CommandResult(f"market {name}", message=summary(result), runId=args.run, status=status)

    return handler


def _market_decide(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from datetime import datetime, timezone

    from hipstraw_mm.market.decide import compute_market_status, decide_path, unassessed_dimensions
    from hipstraw_mm.market.layers import load_layers
    from hipstraw_mm.market.settings import load_pipeline_settings
    from hipstraw_mm.market.trace import Tracer

    run_id = args.run
    run = ctx.store.get_market_run(run_id)
    if run is None:
        raise PreconditionError(f"market run {run_id!r} not found")
    if run.get("status") != "roled":
        raise PreconditionError(f"market run {run_id!r} is '{run.get('status')}', expected 'roled'")
    config_dir = Path(args.config_dir)
    tracer = Tracer(
        store=ctx.store, layers=load_layers(config_dir), settings=load_pipeline_settings(config_dir), run_id=run_id
    )
    # The manager sees only final paths, their evaluations, and the run summary (FR-002).
    finals = [p for p in ctx.store.list_paths(run_id) if p.get("isFinal")]
    companies = ctx.store.list_market_companies(run_id)
    decided: list[dict[str, Any]] = []
    for path in finals:
        pid = path["pathId"]
        linked = [
            {"disposition": link.get("disposition"), "verified": link.get("disposition") == "include"}
            for c in companies for link in c.get("links", []) if link.get("pathId") == pid
        ]
        view = {
            "companies": linked,
            "sufficiency": path.get("evidenceStates", {}).get("sufficiency", "insufficient"),
            "canStillFill": bool(path.get("canStillFill")),
        }
        with tracer.step("market_manager", "market_manager", "decide_path", right="decide_path") as step_ctx:
            step_ctx.set_inputs({"pathId": pid, **view})
            result = decide_path(view)
            step_ctx.set_outputs(result)
            step_ctx.set_decision(result["decision"])
            ctx.store.create_path_decision({
                "marketRunId": run_id, "pathId": pid, **result,
                "inputs": view, "decidedAt": datetime.now(timezone.utc).isoformat(),
            })
        decided.append({"pathId": pid, "decision": result["decision"]})
    with tracer.step("market_manager", "market_manager", "set_market_status", right="set_market_status") as step_ctx:
        status = compute_market_status(decided)
        step_ctx.set_inputs({"decisions": decided})
        step_ctx.set_outputs(status)
        step_ctx.set_decision(status["state"])
    market_status = {**status, "decidedAt": datetime.now(timezone.utc).isoformat()}
    ctx.store.transition_market_run(
        run_id, "roled", "decided", {"marketStatus": market_status, "unassessed": unassessed_dimensions()}
    )
    return CommandResult(
        "market decide",
        message=f"{len(decided)} decision(s); market status {status['state']}",
        runId=run_id,
        status="decided",
    )


def _market_report(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.market.layers import load_layers
    from hipstraw_mm.market.report import write_market_report
    from hipstraw_mm.market.settings import load_pipeline_settings
    from hipstraw_mm.market.trace import Tracer

    run_id = args.run
    run = ctx.store.get_market_run(run_id)
    if run is None:
        raise PreconditionError(f"market run {run_id!r} not found")
    if run.get("status") != "decided":
        raise PreconditionError(f"market run {run_id!r} is '{run.get('status')}', expected 'decided'")
    config_dir = Path(args.config_dir)
    tracer = Tracer(
        store=ctx.store, layers=load_layers(config_dir), settings=load_pipeline_settings(config_dir), run_id=run_id
    )
    out = write_market_report(ctx.store, tracer, run_id, Path(args.out) if args.out else None)
    ctx.store.transition_market_run(run_id, "decided", "reported")
    return CommandResult("market report", message=f"report written to {out}", runId=run_id, status="reported")


def _beam_summary(r: dict[str, Any]) -> str:
    text = f"{r['finalPaths']} final, {r['deferred']} deferred"
    return text + (f" (shortfall: {r['shortfall']['reason']})" if r["shortfall"] else "")


PIPELINE_STAGES = (
    "vichara", "meaning", "graph", "validate", "links", "beam", "assess", "companies", "buyers", "decide", "report",
)


def _start_viewer(ctx: Context, port: int) -> Any:
    import threading

    from hipstraw_mm.viewer.server import ViewerServer, as_read_store

    server = ViewerServer(as_read_store(ctx.store), port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"viewer: http://{server.server_address[0]!s}:{server.server_address[1]}/", file=sys.stderr)
    return server


def _market_run_pipeline(ctx: Context, args: argparse.Namespace) -> CommandResult:
    """start, then every stage in order. The first failure marks the run failed and stops."""
    import time

    from hipstraw_mm.market.objective import resolve_pdf_paths
    from hipstraw_mm.market.start import market_start

    server = _start_viewer(ctx, args.port) if args.serve else None
    run_id = ""
    error: Exception | None = None
    try:
        run_id = market_start(ctx, args.program, resolve_pdf_paths(args.objective_pdf))
        print(f"{run_id}: opened", file=sys.stderr)
        stage_args = argparse.Namespace(run=run_id, config_dir=args.config_dir, out=None)
        for stage in PIPELINE_STAGES:
            try:
                result = MARKET_HANDLERS[stage](ctx, stage_args)
                if stage == "validate" and result.status != "validated":
                    raise PreconditionError("the seed graph failed validation: " + "; ".join(result.warnings[:5]))
            except Exception as exc:
                run = ctx.store.get_market_run(run_id) or {}
                with contextlib.suppress(Exception):
                    ctx.store.transition_market_run(
                        run_id, run.get("status", "opened"), "failed",
                        {"errorStage": stage, "errorMessage": scrub(str(exc) or type(exc).__name__)},
                    )
                raise
            print(f"{run_id}: {result.status} ({stage}) {result.message}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - re-raised after the viewer has had a chance to show the failure
        error = exc
    if server is not None:
        print("viewer is still running; press Ctrl+C to stop", file=sys.stderr)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.shutdown()
    if error is not None:
        raise error
    return CommandResult("market run", message=f"pipeline complete: {run_id}", runId=run_id, status="reported")


MARKET_HANDLERS: dict[str, Callable[[Context, argparse.Namespace], CommandResult]] = {
    "start": _market_start,
    "vichara": _stage_handler(
        "vichara", "deliberated", lambda r: f"{r['dimensions']} dimensions, {r['unresolved']} unresolved"
    ),
    "meaning": _market_meaning,
    "graph": _stage_handler("graph", "graphed", lambda r: f"{r['nodes']} nodes, {r['edges']} edges"),
    "validate": _market_validate,
    "links": _stage_handler("links", "linked", lambda r: f"{r['links']} links, {r['flagged']} flagged"),
    "beam": _stage_handler("beam", "searched", _beam_summary),
    "assess": _stage_handler("assess", "assessed", lambda r: f"{r['assessedPaths']} paths assessed"),
    "companies": _stage_handler(
        "companies", "verified",
        lambda r: f"{r['companies']} companies ({r['included']} included) across {r['paths']} paths",
    ),
    "buyers": _stage_handler("buyers", "roled", lambda r: f"{r['roles']} buyer roles across {r['paths']} paths"),
    "decide": _market_decide,
    "report": _market_report,
    "run": _market_run_pipeline,
    "show": _market_show,
}

HANDLERS: dict[str, Callable[[Context, argparse.Namespace], CommandResult]] = {
    "intake": lambda ctx, a: intake(ctx, a.program),
    "candidates": lambda ctx, a: candidates(ctx, a.program),
    "position": lambda ctx, a: position(ctx, a.candidate, a.file),
    "discover": lambda ctx, a: discover(ctx, a.run),
    "verify": lambda ctx, a: verify(ctx, a.run),
    "review": lambda ctx, a: review(ctx, a.run),
    "report": lambda ctx, a: report(ctx, a.run, Path(a.out) if a.out else None),
    "run": _run,
    "show": _not_implemented,  # T071, after the demo
    "market": _market_dispatch,
    "view": _view,
}


_HANDLED = (HipstrawError, InvalidTransitionError, NotFoundError, LLMSchemaError, ReplayMissingError)


def _error_code(exc: Exception) -> int:
    if isinstance(exc, HipstrawError):
        return exc.exit_code
    if isinstance(exc, (InvalidTransitionError, NotFoundError)):
        return PreconditionError.exit_code
    return ExternalServiceError.exit_code


def main(
    argv: list[str] | None = None,
    *,
    context_factory: Callable[[LoadedConfig], Context] = build_context,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    load_dotenv()
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    command = "hipstraw-mm"
    json_mode = "--json" in (argv if argv is not None else sys.argv[1:])
    try:
        args = build_parser().parse_args(argv)
        command, json_mode = args.command, args.json
        factory = build_memory_context if args.memory else context_factory
        ctx = factory(load_config(Path(args.config_dir)))
        if args.memory and command == "market":
            for program_file in sorted((Path(args.config_dir) / "programs").glob("*.yaml")):
                intake(ctx, program_file.stem)
        result = HANDLERS[command](ctx, args)
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    except _HANDLED as exc:
        code = _error_code(exc)
        message = scrub(str(exc) or type(exc).__name__)
        print(f"error: {message}", file=err)
        if json_mode:
            print(json.dumps({"command": command, "error": {"code": code, "message": message}}), file=out)
        return code

    if json_mode:
        print(json.dumps(result.to_json()), file=out)
    else:
        if result.message:
            print(result.message, file=out)
        for warning in result.warnings:
            print(f"warning: {warning}", file=err)
    return 0
