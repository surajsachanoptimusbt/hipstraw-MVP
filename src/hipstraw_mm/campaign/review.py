"""Review runs (HA C4), the review queue (C9) and acceptance (C3).

When a Line ends, its Review is assembled by code from what the Moves did (research R9): no extra model
call at the point where honesty matters most. A Hipstraw reviewer then accepts, rejects or corrects each
finding and validates the Review; only the Sponsor's acceptance commits the successor Position, and only
against the base version the Review pinned (constitution VI).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from hipstraw_mm.campaign.audit import record_audit
from hipstraw_mm.campaign.config import load_roles, load_settings
from hipstraw_mm.campaign.gate import authorize
from hipstraw_mm.campaign.models import (
    Correction,
    Escalation,
    Finding,
    LineRun,
    ModelUse,
    MoveExecution,
    PositionItem,
    PositionSnapshot,
    Quote,
    ReviewRun,
    Verdict,
)
from hipstraw_mm.campaign.moves.readiness import load_criteria
from hipstraw_mm.campaign.repertoire import Repertoire, load_repertoire
from hipstraw_mm.campaign.stamp import mechanism_stamp
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.campaign.working import working_items
from hipstraw_mm.errors import PreconditionError, UsageError
from hipstraw_mm.market.trace import Tracer

VERDICT_TEXT = {"met": "met", "partly": "partly met", "not_met": "not met", "unknown": "unknown (too little evidence)"}


def rubric_head(question_id: str, title: str, channel_name: str | None = None) -> str:
    """How a rubric finding's text opens: "CR01 Message fits the audience (Email): " or, campaign-wide,
    "CR06 Specific audience: "."""
    return f"{question_id} {title}" + (f" ({channel_name})" if channel_name else "") + ": "


def rubric_title(finding: Finding) -> str:
    """The question title a rubric finding was judged under, read from its own text, so a finding judged with an
    earlier rubric version keeps its own question even after the rubric is renumbered."""
    rest = finding.text[len(finding.questionId or "") + 1:]
    head = rest.split(": ", 1)[0]
    if finding.channel and head.endswith(")") and " (" in head:
        head = head.rsplit(" (", 1)[0]
    return head


def rubric_reason(text: str, head: str) -> str:
    """A rubric finding's text without its opening and verdict: the reason alone."""
    if text.startswith(head):
        rest = text[len(head):]
        for verdict in sorted(VERDICT_TEXT.values(), key=len, reverse=True):
            if rest.startswith(f"{verdict}. "):
                return rest[len(verdict) + 2:]
    return text


class _Findings:
    def __init__(self) -> None:
        self.items: list[Finding] = []

    def add(self, **fields: object) -> None:
        text = str(fields["text"])
        self.items.append(Finding(findingId=f"F{len(self.items) + 1:02d}", currentText=text,
                                  **fields))  # type: ignore[arg-type]


def _assemble(store: CampaignStore, rep: Repertoire, criteria_version: str, executions: list[MoveExecution],
              items: list[PositionItem]) -> list[Finding]:
    by_id = {i.itemId: i for i in items}
    out = _Findings()
    deterministic = f"deterministic check (readiness criteria {criteria_version})"
    for e in executions:
        name = rep.moves[e.moveId].name if e.moveId in rep.moves else e.moveId
        if e.status != "succeeded":
            out.add(kind="gap", area="readiness", text=f"{e.moveId} {name} did not run: {e.error or e.gate}",
                    uncertainty="the Move's check is missing from this Review", sourceMove=e.moveId,
                    itemRefs=[], evidenceRefs=[])
            continue
        for item in e.newItems:
            if item.kind == "blocker" and item.state == "open":
                out.add(kind="blocker", area=item.area, text=item.text, itemRefs=[item.itemId],
                        evidenceRefs=item.evidenceRefs, uncertainty=deterministic, sourceMove=e.moveId,
                        channel=item.channel)
            elif item.kind == "unknown":
                out.add(kind="unknown", area=item.area, text=item.text, itemRefs=[item.itemId],
                        evidenceRefs=item.evidenceRefs, uncertainty="evidence missing", sourceMove=e.moveId,
                        channel=item.channel)
            elif item.kind == "observation" and item.state == "stale":
                out.add(kind="stale_metric", area="readiness", text=f"Stale metric: {item.text} ({item.note})",
                        itemRefs=[item.itemId], evidenceRefs=item.evidenceRefs,
                        uncertainty="metric cannot be relied on until refreshed", sourceMove=e.moveId)
            elif item.kind == "hypothesis":
                out.add(kind="proposal", area="strategy", text=f"Proposed variant to test: {item.text}",
                        itemRefs=[item.itemId], evidenceRefs=item.evidenceRefs, isProposal=True,
                        uncertainty="model proposal; untested", sourceMove=e.moveId)
        for t in e.transitions:
            changed = by_id.get(t.itemId)
            text = changed.text if changed else t.itemId
            if t.toState == "cleared":
                out.add(kind="blocker", area="readiness", text=f"Cleared: {text}", itemRefs=[t.itemId],
                        evidenceRefs=t.evidenceRefs, uncertainty=deterministic, sourceMove=e.moveId,
                        channel=changed.channel if changed else None)
            elif t.toState == "resolved":
                out.add(kind="unknown", area=changed.area if changed else "readiness", text=f"Resolved: {text}",
                        itemRefs=[t.itemId], evidenceRefs=t.evidenceRefs, uncertainty=deterministic,
                        sourceMove=e.moveId, channel=changed.channel if changed else None)
            elif t.toState == "awaiting_evidence":
                out.add(kind="assumption", area="strategy", text=f"Evidence requested from the Sponsor: {text}",
                        itemRefs=[t.itemId], evidenceRefs=[], uncertainty="unverified until the Sponsor answers",
                        sourceMove=e.moveId)
            elif t.toState == "planned":
                out.add(kind="test_plan", area="strategy", text=f"Draft Test Plan for {t.itemId}: {text}",
                        itemRefs=[t.itemId], evidenceRefs=[], uncertainty="a draft, not an approval",
                        sourceMove=e.moveId)
            elif t.fromState == "running":
                out.add(kind="delta", area="strategy", text=f"Observed Delta for {t.itemId}: {text} ({t.toState})",
                        itemRefs=[t.itemId], evidenceRefs=t.evidenceRefs,
                        uncertainty="observational comparison; never causal proof", sourceMove=e.moveId)
        for p in e.proposals:
            kind = p.get("type")
            if kind == "rubric":
                quotes = [Quote(**q) for q in p.get("quotes", [])]
                refs = list(dict.fromkeys([*(q.evidenceId for q in quotes), *p.get("evidenceRefs", [])]))
                head = rubric_head(p["questionId"], p["title"], p.get("channelName"))
                out.add(kind="rubric", area=p["area"], questionId=p["questionId"], verdict=p["verdict"],
                        quotes=quotes, fix=p.get("fix"), evidenceRefs=refs, itemRefs=[], isProposal=True,
                        text=f"{head}{VERDICT_TEXT[p['verdict']]}. {p['reason']}", channel=p.get("channel"),
                        uncertainty="model judgement against the rubric; check the quotes", sourceMove=e.moveId)
            elif kind == "standard" and p["level"] == "should" and p["status"] == "not_met":
                # A `must` miss is already a blocker above; a `should` miss is a fix the reviewer confirms.
                out.add(kind="standard", area="readiness", channel=p["channel"], itemRefs=[], evidenceRefs=[],
                        text=f"{p['channelName']}: {p['text']}: not met ({p['detail']}). Source: {p['source']}",
                        uncertainty=f"deterministic check against {p['standardsVersion']} (practice, not a rule)",
                        sourceMove=e.moveId)
            elif kind == "gap":
                out.add(kind="gap", area=p.get("area", "strategy"), text=p["text"], itemRefs=p.get("itemRefs", []),
                        evidenceRefs=p.get("evidenceRefs", []), isProposal=True,
                        uncertainty="model proposal", sourceMove=e.moveId)
            elif kind == "assumption":
                out.add(kind="assumption", area="strategy", text=f"Suggested assumption to verify: {p['text']}",
                        itemRefs=[], evidenceRefs=p.get("evidenceRefs", []), isProposal=True,
                        uncertainty="model proposal", sourceMove=e.moveId)
        if e.moveId == "M12":
            for record_id in e.produced:
                escalation = store.get(Escalation, record_id)
                if escalation:
                    out.add(kind="escalation", area="readiness", text=f"Escalated to {escalation.to}: "
                            f"{len(escalation.itemRefs)} open items", itemRefs=escalation.itemRefs, evidenceRefs=[],
                            uncertainty="awaiting the Sponsor's decision", sourceMove=e.moveId)
    covered = {ref for f in out.items if f.kind != "escalation" for ref in f.itemRefs}
    for item in items:
        if item.itemId in covered:
            continue
        if (item.kind, item.state) in (("blocker", "open"), ("unknown", "open"), ("claim", "contested")):
            kind = {"blocker": "blocker", "unknown": "unknown", "claim": "contested"}[item.kind]
            out.add(kind=kind, area=item.area, text=item.text, itemRefs=[item.itemId], evidenceRefs=item.evidenceRefs,
                    uncertainty=f"still open (set by {item.setBy})", sourceMove=None, channel=item.channel)
    return out.items


def draft_review(store: CampaignStore, config_dir: Path, run: LineRun, now: datetime, tracer: Tracer) -> ReviewRun:
    """Assemble the Review for a finished or stopped Line run from its Move outputs."""
    rep = load_repertoire(config_dir)
    criteria = load_criteria(config_dir)
    base = store.get(PositionSnapshot, f"pos_{run.launchId}_v{run.basePositionVersion}")
    if base is None:
        raise PreconditionError(f"base Position v{run.basePositionVersion} of {run.launchId} not found")
    executions = [e for e in store.list_for_launch(MoveExecution, run.launchId) if e.lineRunId == run.lineRunId]
    items = working_items(base.items, executions)
    review_id = f"rev_{run.launchId}_{len(store.list_for_launch(ReviewRun, run.launchId)) + 1}"
    e2 = [e for e in executions if "E2" in e.effectClasses and e.status == "succeeded" and e.models]
    rubric_version = next((p.get("rubricVersion") for e in e2 for p in e.proposals if p.get("rubricVersion")), None)
    with tracer.step("review", "review_assembler", "draft_review", right="draft_review") as step:
        step.set_inputs({"lineRunId": run.lineRunId, "basePositionVersion": run.basePositionVersion,
                         "executions": [e.executionId for e in executions]})
        findings = _assemble(store, rep, criteria.version, executions, items)
        review = ReviewRun(
            reviewId=review_id, launchId=run.launchId, lineRunId=run.lineRunId,
            question=rep.lines[run.lineId].reviewQuestion, basePositionVersion=run.basePositionVersion,
            evidenceCutoff=now.isoformat(), state="drafted", findings=findings, proposedItems=items,
            scopeStatement=load_settings(config_dir).scopeStatement, createdAt=now.isoformat(),
            mechanismStamp=mechanism_stamp(
                repertoire_version=rep.version, criteria_version=criteria.version, rubric_version=rubric_version,
                prompt_versions=[p for e in e2 if (p := rep.moves[e.moveId].promptVersion)],
                models=[ModelUse(served=m) for m in dict.fromkeys(m for e in e2 for m in e.models)],
            ),
        )
        store.insert(review)
        step.set_outputs({"reviewId": review_id, "findings": len(findings),
                          "kinds": sorted({f.kind for f in findings})})
        step.set_decision("drafted", "assembled from the Move outputs; awaiting the review queue")
    return review


# -- the review queue ------------------------------------------------------------------------------------


def _load(store: CampaignStore, review_id: str) -> ReviewRun:
    review = store.get(ReviewRun, review_id)
    if review is None:
        raise PreconditionError(f"Review {review_id} not found")
    return review


def _require(review: ReviewRun, state: str, hint: str) -> None:
    if review.state != state:
        raise PreconditionError(f"{review.reviewId} is {review.state}; {hint}")


def review_finding(store: CampaignStore, config_dir: Path, review_id: str, finding_id: str, *,
                   action: Literal["accept", "reject", "correct"], reason: str, by: str, role: str, now: datetime,
                   text: str | None = None, verdict: Verdict | None = None) -> ReviewRun:
    review = _load(store, review_id)
    authorize(store, load_roles(config_dir), launch_id=review.launchId, actor=by, role=role,
              action="review_finding", at=now.isoformat())
    _require(review, "drafted", "only a drafted Review's findings can be reviewed")
    if action == "correct" and not (text or "").strip():
        raise UsageError("a correction needs the corrected text")
    finding = next((f for f in review.findings if f.findingId == finding_id), None)
    if finding is None:
        raise UsageError(f"{review_id} has no finding {finding_id}")
    if verdict is not None and (finding.kind != "rubric" or action != "correct"):
        raise UsageError("a new verdict is only given when correcting a rubric finding")
    state = {"accept": "accepted", "reject": "rejected", "correct": "corrected"}[action]
    updated = finding.model_copy(update={"reviewState": state,
                                         "currentText": text if action == "correct" else finding.currentText,
                                         "verdict": verdict or finding.verdict})
    correction = Correction(
        correctionId=f"cor_{review_id}_{len(store.list_for_launch(Correction, review.launchId)) + 1}",
        reviewId=review_id, launchId=review.launchId, findingId=finding_id, action=action,
        originalText=finding.text, newText=text if action == "correct" else None,
        originalVerdict=finding.verdict if verdict else None, newVerdict=verdict, by=by, role=role, reason=reason,
        at=now.isoformat(),
    )
    tracer = campaign_tracer(store, config_dir, review.launchId)
    with tracer.step("review", "reviewer", "review_finding", right="review_finding") as step:
        step.set_inputs({"reviewId": review_id, "findingId": finding_id, "action": action, "by": by})
        store.insert(correction)
        review = review.model_copy(update={"findings": [updated if f.findingId == finding_id else f
                                                         for f in review.findings]})
        store.save(review)
        step.set_decision(state, reason)
    record_audit(store, launch_id=review.launchId, at=now.isoformat(), actor=by, role=role, action="review_finding",
                 right="review_finding", before=f"{review_id}#{finding_id}", after=correction.correctionId,
                 reason=reason)
    return review


def validate_review(store: CampaignStore, config_dir: Path, review_id: str, *, by: str, role: str,
                    now: datetime) -> ReviewRun:
    review = _load(store, review_id)
    authorize(store, load_roles(config_dir), launch_id=review.launchId, actor=by, role=role,
              action="validate_review", at=now.isoformat())
    _require(review, "drafted", "only a drafted Review can be validated")
    pending = [f.findingId for f in review.findings if f.reviewState == "pending"]
    if pending:
        raise PreconditionError(f"{review_id} still has pending findings: {', '.join(pending)}")
    tracer = campaign_tracer(store, config_dir, review.launchId)
    with tracer.step("review", "reviewer", "validate_review", right="validate_review") as step:
        step.set_inputs({"reviewId": review_id, "by": by})
        review = review.model_copy(update={"state": "validated", "validatedBy": by, "validatedAt": now.isoformat()})
        store.save(review)
        step.set_decision("validated", None)
    record_audit(store, launch_id=review.launchId, at=now.isoformat(), actor=by, role=role, action="validate_review",
                 right="validate_review", before=f"{review_id}:drafted", after=f"{review_id}:validated")
    return review


def _successor_items(review: ReviewRun, base: PositionSnapshot) -> list[PositionItem]:
    """The proposed items, minus what rejected findings changed, with corrected text carried over."""
    base_items = {i.itemId: i for i in base.items}
    items = {i.itemId: i for i in review.proposedItems}
    for f in review.findings:
        if f.sourceMove is None or f.kind == "escalation":
            continue  # items still open from earlier versions are kept as they were
        for ref in f.itemRefs:
            if f.reviewState == "rejected":
                if ref in base_items:
                    items[ref] = base_items[ref]
                else:
                    items.pop(ref, None)
            elif f.reviewState == "corrected" and ref in items and ref not in base_items:
                items[ref] = items[ref].model_copy(update={"text": f.currentText,
                                                           "note": "corrected by the reviewer"})
    return list(items.values())


def accept_review(store: CampaignStore, config_dir: Path, review_id: str, *, by: str, role: str, now: datetime,
                  reason: str | None = None) -> ReviewRun:
    review = _load(store, review_id)
    authorize(store, load_roles(config_dir), launch_id=review.launchId, actor=by, role=role, action="accept_review",
              at=now.isoformat())
    _require(review, "validated", "the reviewer must validate it first")
    base = store.get(PositionSnapshot, f"pos_{review.launchId}_v{review.basePositionVersion}")
    if base is None:
        raise PreconditionError(f"base Position v{review.basePositionVersion} not found")
    version = max(p.version for p in store.list_for_launch(PositionSnapshot, review.launchId)) + 1
    successor = PositionSnapshot(
        positionId=f"pos_{review.launchId}_v{version}", launchId=review.launchId, version=version, state="accepted",
        baseVersion=review.basePositionVersion, evidenceCutoff=review.evidenceCutoff, createdAt=now.isoformat(),
        origin=review_id, mechanismStamp=review.mechanismStamp, items=_successor_items(review, base),
    )
    tracer = campaign_tracer(store, config_dir, review.launchId)
    with tracer.step("review", "sponsor", "accept_review", right="accept_review") as step:
        step.set_inputs({"reviewId": review_id, "by": by, "reason": reason})
        with tracer.step("campaign_manager", "position_keeper", "commit_position", right="commit_position") as commit:
            commit.set_inputs({"base": review.basePositionVersion, "successor": version})
            store.commit_position(review.launchId, review.basePositionVersion, successor)
            commit.set_decision(f"v{version} accepted", f"v{review.basePositionVersion} superseded")
        review = review.model_copy(update={"state": "accepted", "decidedBy": by, "decidedAt": now.isoformat(),
                                           "decisionReason": reason, "committedPositionVersion": version})
        store.save(review)
        step.set_decision("accepted", reason)
    record_audit(store, launch_id=review.launchId, at=now.isoformat(), actor=by, role=role, action="accept_review",
                 right="accept_review", before=f"pos_{review.launchId}_v{review.basePositionVersion}",
                 after=successor.positionId, reason=reason)
    return review


def reject_review(store: CampaignStore, config_dir: Path, review_id: str, *, by: str, role: str, now: datetime,
                  reason: str) -> ReviewRun:
    review = _load(store, review_id)
    authorize(store, load_roles(config_dir), launch_id=review.launchId, actor=by, role=role, action="reject_review",
              at=now.isoformat())
    _require(review, "validated", "the reviewer must validate it first")
    tracer = campaign_tracer(store, config_dir, review.launchId)
    with tracer.step("review", "sponsor", "reject_review", right="reject_review") as step:
        step.set_inputs({"reviewId": review_id, "by": by, "reason": reason})
        review = review.model_copy(update={"state": "rejected", "decidedBy": by, "decidedAt": now.isoformat(),
                                           "decisionReason": reason})
        store.save(review)
        step.set_decision("rejected", reason)
    record_audit(store, launch_id=review.launchId, at=now.isoformat(), actor=by, role=role, action="reject_review",
                 right="reject_review", before=f"{review_id}:validated", after=f"{review_id}:rejected", reason=reason)
    return review
