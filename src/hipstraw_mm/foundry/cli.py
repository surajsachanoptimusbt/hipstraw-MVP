"""`hipstraw-mm demand ...`: market demand validation against the demand evidence rubric (Blueprint v0.1 section 07).

Dispatched by the top-level CLI before the market context is built: it reads a case file or a thesis and the
rubric config, and needs no store, model or network. Lines are picked by the playbook's rules, never by a model
(Nov 6 meeting).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from hipstraw_mm.context import CommandResult
from hipstraw_mm.foundry.demand import (
    DemandRubric,
    assess,
    load_case,
    load_demand_rubric,
    render_markdown,
    run_lab,
)


def register(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
    common: argparse.ArgumentParser,
    common_after: argparse.ArgumentParser,
    parser_class: type[argparse.ArgumentParser],
) -> None:
    group = sub.add_parser("demand", parents=[common], help="validate market demand against the demand evidence rubric")
    dsub = group.add_subparsers(dest="demand_command", required=True, parser_class=parser_class)

    p = dsub.add_parser("assess", parents=[common_after], help="judge a case's evidence; writes a markdown report")
    p.add_argument("--case", required=True, help="case file (YAML): question, offering, segment, gates, evidence")
    p.add_argument("--out", default=None, help="report path (default: reports/<case>_demand.md)")

    p = dsub.add_parser("program", parents=[common_after],
                        help="walk a market thesis through to a demand validation program: Lines, Moves, scorecard")
    p.add_argument("--thesis", required=True, help="thesis file (YAML): product, market, demand hypotheses")
    p.add_argument("--out-dir", default="reports/demand", help="where the page, markdown and JSON go")

    p = dsub.add_parser("recommend", parents=[common_after],
                        help="the playbook's Line for each task of each hypothesis, with the Lines available")
    p.add_argument("--thesis", required=True, help="thesis file (YAML): product, market, demand hypotheses")

    p = dsub.add_parser("worksheet", parents=[common_after],
                        help="write the predefined tasks, Lines, Moves and metrics as a worksheet (.xlsx)")
    p.add_argument("--out", default="docs/hipstraw_demand_lines_and_moves.xlsx")

    dsub.add_parser("rubric", parents=[common_after], help="show the rubric: dimensions, gates, Moves")

    p = dsub.add_parser("lab", parents=[common_after], help="run the rubric's lab cases and report agreement")
    p.add_argument("--dir", default=None, help="lab cases (default: <config-dir>/foundry/lab/demand_evidence)")


def dispatch(args: argparse.Namespace) -> CommandResult:
    config_dir = Path(args.config_dir)
    rubric = load_demand_rubric(config_dir)
    if args.demand_command == "rubric":
        lines = [f"{rubric.version} ({rubric.qualification})"]
        lines += [f"  {d.id} {d.title}: {d.question}" for d in rubric.dimensions]
        lines += [f"  {g.id} gate: {g.text}" for g in rubric.gates]
        lines += [f"  {m.id} {m.name} ({m.effect})" for m in rubric.moves]
        return CommandResult("demand rubric", status=rubric.qualification, message="\n".join(lines),
                             data=rubric.model_dump(mode="json"))
    if args.demand_command == "lab":
        lab_dir = Path(args.dir) if args.dir else config_dir / "foundry" / "lab" / "demand_evidence"
        results = run_lab(lab_dir, rubric)
        agreed = sum(1 for r in results if r.agrees)
        lines = [f"{agreed} of {len(results)} lab cases agree with their expected result"]
        lines += [f"  {'ok ' if r.agrees else 'NO '} {r.case}: expected {r.expected}, got {r.decision}"
                  + "".join(f"; {x}" for x in r.differences) for r in results]
        return CommandResult("demand lab", status="agree" if agreed == len(results) else "disagree",
                             message="\n".join(lines), counts={"cases": len(results), "agree": agreed},
                             data={"rubricVersion": rubric.version,
                                   "results": [r.model_dump(mode="json") for r in results]})
    if args.demand_command == "program":
        return _program(args, rubric)
    if args.demand_command == "recommend":
        return _recommend(args, rubric)
    if args.demand_command == "worksheet":
        from hipstraw_mm.foundry.worksheet import write_worksheet

        out = write_worksheet(rubric, Path(args.out))
        return CommandResult("demand worksheet", message=f"{len(rubric.tasks)} tasks, {len(rubric.lines)} Lines, "
                             f"{len(rubric.moves)} Moves, {len(rubric.scorecard)} metrics: {out}",
                             data={"worksheet": str(out)})
    case = load_case(Path(args.case), rubric)
    assessment = assess(case, rubric)
    out = Path(args.out) if args.out else Path("reports") / f"{case.case}_demand.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(assessment, case, rubric), encoding="utf-8")
    states = ", ".join(f"{d.id} {d.state}" for d in assessment.dimensions)
    return CommandResult("demand assess", runId=case.case, status=assessment.decision,
                         message=f"{assessment.decisionText}\n  {states}\n  report: {out}",
                         warnings=assessment.warnings,
                         data={"report": str(out), **assessment.model_dump(mode="json")})


def _program(args: argparse.Namespace, rubric: DemandRubric) -> CommandResult:
    from hipstraw_mm.foundry.program_report import render_program_html, render_program_markdown
    from hipstraw_mm.foundry.walkthrough import load_thesis, run_walkthrough

    w = run_walkthrough(load_thesis(Path(args.thesis), rubric), rubric)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    page, markdown, trace = (out / f"{w.thesis}_walkthrough.html", out / f"{w.thesis}_program.md",
                             out / f"{w.thesis}_walkthrough.json")
    page.write_text(render_program_html(w), encoding="utf-8")
    markdown.write_text(render_program_markdown(w), encoding="utf-8")
    trace.write_text(w.model_dump_json(indent=2), encoding="utf-8")
    lines = [f"{w.product}: {len(w.hypotheses)} hypotheses, {len(w.steps)} steps"]
    lines += [f"  {p.id} {p.name}: {p.assessment.decision} ({p.checkpoint}); Lines "
              + " > ".join(pl.id for pl in p.program) for p in w.hypotheses]
    lines.append(f"  page: {page}")
    return CommandResult("demand program", runId=w.thesis, status="planned", message="\n".join(lines),
                         counts={"hypotheses": len(w.hypotheses), "steps": len(w.steps)},
                         data={"page": str(page), "markdown": str(markdown), "trace": str(trace),
                               **w.model_dump(mode="json")})


def _recommend(args: argparse.Namespace, rubric: DemandRubric) -> CommandResult:
    from hipstraw_mm.foundry.playbook import recommend
    from hipstraw_mm.foundry.walkthrough import load_thesis

    rec = recommend(load_thesis(Path(args.thesis), rubric), rubric)
    lines = [f"{rec.product}: Lines picked by the playbook"]
    for h in rec.hypotheses:
        lines.append(f"  {h.id} {h.name}")
        for t in h.tasks:
            others = [f"{o.lineId} not eligible" for o in t.options if not o.eligible]
            lines.append(f"    {t.taskId} {t.task}: {t.lineId or 'no Line'} {t.lineName if t.lineId else ''}".rstrip()
                         + (f"  ({'; '.join(others)})" if others else ""))
    return CommandResult("demand recommend", runId=rec.thesis, status="recommended", message="\n".join(lines),
                         counts={"hypotheses": len(rec.hypotheses)},
                         data={"payloadHash": rec.payload_hash(), **rec.model_dump(mode="json")})
