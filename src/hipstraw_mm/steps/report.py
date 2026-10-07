"""T043 report (thin): sections 1–8 of contracts/demo-report.md, from stored records only.

No model call. Sections 9–11 (unknowns and conflicts, traceability, footer) come with T070.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.models import DemoReport
from hipstraw_mm.steps.common import require_run, run_step
from hipstraw_mm.store.base import Doc

STEP = "report"
HYPOTHESIS_MINIMUM = 3  # SC-003: at least 3 included companies


def report(ctx: Context, run_id: str, out_dir: Path | None = None) -> CommandResult:
    run = require_run(ctx.store, run_id, "reviewed")
    return run_step(ctx, run_id, STEP, lambda: _report(ctx, run, out_dir or ctx.reports_dir))


def _cell(text: object) -> str:
    """Text safe inside a markdown table cell."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _website(record: Doc) -> str:
    return f"https://{record['domain']}/" if record.get("domain") else "none (registry-only)"


def _report(ctx: Context, run: Doc, out_dir: Path) -> CommandResult:
    store, run_id = ctx.store, run["runId"]
    program = store.get_program(run["programId"]) or {}
    candidate = store.get_candidate(run["candidateId"]) or {}
    records = {r["companyRecordId"]: r for r in store.list_company_records(run_id)}
    evidence = {e["evidenceId"]: e for e in store.list_evidence(run_id)}
    groups: dict[str, list[tuple[Doc, Doc]]] = {"include": [], "needs_verification": [], "exclude": []}
    for decision in store.list_review_decisions(run_id):
        record = records[decision["companyRecordId"]]
        groups[decision["disposition"]].append((record, decision))
    for pairs in groups.values():
        pairs.sort(key=lambda pair: pair[0]["name"].casefold())

    counts = {
        "returned": len(records),
        "included": len(groups["include"]),
        "excluded": len(groups["exclude"]),
        "needsVerification": len(groups["needs_verification"]),
        "shortfall": int((run.get("counts") or {}).get("shortfall", 0)),
    }
    interests = {i["id"]: i["label"] for i in program.get("primaryInterests", [])}
    markdown = "\n".join(
        [
            *_title_and_summary(run, program, candidate, counts),
            *_position(run, interests),
            *_constraints(run),
            *_hypothesis(groups["include"]),
            *_included(groups["include"], evidence, interests),
            *_needs_verification(groups["needs_verification"]),
            *_excluded(groups["exclude"]),
        ]
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.md"
    path.write_text(markdown, encoding="utf-8", newline="\n")
    data = path.read_bytes()
    meta = DemoReport(
        runId=run_id,
        path=path.as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
        counts=counts,
        generatedAt=ctx.now_iso(),
    )
    store.upsert_demo_report(run_id, meta.model_dump())
    store.transition_run(
        run_id,
        "reviewed",
        "reported",
        {"stepTimes": {**(run.get("stepTimes") or {}), "reportedAt": ctx.now_iso()}},
    )
    ctx.log.step_end(
        run_id,
        STEP,
        {
            "included": counts["included"],
            "needsVerification": counts["needsVerification"],
            "excluded": counts["excluded"],
            "reportBytes": len(data),
        },
    )
    warnings = []
    if counts["shortfall"]:
        warnings.append(
            f"shortfall: {counts['returned']} of {counts['returned'] + counts['shortfall']} companies found"
        )
    return CommandResult(
        STEP, message=f"report written to {path}", runId=run_id, status="reported", counts=counts, warnings=warnings
    )


# -- sections ---------------------------------------------------------------------


def _title_and_summary(run: Doc, program: Doc, candidate: Doc, counts: dict[str, int]) -> list[str]:
    run_date = str(run.get("createdAt") or (run.get("stepTimes") or {}).get("reviewedAt") or "")[:10]
    lines = [
        f"# Invoice Alpha: first position report ({run['runId']})",
        "",
        "## Run summary",
        "",
        f"- Program: {program.get('name', run['programId'])} ({program.get('sourceUrl', 'source unknown')})",
        f"- Experiment context: {candidate.get('label', 'unknown')} (candidate `{run['candidateId']}`)",
        f"- Run date: {run_date or 'unknown'}; model: {run.get('model') or 'not set'}",
        f"- Companies returned: {counts['returned']}; included: {counts['included']}; "
        f"excluded: {counts['excluded']}; needs verification: {counts['needsVerification']}",
    ]
    if counts["shortfall"]:
        lines.append(f"- Shortfall: {counts['shortfall']}. {run.get('shortfallReason') or ''}".rstrip())
    else:
        lines.append("- Shortfall: none")
    return [*lines, ""]


def _position(run: Doc, interests: dict[str, str]) -> list[str]:
    position = run["position"]
    labels = ", ".join(interests.get(i, i) for i in position["primaryInterestIds"])
    return [
        "## First position",
        "",
        f"- Segment: {position['segment']}",
        f"- Company archetype: {position['companyArchetype']}",
        f"- Buyer: {position['buyer']}",
        f"- Problem: {position['problem']}",
        f"- Trigger: {position['trigger']}",
        f"- Primary interests: {labels}",
        "",
    ]


def _constraints(run: Doc) -> list[str]:
    constraints = run["constraintsInForce"]
    return [
        "## Constraints in force",
        "",
        f"- Fewer than {constraints['maxEmployees']:,} employees",
        f"- Less than ${constraints['maxRevenueUsd']:,} revenue",
        "- Headquarters in one of these metro areas (US Census combined statistical areas):",
        *(f"  - {m['name']} (CSA {m['csaCode']})" for m in constraints["metros"]),
        "",
    ]


def _hypothesis(included: list[tuple[Doc, Doc]]) -> list[str]:
    met = "met" if len(included) >= HYPOTHESIS_MINIMUM else "not met"
    return [
        "## Hypothesis check (SC-003)",
        "",
        f"Included companies: {len(included)} (minimum {HYPOTHESIS_MINIMUM}: {met}).",
        "",
        "Spot-check, filled in by the reviewer:",
        "",
        "| Company | Meets constraints (yes/no) | Genuine interest signal (yes/no) | Notes |",
        "|---|---|---|---|",
        *(f"| {_cell(record['name'])} |  |  |  |" for record, _ in included),
        "",
    ]


def _included(included: list[tuple[Doc, Doc]], evidence: dict[str, Doc], interests: dict[str, str]) -> list[str]:
    lines = ["## Included companies", ""]
    if not included:
        lines += ["None.", ""]
    for record, decision in included:
        confidence = record.get("confidence")
        band = confidence["band"] if confidence else "not computed"
        hq = record.get("hq") or {}
        size_values = [
            f"{evidence.get(s['evidenceId'], {}).get('claimValue', '?')} {s['kind']}"
            for s in (record.get("size") or {}).get("signals", [])
        ]
        lines += [
            f"### {record['name']}",
            "",
            f"- Website: {_website(record)}",
            f"- Confidence: {band}",
            f"- Headquarters: {hq.get('city') or '?'}, {hq.get('state') or '?'} ({hq.get('status', 'unknown')})",
            f"- Size: {', '.join(size_values) or 'unknown'}",
            "- Fit:",
            *(
                f"  - {fit['aspect']}: {fit['statement']} "
                f"(interests: {', '.join(interests.get(i, i) for i in fit['primaryInterestIds'])})"
                for fit in record.get("fitClaims", [])
            ),
            "- Interest signals:",
            *(f"  - {signal['kind']}: {signal['statement']}" for signal in record.get("interestSignals", [])),
            f"- Falsifier: {record.get('falsifier') or 'unknown'}",
            f"- Review: {decision['reason']}",
            "",
            "| Claim | URL | Date | Reliability | Excerpt |",
            "|---|---|---|---|---|",
        ]
        for evidence_id in decision.get("evidenceIds", []):
            ev = evidence.get(evidence_id)
            if ev is None:
                continue
            lines.append(
                f"| {_cell(ev['claimField'])}: {_cell(ev['claimValue'])} | {_cell(ev['url'])} | "
                f'{_cell(ev.get("publishedAt") or "unknown")} | {_cell(ev["reliability"])} | "{_cell(ev["excerpt"])}" |'
            )
        lines.append("")
    return lines


def _needs_verification(pairs: list[tuple[Doc, Doc]]) -> list[str]:
    lines = ["## Needs verification", ""]
    if not pairs:
        return [*lines, "None.", ""]
    lines += ["| Company | Website | What is missing | Review reason |", "|---|---|---|---|"]
    for record, decision in pairs:
        open_rules = [f"{r['rule']} ({r['outcome']})" for r in decision["ruleResults"] if r["outcome"] != "pass"]
        unknowns = [u["field"] for u in record.get("unknowns", [])]
        missing = "; ".join(
            part
            for part in (
                f"rules not passed: {', '.join(open_rules)}" if open_rules else "",
                f"unknowns: {', '.join(unknowns)}" if unknowns else "",
            )
            if part
        )
        lines.append(
            f"| {_cell(record['name'])} | {_cell(_website(record))} | {_cell(missing or 'judgement')} | "
            f"{_cell(decision['reason'])} |"
        )
    return [*lines, ""]


def _excluded(pairs: list[tuple[Doc, Doc]]) -> list[str]:
    lines = ["## Excluded", ""]
    if not pairs:
        return [*lines, "None.", ""]
    lines += ["| Company | Website | Failed rule | Review reason |", "|---|---|---|---|"]
    for record, decision in pairs:
        failed = [r["rule"] for r in decision["ruleResults"] if r["outcome"] == "fail"]
        rule = ", ".join(failed) or "judgement: falsifier met"
        lines.append(
            f"| {_cell(record['name'])} | {_cell(_website(record))} | {_cell(rule)} | {_cell(decision['reason'])} |"
        )
    return [*lines, ""]
