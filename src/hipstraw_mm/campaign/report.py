"""The campaign readiness report (US5, FR-046, FR-051): rendered only from an accepted Position.

It answers channel by channel (Oct 30 meeting): for each channel, whether the message is right for the
audience that channel reaches, with the quotes behind each verdict and the fix, and the channel's own rules
(M13) with their sources; then a side-by-side comparison when there is more than one channel. After that: the
campaign-wide questions, the blockers and what clears them, open assumptions and unknowns, the Lines used with
their deviations, and an evidence index. There is no total and no prediction: every line traces to evidence or
says it is unknown.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from hipstraw_mm.campaign.channels import channel_plans, load_channel_standards
from hipstraw_mm.campaign.config import load_settings
from hipstraw_mm.campaign.models import (
    Deviation,
    EvidenceRecord,
    Finding,
    LineRun,
    Mandate,
    MoveExecution,
    PositionItem,
    PositionSnapshot,
    ReportRecord,
    ReviewRun,
)
from hipstraw_mm.campaign.moves.readiness import load_criteria
from hipstraw_mm.campaign.repertoire import load_repertoire
from hipstraw_mm.campaign.review import VERDICT_TEXT, rubric_head, rubric_reason, rubric_title
from hipstraw_mm.campaign.rubric import load_rubric
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.errors import PreconditionError

_REVIEWED = ("accepted", "corrected")
_STRATEGY_KINDS = ("gap", "proposal", "test_plan", "delta", "assumption", "contested", "stale_metric")


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _refs(refs: list[str]) -> str:
    return ", ".join(refs) if refs else "no evidence cited"


def _rubric_rows(findings: list[Finding], titles: dict[str, str], names: dict[str, str]) -> list[str]:
    rows = ["| Question | Verdict | Why | Evidence | Fix |", "|---|---|---|---|---|"]
    for f in findings:
        assert f.questionId and f.verdict
        title = rubric_title(f)  # the question it was judged under, whatever the current rubric version
        head = rubric_head(f.questionId, title, names.get(f.channel) if f.channel else None)
        why = rubric_reason(f.currentText, head)
        quotes = "; ".join(f'"{q.quote}" [{q.evidenceId}]' for q in f.quotes) or (
            "unknown: no quote" if f.verdict == "unknown" else _refs(f.evidenceRefs))
        corrected = " (corrected by the reviewer)" if f.reviewState == "corrected" else ""
        rows.append(f"| {f.questionId} {_cell(title)} | {VERDICT_TEXT[f.verdict]} | {_cell(why)}{corrected} "
                    f"| {_cell(quotes)} | {_cell(f.fix or '')} |")
    return rows


def _clears_when(key: str | None, criteria_text: dict[str, str], check_text: dict[str, str]) -> str:
    if key and key in criteria_text:
        return criteria_text[key]
    if key and key.startswith("DZ02:"):
        return "the asset is ready before the Day Zero lead time"
    if key and key.split(":")[0] in check_text:
        return f"{check_text[key.split(':')[0]]} (M13 finds it met)"
    return "the Sponsor resolves it"


_RESULT = {"met": "met", "not_met": "**not met**", "not_stated": "not stated"}


def _standards(executions: list[MoveExecution]) -> dict[str, list[dict[str, Any]]]:
    """The latest M13 checklist for each channel."""
    out: dict[str, list[dict[str, Any]]] = {}
    for e in sorted((e for e in executions if e.moveId == "M13" and e.status == "succeeded"), key=lambda e: e.endedAt):
        latest: dict[str, list[dict[str, Any]]] = {}
        for p in e.proposals:
            if p.get("type") == "standard":
                latest.setdefault(p["channel"], []).append(p)
        out.update(latest)
    return out


def _channel_sections(mandate: Mandate, rubric_findings: list[Finding], titles: dict[str, str],
                      names: dict[str, str], standards: dict[str, list[dict[str, Any]]],
                      items: list[PositionItem], rejected: set[tuple[str, str]]) -> list[str]:
    plans = channel_plans(mandate)
    by_channel: dict[str, dict[str, Finding]] = {}
    for f in rubric_findings:
        if f.channel and f.questionId:
            by_channel.setdefault(f.channel, {})[f.questionId] = f
    out: list[str] = []
    if len(plans) > 1:
        channel_qs = list(dict.fromkeys([*(f.questionId for f in rubric_findings if f.channel and f.questionId),
                                         *(q for q, c in sorted(rejected) if c)]))
        out += ["### Side by side", "",
                "| Question | " + " | ".join(names.get(p.channel, p.channel) for p in plans) + " |",
                "|---|" + "---|" * len(plans)]
        for qid in channel_qs:
            cells = []
            for p in plans:
                found = by_channel.get(p.channel, {}).get(qid)
                cells.append(VERDICT_TEXT[found.verdict] if found and found.verdict
                             else "rejected" if (qid, p.channel) in rejected else "not judged")
            out.append(f"| {qid} {_cell(titles.get(qid, ''))} | " + " | ".join(cells) + " |")
        for label, kind in (("Open blockers", "blocker"), ("Open unknowns", "unknown")):
            cells = [str(sum(1 for i in items if (i.channel, i.kind, i.state) == (p.channel, kind, "open")))
                     for p in plans]
            out.append(f"| {label} | " + " | ".join(cells) + " |")
        cells = [str(sum(1 for r in standards[p.channel] if (r["level"], r["status"]) == ("should", "not_met")))
                 if p.channel in standards else "not checked" for p in plans]
        out.append("| Practice fixes | " + " | ".join(cells) + " |")
        out.append("")
    for plan in plans:
        name = names.get(plan.channel, plan.channel)
        out += [f"### {name}", ""]
        facts = [f"Reaches: {plan.audience or 'not stated'}"]
        if plan.budget:
            facts.append(f"budget {plan.budget.amount:g} {plan.budget.currency}")
        if plan.successMeasure:
            facts.append(f"measured by: {plan.successMeasure}")
        out += ["; ".join(facts) + ".", ""]
        judged = list(by_channel.get(plan.channel, {}).values())
        out += _rubric_rows(judged, titles, names) if judged else ["No rubric judgements for this channel yet."]
        checks = standards.get(plan.channel)
        out.append("")
        if checks:
            version = checks[0].get("standardsVersion", "")
            out += [f"Channel rules ({version}): `must` is a platform rule, the law or a fact the channel cannot be "
                    "judged without; `should` is established practice.", "",
                    "| Check | Level | Result | Source |", "|---|---|---|---|"]
            out += [f"| {r['checkId']} {_cell(r['text'])} | {r['level']} | {_RESULT[r['status']]}"
                    + (f" ({_cell(r['detail'])})" if r["status"] != "met" else "") + f" | {_cell(r['source'])} |"
                    for r in checks]
        else:
            out.append("Channel rules not checked yet. Run L01 Readiness-first (M13).")
        open_here = [i for i in items if i.channel == plan.channel and i.state == "open"
                     and i.kind in ("blocker", "unknown")]
        if open_here:
            out += ["", "Open on this channel: " + "; ".join(f"**{i.itemId}** {i.text}" for i in open_here) + "."]
        out.append("")
    return out


def build_report(store: CampaignStore, config_dir: Path, launch_id: str) -> tuple[str, PositionSnapshot]:
    position = store.head_position(launch_id)
    if position is None or position.state != "accepted":
        raise PreconditionError(f"{launch_id} has no accepted Position yet; accept a Review first")
    mandate = store.latest_mandate(launch_id)
    # Every accepted Review behind the current Position, oldest first: the report covers the whole history.
    reviews = sorted((r for r in store.list_for_launch(ReviewRun, launch_id) if r.state == "accepted"),
                     key=lambda r: r.committedPositionVersion or 0)
    if not reviews or mandate is None:
        raise PreconditionError(f"the Reviews behind Position v{position.version} are missing")
    latest = reviews[-1]
    rep, rubric, criteria = load_repertoire(config_dir), load_rubric(config_dir), load_criteria(config_dir)
    settings, channel_standards = load_settings(config_dir), load_channel_standards(config_dir)
    names = {c: channel_standards.name(c) for c in mandate.strategy.channels}
    titles = {q.id: q.title for q in rubric.questions}
    check_text = {c.id: c.text for s in channel_standards.channels.values() for c in s.checks}
    executions_all = store.list_for_launch(MoveExecution, launch_id)
    accepted_runs = {r.lineRunId for r in reviews}
    reviewed = [f for r in reviews for f in r.findings if f.reviewState in _REVIEWED]
    judged = [r for r in reviews if any(f.kind == "rubric" for f in r.findings)]
    rubric_review = judged[-1] if judged else None
    rubric_findings = [f for f in rubric_review.findings
                       if f.kind == "rubric" and f.reviewState in _REVIEWED] if rubric_review else []
    rejected = {(f.questionId or "", f.channel or "") for f in rubric_review.findings
                if f.kind == "rubric" and f.reviewState == "rejected"} if rubric_review else set()
    items = position.items
    criteria_text = {c.id: c.text for c in criteria.criteria}

    lines = [
        f"# Campaign Readiness Review: {mandate.product.name} ({mandate.market})",
        "",
        f"Launch `{launch_id}` · Position v{position.version} accepted by {latest.decidedBy} · "
        f"Day Zero {mandate.dayZero.isoformat()} · evidence as of {latest.evidenceCutoff[:10]}",
        "",
        f"> {settings.scopeStatement}",
        "",
        "## Channel by channel: is the message right for the audience it reaches?",
        "",
        "Each question is judged met, partly met, not met or unknown from quoted evidence, for each channel's own "
        "audience and copy. There is no total.",
        "",
    ]
    if rubric_review is not None:
        lines += [f"Judgements from Review `{rubric_review.reviewId}` "
                  f"(Position v{rubric_review.committedPositionVersion}).", ""]
    else:
        lines += ["No rubric judgements yet. Run L02 Strategy validation to judge the campaign.", ""]
    standards = _standards([e for e in executions_all if e.lineRunId in accepted_runs])
    lines += _channel_sections(mandate, rubric_findings, titles, names, standards, position.items, rejected)

    lines += ["## Whole campaign", ""]
    campaign_wide = [f for f in rubric_findings if not f.channel]
    lines += _rubric_rows(campaign_wide, titles, names) if campaign_wide else ["No campaign-wide judgements yet."]
    if rejected:
        lines += ["", f"Judgements rejected by the reviewer: {len(rejected)}."]

    lines += ["", "## Readiness blockers", ""]
    blockers = [i for i in items if i.kind == "blocker" and i.state == "open"]
    lines += [f"- **{i.itemId}** {i.text}. Clears when: {_clears_when(i.key, criteria_text, check_text)}. "
              f"[{_refs(i.evidenceRefs)}]" for i in blockers] or ["None open."]

    lines += ["", "## Strategy findings", ""]
    strategy = [f for f in reviewed if f.kind in _STRATEGY_KINDS]
    lines += [f"- {f.currentText}" + (" (proposal)" if f.isProposal else "")
              + f" [{_refs(f.evidenceRefs or f.itemRefs)}]" for f in strategy] or ["None."]

    lines += ["", "## Open assumptions", ""]
    assumptions = [i for i in items if i.kind == "assumption" and i.state in ("open", "awaiting_evidence")]
    lines += [f"- **{i.itemId}** {i.text} ({i.state.replace('_', ' ')}{', core' if i.core else ''})"
              for i in assumptions] or ["None."]

    lines += ["", "## Unknowns", ""]
    unknowns = [i for i in items if i.kind == "unknown" and i.state == "open"]
    lines += [f"- **{i.itemId}** {i.text}" for i in unknowns] or ["None."]

    lines += ["", "## Lines used", ""]
    deviations_all = store.list_for_launch(Deviation, launch_id)
    for review in reviews:
        run = store.get(LineRun, review.lineRunId)
        if run is None:
            continue
        line = rep.lines.get(run.lineId)
        executions = [e for e in executions_all if e.lineRunId == run.lineRunId]
        deviations = [d for d in deviations_all if d.lineRunId == run.lineRunId]
        lines.append(f"- **{run.lineId} {line.name if line else ''}** v{run.lineVersion} (Position "
                     f"v{review.committedPositionVersion}), chosen by {run.chosenBy}: {run.reason}. "
                     "Moves run: " + ", ".join(f"{e.moveId} {e.status}" for e in executions) + ". "
                     "Deviations: " + ("; ".join(" ".join(filter(None, [d.type, d.moveId, f"by {d.by} ({d.reason})"]))
                                                 for d in deviations) or "none") + ". "
                     f"Reviewed by {review.validatedBy}; accepted by {review.decidedBy}.")

    cited = {r for f in reviewed for r in [*f.evidenceRefs, *(q.evidenceId for q in f.quotes)]}
    cited |= {r for i in items if i.state in ("open", "awaiting_evidence", "contested") for r in i.evidenceRefs}
    evidence = [e for e in store.list_for_launch(EvidenceRecord, launch_id) if e.evidenceId in cited]
    lines += ["", "## Evidence", "", "| Evidence | Kind | Source | State | Note |", "|---|---|---|---|---|"]
    lines += [f"| {e.evidenceId} | {e.kind} | {_cell(e.sourceRef)} | {e.verificationState} | {_cell(e.uncertainty)} |"
              for e in evidence]

    stamps = [r.mechanismStamp for r in reviews]
    prompts = sorted({p for s in stamps for p in s.promptVersions})
    models = sorted({m.served or m.configured or "" for s in stamps for m in s.models} - {""})
    rubric_versions = sorted({s.rubricVersion for s in stamps if s.rubricVersion})
    lines += [
        "",
        "---",
        "",
        "Verdicts are evidence-linked judgements checked by a Hipstraw reviewer, not a prediction of results. "
        f"Mechanism: code {stamps[-1].codeVersion}, repertoire {stamps[-1].repertoireVersion}, "
        f"criteria {stamps[-1].criteriaVersion}, channel rules {channel_standards.version}"
        + (f", rubric {', '.join(rubric_versions)}" if rubric_versions else "")
        + (f", prompts {', '.join(prompts)}" if prompts else "")
        + (f", models {', '.join(models)}" if models else "")
        + ".",
        "",
    ]
    return "\n".join(lines), position


def render_report(store: CampaignStore, config_dir: Path, launch_id: str, now: datetime,
                  out_path: Path) -> ReportRecord:
    text, position = build_report(store, config_dir, launch_id)
    tracer = campaign_tracer(store, config_dir, launch_id)
    with tracer.step("campaign_manager", "launch_desk", "render_report", right="render_report") as step:
        step.set_inputs({"positionVersion": position.version, "out": str(out_path)})
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        record = ReportRecord(
            reportId=f"rpt_{launch_id}_{len(store.list_for_launch(ReportRecord, launch_id)) + 1}", launchId=launch_id,
            positionVersion=position.version, renderedAt=now.isoformat(), path=str(out_path),
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        store.insert(record)
        step.set_outputs({"reportId": record.reportId, "sha256": record.sha256})
        step.set_decision("rendered", None)
    return record
