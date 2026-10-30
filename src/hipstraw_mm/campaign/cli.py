"""`hipstraw-mm campaign ...` (specs/004-campaign-readiness-g0/contracts/cli.md).

Dispatched by the top-level CLI before the market context is built, so campaign commands need no
Firestore, search key or market program.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.context import CommandResult

Handler = Callable[[argparse.Namespace], CommandResult]
HANDLERS: dict[str, Handler] = {}


def _command(name: str) -> Callable[[Handler], Handler]:
    def wrap(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return wrap


def register(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
    common: argparse.ArgumentParser,
    common_after: argparse.ArgumentParser,
    parser_class: type[argparse.ArgumentParser],
) -> None:
    group = sub.add_parser("campaign", parents=[common], help="Hipstraw G0 campaign strategy and readiness testing")
    group.add_argument("--db", default=None, help="database file (default: $HIPSTRAW_CAMPAIGN_DB or .runs/campaign.db)")
    csub = group.add_subparsers(dest="campaign_command", required=True, parser_class=parser_class)

    csub.add_parser("lint", parents=[common_after], help="load the repertoire and run the Line lint")

    p = csub.add_parser("submit", parents=[common_after], help="launch intake: mandate, evidence, Position v1")
    p.add_argument("--file", required=True, help="launch file (YAML)")
    _actor(p)

    p = csub.add_parser("amend", parents=[common_after], help="record a new mandate version")
    p.add_argument("--launch", required=True)
    p.add_argument("--file", required=True)
    _actor(p)

    p = csub.add_parser("show", parents=[common_after], help="launch status: mandate, Position, Lines, Reviews")
    p.add_argument("--launch", required=True)

    p = csub.add_parser("lines", parents=[common_after], help="which Lines fit this launch, and why")
    p.add_argument("--launch", required=True)

    p = csub.add_parser("choose", parents=[common_after], help="choose a Line; opens the tactic record")
    p.add_argument("--launch", required=True)
    p.add_argument("--line", required=True)
    p.add_argument("--reason", required=True)
    _actor(p)

    for name, help_text in (("step", "run the next stage of a Line"), ("run", "run every remaining stage")):
        p = csub.add_parser(name, parents=[common_after], help=help_text)
        p.add_argument("--line-run", required=True)
        _actor(p)

    p = csub.add_parser("deviate", parents=[common_after], help="skip or add a Move before the next stage")
    p.add_argument("--line-run", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--skip", metavar="MOVE")
    group.add_argument("--add", metavar="MOVE")
    p.add_argument("--stage", type=int, default=None, help="stage number (1-based); default: the next stage")
    p.add_argument("--reason", required=True)
    _actor(p)

    p = csub.add_parser("stop", parents=[common_after], help="stop the Line; its Review covers what ran")
    p.add_argument("--line-run", required=True)
    p.add_argument("--reason", required=True)
    _actor(p)

    p = csub.add_parser("report", parents=[common_after], help="the readiness report from the accepted Position")
    p.add_argument("--launch", required=True)
    p.add_argument("--out", default=None, help="default: reports/<launch>_readiness.md")

    p = csub.add_parser("view", parents=[common_after], help="serve the read-only campaign page on 127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p = csub.add_parser("console", parents=[common_after],
                        help="serve the campaign page with its approved actions (submit, review, accept) on 127.0.0.1")
    p.add_argument("--port", type=int, default=8766)

    rp = csub.add_parser("review", parents=[common_after], help="the review queue: show, finding, validate, accept")
    rsub = rp.add_subparsers(dest="review_command", required=True, parser_class=parser_class)
    p = rsub.add_parser("show", parents=[common_after], help="a Review with its findings")
    p.add_argument("--review", required=True)
    p = rsub.add_parser("finding", parents=[common_after], help="accept, reject or correct one finding")
    p.add_argument("--review", required=True)
    p.add_argument("--finding", required=True)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--accept", action="store_true")
    action.add_argument("--reject", action="store_true")
    action.add_argument("--correct", metavar="TEXT")
    p.add_argument("--verdict", choices=["met", "partly", "not_met", "unknown"], default=None,
                   help="with --correct on a rubric finding: the reviewer's verdict")
    p.add_argument("--reason", required=True)
    _actor(p)
    p = rsub.add_parser("validate", parents=[common_after], help="the reviewer validates a drafted Review")
    p.add_argument("--review", required=True)
    _actor(p)
    p = rsub.add_parser("accept", parents=[common_after], help="the Sponsor accepts; commits the next Position")
    p.add_argument("--review", required=True)
    p.add_argument("--reason", default=None)
    _actor(p)
    p = rsub.add_parser("reject", parents=[common_after], help="the Sponsor rejects a validated Review")
    p.add_argument("--review", required=True)
    p.add_argument("--reason", required=True)
    _actor(p)


def _actor(p: argparse.ArgumentParser) -> None:
    p.add_argument("--by", required=True, help="name of the person acting")
    p.add_argument("--as", dest="role", required=True, help="role: sponsor, campaign_manager or reviewer")


def dispatch(args: argparse.Namespace) -> CommandResult:
    return HANDLERS[args.campaign_command](args)


def _config_dir(args: argparse.Namespace) -> Path:
    return Path(args.config_dir)


def _store(args: argparse.Namespace) -> SqliteCampaignStore:
    return SqliteCampaignStore(args.db)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@_command("lint")
def _lint(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.repertoire import load_repertoire

    rep = load_repertoire(_config_dir(args))
    return CommandResult(
        "campaign lint", status="ok",
        message=f"{rep.version}: {len(rep.moves)} Moves, {len(rep.lines)} Lines, no lint errors",
        counts={"moves": len(rep.moves), "lines": len(rep.lines)},
        data={"repertoireVersion": rep.version, "errors": []},
    )


@_command("submit")
def _submit(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.intake import submit_launch

    r = submit_launch(_store(args), _config_dir(args), Path(args.file), by=args.by, role=args.role, now=_now())
    counts = ", ".join(f"{n} {kind}" for kind, n in sorted(r.items.items()))
    return CommandResult(
        "campaign submit", runId=r.launchId, status="proposed",
        message=f"{r.launchId}: mandate v1, {r.evidence} evidence records, Position v1 proposed ({counts})",
        data={"launchId": r.launchId, "mandateVersion": r.mandateVersion, "evidence": r.evidence,
              "positionVersion": r.positionVersion, "items": r.items},
    )


@_command("amend")
def _amend(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.intake import amend_mandate

    r = amend_mandate(_store(args), _config_dir(args), args.launch, Path(args.file), by=args.by, role=args.role,
                      now=_now())
    return CommandResult(
        "campaign amend", runId=r.launchId, status="amended",
        message=f"{r.launchId}: mandate v{r.mandateVersion}, {r.evidence} new evidence records",
        data={"launchId": r.launchId, "mandateVersion": r.mandateVersion, "evidence": r.evidence},
    )


@_command("show")
def _show(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.status import launch_summary, summary_text

    summary = launch_summary(_store(args), args.launch)
    return CommandResult("campaign show", runId=args.launch, message=summary_text(summary), data=summary)


@_command("lines")
def _lines(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.selection import recommend_for_launch

    rec = recommend_for_launch(_store(args), _config_dir(args), args.launch, _now())
    text = [f"{args.launch}: Position v{rec.positionVersion}"]
    for label, choices in (("eligible", rec.eligible), ("excluded", rec.excluded)):
        for c in choices:
            text.append(f"  {c.lineId} {label}: {'; '.join(c.reasons)}")
    return CommandResult("campaign lines", runId=args.launch, message="\n".join(text),
                         data=rec.model_dump(mode="json"))


@_command("choose")
def _choose(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.selection import choose_line

    run = choose_line(_store(args), _config_dir(args), args.launch, args.line, by=args.by, role=args.role,
                      reason=args.reason, now=_now())
    stages = " -> ".join(", ".join(stage) for stage in run.plannedStages)
    return CommandResult(
        "campaign choose", runId=run.lineRunId, status=run.state,
        message=f"{run.lineRunId}: {run.lineId} v{run.lineVersion} chosen ({stages})",
        data={"lineRunId": run.lineRunId, "lineId": run.lineId, "lineVersion": run.lineVersion,
              "plannedStages": run.plannedStages},
    )


def _executions_text(executions: list[Any]) -> str:
    return "\n".join(f"  stage {e.stageIndex + 1} {e.moveId}: {e.status} ({e.note or e.gate})" for e in executions)


@_command("step")
def _step(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.adapters import campaign_models
    from hipstraw_mm.campaign.runner import step_line

    r = step_line(_store(args), _config_dir(args), args.line_run, by=args.by, role=args.role, now=_now(),
                  model=campaign_models())
    done = f"; Review {r.reviewId} opened" if r.reviewId else ""
    return CommandResult(
        "campaign step", runId=args.line_run, status="completed" if r.reviewId else "staged",
        message=f"{args.line_run}: stage {r.stageIndex + 1} ran{done}\n{_executions_text(r.executions)}",
        data={"stage": r.stageIndex + 1, "executions": [e.model_dump(mode="json") for e in r.executions],
              "reviewId": r.reviewId},
    )


@_command("run")
def _run(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.adapters import campaign_models
    from hipstraw_mm.campaign.runner import run_line

    results = run_line(_store(args), _config_dir(args), args.line_run, by=args.by, role=args.role, now=_now(),
                       model=campaign_models())
    executions = [e for r in results for e in r.executions]
    review_id = results[-1].reviewId
    return CommandResult(
        "campaign run", runId=args.line_run, status="completed",
        message=f"{args.line_run}: {len(results)} stages ran; Review {review_id} opened\n"
                f"{_executions_text(executions)}",
        data={"executions": [e.model_dump(mode="json") for e in executions], "reviewId": review_id},
    )


@_command("deviate")
def _deviate(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.models import LineRun
    from hipstraw_mm.campaign.runner import deviate

    store = _store(args)
    d = deviate(store, _config_dir(args), args.line_run, skip=args.skip, add=args.add, stage=args.stage,
                by=args.by, role=args.role, reason=args.reason, now=_now())
    run = store.get(LineRun, args.line_run)
    assert run is not None
    return CommandResult(
        "campaign deviate", runId=args.line_run, status=run.state,
        message=f"{d.deviationId}: {d.type} {d.moveId}; planned stages now "
                + " -> ".join(", ".join(s) for s in run.plannedStages[run.nextStage:]),
        data={"deviationId": d.deviationId, "type": d.type, "plannedStages": run.plannedStages,
              "state": run.state, "reviewId": run.reviewId},
    )


@_command("stop")
def _stop(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.runner import stop_line

    run = stop_line(_store(args), _config_dir(args), args.line_run, by=args.by, role=args.role, reason=args.reason,
                    now=_now())
    return CommandResult("campaign stop", runId=run.lineRunId, status=run.state,
                         message=f"{run.lineRunId}: abandoned; Review {run.reviewId} opened",
                         data={"state": run.state, "reviewId": run.reviewId})


def _review_text(review: Any) -> str:
    lines = [f"{review.reviewId} ({review.state}): {review.question}"]
    for f in review.findings:
        tag = f" [{f.verdict}]" if f.verdict else ""
        proposal = " (proposal)" if f.isProposal else ""
        lines.append(f"  {f.findingId} {f.reviewState:<9} {f.area:<9} {f.kind}{tag}{proposal}: {f.currentText}")
        for q in f.quotes:
            lines.append(f'      "{q.quote}" [{q.evidenceId}]')
        if f.fix:
            lines.append(f"      fix: {f.fix}")
    return "\n".join(lines)


@_command("review")
def _review(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign import review as rv
    from hipstraw_mm.campaign.models import ReviewRun

    store, cmd = _store(args), args.review_command
    if cmd == "show":
        review = store.get(ReviewRun, args.review)
        if review is None:
            from hipstraw_mm.errors import PreconditionError

            raise PreconditionError(f"Review {args.review} not found")
    elif cmd == "finding":
        action: Literal["accept", "reject", "correct"] = (
            "accept" if args.accept else "reject" if args.reject else "correct"
        )
        review = rv.review_finding(store, _config_dir(args), args.review, args.finding, action=action,
                                   text=args.correct, verdict=args.verdict, reason=args.reason, by=args.by,
                                   role=args.role, now=_now())
    elif cmd == "validate":
        review = rv.validate_review(store, _config_dir(args), args.review, by=args.by, role=args.role, now=_now())
    elif cmd == "accept":
        review = rv.accept_review(store, _config_dir(args), args.review, by=args.by, role=args.role, now=_now(),
                                  reason=args.reason)
    else:
        review = rv.reject_review(store, _config_dir(args), args.review, by=args.by, role=args.role, now=_now(),
                                  reason=args.reason)
    data = review.model_dump(mode="json")
    if review.committedPositionVersion is not None:
        data["positionVersion"] = review.committedPositionVersion
    return CommandResult(f"campaign review {cmd}", runId=review.reviewId, status=review.state,
                         message=_review_text(review), data=data)


@_command("report")
def _report(args: argparse.Namespace) -> CommandResult:
    from hipstraw_mm.campaign.report import render_report

    out = Path(args.out) if args.out else Path("reports") / f"{args.launch}_readiness.md"
    record = render_report(_store(args), _config_dir(args), args.launch, _now(), out)
    return CommandResult("campaign report", runId=args.launch, status="rendered",
                         message=f"{record.reportId}: {record.path} (Position v{record.positionVersion})",
                         data=record.model_dump(mode="json"))


@_command("view")
def _view(args: argparse.Namespace) -> CommandResult:
    import sys

    from hipstraw_mm.campaign.store import default_db_path
    from hipstraw_mm.campaign.viewer import CampaignHandler, CampaignView
    from hipstraw_mm.viewer.server import ViewerServer

    db = args.db or default_db_path()
    server = ViewerServer(CampaignView(db, _config_dir(args)), port=args.port, handler=CampaignHandler)
    print(f"campaign page: http://{server.server_address[0]!s}:{server.server_address[1]}/ "
          f"(reads {db}; Ctrl+C stops it)", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return CommandResult("campaign view", message="campaign page stopped")


@_command("console")
def _console(args: argparse.Namespace) -> CommandResult:
    """Constitution XIII (v2.0.0): the page plus the approved actions, each through the governed operation."""
    import sys

    from hipstraw_mm.campaign.console import CampaignConsole, ConsoleServer
    from hipstraw_mm.campaign.store import SqliteCampaignStore, default_db_path
    from hipstraw_mm.campaign.viewer import CampaignView

    db = args.db or default_db_path()
    SqliteCampaignStore(db).close()  # create the database, so the page can open it before the first launch
    server = ConsoleServer(CampaignView(db, _config_dir(args)), CampaignConsole(db, _config_dir(args)),
                           port=args.port)
    print(f"campaign console: http://{server.server_address[0]!s}:{server.server_address[1]}/ "
          f"(changes {db} only through the governed commands; Ctrl+C stops it)", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return CommandResult("campaign console", message="campaign console stopped")
