"""The read-only campaign page (Constitution XIII): `hipstraw-mm campaign view`.

Three views of one launch, for the three people who use it (Oct 30 meeting): the report (the answer, channel
by channel: is the message right for the audience each channel reaches, and is the channel ready), the
campaign as the customer submitted it (each channel with its audience and its assets as they will appear),
and the reviewer desk (what awaits a decision, and the decisions made). An audit view keeps the Position
history, the Lines used (tactic record), the evidence, and the trace of every gate decision and model call.
The database is opened read-only, so SQLite refuses any write; the server is the market viewer's (GET and HEAD
only, loopback only, Host header checked). Decisions are taken in the CLI; the page shows the command. The
page polls, so commands run in a terminal appear while it is open.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from hipstraw_mm.campaign.channels import channel_plans, load_channel_standards
from hipstraw_mm.campaign.config import load_settings
from hipstraw_mm.campaign.intake import asset_content
from hipstraw_mm.campaign.models import (
    Correction,
    Deviation,
    EvidenceRecord,
    Finding,
    Launch,
    LineRun,
    Mandate,
    MoveExecution,
    PositionItem,
    PositionSnapshot,
    ReviewRun,
    TestPlan,
)
from hipstraw_mm.campaign.repertoire import load_repertoire
from hipstraw_mm.campaign.review import rubric_head, rubric_reason, rubric_title
from hipstraw_mm.campaign.rubric import load_rubric
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.viewer.server import _Handler

Doc = dict[str, Any]
_CONTENT_LIMIT = 6000
_OPEN_ASSUMPTION = ("open", "awaiting_evidence")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _changes(base: PositionSnapshot, snapshot: PositionSnapshot) -> list[Doc]:
    before = {i.itemId: i for i in base.items}
    after = {i.itemId for i in snapshot.items}
    out: list[Doc] = []
    for item in snapshot.items:
        old = before.get(item.itemId)
        if old is None:
            out.append({"itemId": item.itemId, "kind": item.kind, "change": "added", "fromState": None,
                        "toState": item.state, "text": item.text})
        elif old.state != item.state or old.text != item.text:
            out.append({"itemId": item.itemId, "kind": item.kind, "change": "changed", "fromState": old.state,
                        "toState": item.state, "text": item.text})
    out += [{"itemId": i.itemId, "kind": i.kind, "change": "removed", "fromState": i.state, "toState": None,
             "text": i.text} for i in base.items if i.itemId not in after]
    return out


def _content(record: EvidenceRecord) -> tuple[str, bool]:
    text = record.content if isinstance(record.content, str) else json.dumps(record.content, indent=2,
                                                                              ensure_ascii=False)
    return text[:_CONTENT_LIMIT], len(text) > _CONTENT_LIMIT


class CampaignView:
    """Everything the page reads, shaped for it. Nothing here writes, and the connection could not."""

    def __init__(self, db_path: str, config_dir: Path, now: Callable[[], datetime] = _utc_now) -> None:
        self._db_path = Path(db_path)
        self._now = now
        self._rubric = load_rubric(config_dir)
        self._repertoire = load_repertoire(config_dir)
        self._standards = load_channel_standards(config_dir)
        settings = load_settings(config_dir)
        self._scope, self._markets = settings.scopeStatement, settings.launchMarkets
        self._store: SqliteCampaignStore | None = None

    def _db(self) -> SqliteCampaignStore | None:
        """Opened on first use, so the page can start before the first launch is submitted."""
        if self._store is None and self._db_path.is_file():
            self._store = SqliteCampaignStore.read_only(str(self._db_path))
        return self._store

    # -- routes ------------------------------------------------------------------------------------------

    def launches(self) -> list[Doc]:
        db = self._db()
        if db is None:
            return []
        rows = []
        for launch in reversed(db.list_all(Launch)):
            mandate, head = db.latest_mandate(launch.launchId), db.head_position(launch.launchId)
            rows.append({
                "launchId": launch.launchId, "productName": launch.productName, "market": launch.market,
                "createdAt": launch.createdAt, "dayZero": mandate.dayZero.isoformat() if mandate else None,
                "positionVersion": head.version if head else None, "positionState": head.state if head else None,
                "channels": [self._standards.name(c) for c in mandate.strategy.channels] if mandate else [],
            })
        return rows

    def launch(self, launch_id: str) -> Doc | None:
        db = self._db()
        if db is None:
            return None
        launch, mandate, head = db.get(Launch, launch_id), db.latest_mandate(launch_id), db.head_position(launch_id)
        if launch is None or mandate is None or head is None:
            return None
        reviews = db.list_for_launch(ReviewRun, launch_id)
        runs = db.list_for_launch(LineRun, launch_id)
        # The latest reviewer decision on each finding (accept, reject or correct), kept with its reason (C9).
        decisions = {(c.reviewId, c.findingId): c for c in db.list_for_launch(Correction, launch_id)}
        executions = db.list_for_launch(MoveExecution, launch_id)
        deviations = db.list_for_launch(Deviation, launch_id)
        evidence = db.list_for_launch(EvidenceRecord, launch_id)
        items = head.items
        rubric = self._rubric_view(reviews, decisions, mandate.strategy.channels)
        return {
            "launchId": launch_id, "productName": launch.productName, "market": launch.market,
            "owner": launch.owner, "createdAt": launch.createdAt, "scopeStatement": self._scope,
            "mandate": self._mandate(mandate),
            "head": {"version": head.version, "state": head.state},
            "counts": {
                "openBlockers": sum(1 for i in items if i.kind == "blocker" and i.state == "open"),
                "openAssumptions": sum(1 for i in items if i.kind == "assumption" and i.state in _OPEN_ASSUMPTION),
                "unknowns": sum(1 for i in items if i.kind == "unknown" and i.state == "open"),
                "hypotheses": sum(1 for i in items if i.kind == "hypothesis"),
                "reviews": len(reviews), "acceptedReviews": sum(1 for r in reviews if r.state == "accepted"),
            },
            "rubric": rubric,
            "channels": self._channels(mandate, rubric, executions, items, evidence),
            "desk": self._desk(reviews, decisions, runs),
            "positions": self._positions(db.list_for_launch(PositionSnapshot, launch_id)),
            "reviews": [self._review(r, decisions, runs) for r in reviews],
            "lineRuns": [self._line_run(r, executions, deviations) for r in runs],
            "evidence": [self._evidence(e) for e in evidence],
            "testPlans": [p.model_dump(mode="json") for p in db.list_for_launch(TestPlan, launch_id)],
        }

    def trace(self, launch_id: str) -> list[Doc]:
        db = self._db()
        steps = db.list_trace_steps(launch_id) if db else []
        for step in steps:
            step.pop("createdAt", None)
        return steps

    def blob(self, blob_id: str) -> Doc | None:
        db = self._db()
        blob = db.trace_sink().get_trace_blob(blob_id) if db else None
        if blob is None:
            return None
        return {key: blob.get(key) for key in ("blobId", "kind", "content", "truncated", "bytes")}

    def standards(self) -> Doc:
        """What a launch needs per channel (config/campaign/channels.yaml), for the console's form."""
        return {
            "version": self._standards.version, "markets": self._markets,
            "channels": {cid: {"name": s.name, "assetKind": s.assetKind, "setup": s.setup,
                               "assetFields": s.assetFields, "format": s.format}
                         for cid, s in self._standards.channels.items()},
        }

    # -- shapes ------------------------------------------------------------------------------------------

    def _mandate(self, m: Mandate) -> Doc:
        return {
            "version": m.version, "dayZero": m.dayZero.isoformat(),
            "daysToDayZero": (m.dayZero - self._now().date()).days,
            "product": m.product.description, "audience": m.audience.description,
            "objective": m.objective.statement, "successMeasure": m.objective.successMeasure,
            "message": m.strategy.message, "offer": m.strategy.offer, "channels": m.strategy.channels,
            "channelNames": {c: self._standards.name(c) for c in m.strategy.channels},
            "authorizedChannels": m.authorizedChannels,
            "budget": m.strategy.budget.model_dump() if m.strategy.budget else None,
            "approver": m.approver, "trackingPlan": m.trackingPlan,
            "assets": [{"assetId": a.assetId, "kind": a.kind, "channel": a.channel, "url": a.url,
                        "readyDate": a.readyDate.isoformat() if a.readyDate else None} for a in m.assets],
        }

    def _channels(self, m: Mandate, rubric: Doc | None, executions: list[MoveExecution],
                  items: list[PositionItem], evidence: list[EvidenceRecord]) -> list[Doc]:
        """Each channel as the customer planned it, with its answers: the rubric verdicts for this channel, the
        latest M13 checklist of its rules, and what is open on it."""
        checklist: dict[str, list[dict[str, Any]]] = {}
        for e in sorted((e for e in executions if e.moveId == "M13" and e.status == "succeeded"),
                        key=lambda e: e.endedAt):
            latest: dict[str, list[dict[str, Any]]] = {}
            for p in e.proposals:
                if p.get("type") == "standard":
                    latest.setdefault(p["channel"], []).append(
                        {k: p[k] for k in ("checkId", "text", "level", "status", "detail", "source")})
            checklist.update(latest)
        by_content = {(e.content if isinstance(e.content, str) else ""): e.evidenceId
                      for e in evidence if "#asset:" in e.sourceRef}
        out = []
        for plan in channel_plans(m):
            standard = self._standards.channels.get(plan.channel)
            checks = checklist.get(plan.channel)
            assets = [a for a in m.assets if a.channel == plan.channel]
            open_items = [i for i in items if i.channel == plan.channel and i.state == "open"
                          and i.kind in ("blocker", "unknown")]
            out.append({
                "channel": plan.channel, "name": self._standards.name(plan.channel), "known": standard is not None,
                "audience": plan.audience, "successMeasure": plan.successMeasure,
                "budget": plan.budget.model_dump() if plan.budget else None, "setup": plan.setup,
                "setupLabels": standard.setup if standard else {},
                "fieldLabels": standard.assetFields if standard else {},
                "reach": standard.reach.model_dump() if standard else None,
                "format": standard.format if standard else None,
                "assets": [{"assetId": a.assetId, "kind": a.kind, "readyDate": a.readyDate.isoformat()
                            if a.readyDate else None, "url": a.url, "text": a.text, "fields": a.fields,
                            "evidenceId": by_content.get(asset_content(a))} for a in assets],
                "verdicts": [q for q in rubric["questions"] if q["channel"] == plan.channel] if rubric else [],
                "standards": checks,
                "open": [{"itemId": i.itemId, "kind": i.kind, "text": i.text} for i in open_items],
                "counts": {
                    "blockers": sum(1 for i in open_items if i.kind == "blocker"),
                    "unknowns": sum(1 for i in open_items if i.kind == "unknown"),
                    "fixes": sum(1 for c in checks or [] if c["level"] == "should" and c["status"] == "not_met"),
                },
            })
        return out

    @staticmethod
    def _desk(reviews: list[ReviewRun], decisions: dict[tuple[str, str], Correction], runs: list[LineRun]) -> Doc:
        """What awaits a decision, oldest first, and the decisions already made, newest first (C9)."""
        lines = {r.lineRunId: r.lineId for r in runs}
        queue = [{
            "reviewId": r.reviewId, "lineId": lines.get(r.lineRunId), "question": r.question, "state": r.state,
            "pending": [f.model_dump(mode="json") for f in r.findings if f.reviewState == "pending"],
            "done": sum(1 for f in r.findings if f.reviewState != "pending"), "total": len(r.findings),
        } for r in reviews if r.state in ("drafted", "validated")]
        made = sorted(decisions.values(), key=lambda c: c.at, reverse=True)
        return {"queue": queue, "decisions": [c.model_dump(mode="json") for c in made]}

    def _rubric_view(self, reviews: list[ReviewRun], decisions: dict[tuple[str, str], Correction],
                     channels: list[str]) -> Doc | None:
        """The latest Review that judged the rubric, in any state: a drafted one shows as awaiting review. One row
        per question and channel (channel-scoped questions), or per question (campaign-wide ones)."""
        judged = [r for r in reviews if any(f.kind == "rubric" for f in r.findings)]
        if not judged:
            return None
        review = judged[-1]
        stamped = review.mechanismStamp.rubricVersion
        if stamped and stamped != self._rubric.version:
            return self._earlier_rubric(review, decisions, stamped)
        findings = {(f.questionId, f.channel or ""): f for f in review.findings if f.kind == "rubric"}
        questions = []
        for question_id, channel in self._rubric.expected(channels):
            q = self._rubric.question(question_id)
            assert q is not None
            f = findings.get((question_id, channel))
            head = rubric_head(q.id, q.title, self._standards.name(channel) if channel else None)
            decision = decisions.get((review.reviewId, f.findingId)) if f else None
            correction = None
            if f is not None and f.reviewState == "corrected" and decision is not None:
                correction = {"modelVerdict": decision.originalVerdict or f.verdict,
                              "modelReason": rubric_reason(f.text, head),
                              "by": decision.by, "reason": decision.reason, "at": decision.at}
            questions.append({
                "id": q.id, "title": q.title, "scope": q.scope, "channel": channel or None,
                "channelName": self._standards.name(channel) if channel else None,
                "area": q.area, "question": q.question,
                "met": q.met, "partly": q.partly, "notMet": q.notMet,
                "findingId": f.findingId if f else None,
                "verdict": f.verdict if f else None,
                "reason": rubric_reason(f.currentText, head) if f else None,
                "quotes": [quote.model_dump() for quote in f.quotes] if f else [],
                "fix": f.fix if f and f.fix else q.fix,
                "reviewState": f.reviewState if f else None,
                "rejectReason": decision.reason if f and f.reviewState == "rejected" and decision else None,
                "correction": correction,
            })
        return {"version": self._rubric.version, "current": True, "reviewId": review.reviewId,
                "reviewState": review.state, "basePositionVersion": review.basePositionVersion,
                "positionVersion": review.committedPositionVersion, "questions": questions}

    def _earlier_rubric(self, review: ReviewRun, decisions: dict[tuple[str, str], Correction],
                        version: str) -> Doc:
        """A Review judged with an earlier rubric version: its findings as they were judged, under their own
        question titles, never relabelled with the current rubric's questions."""
        questions = []
        for f in (f for f in review.findings if f.kind == "rubric"):
            title = rubric_title(f)
            head = rubric_head(f.questionId or "", title, self._standards.name(f.channel) if f.channel else None)
            decision = decisions.get((review.reviewId, f.findingId))
            questions.append({
                "id": f.questionId, "title": title, "scope": "channel" if f.channel else "campaign",
                "channel": f.channel, "channelName": self._standards.name(f.channel) if f.channel else None,
                "area": f.area, "question": "", "met": "", "partly": "", "notMet": "", "findingId": f.findingId,
                "verdict": f.verdict, "reason": rubric_reason(f.currentText, head),
                "quotes": [quote.model_dump() for quote in f.quotes], "fix": f.fix or "",
                "reviewState": f.reviewState,
                "rejectReason": decision.reason if f.reviewState == "rejected" and decision else None,
                "correction": {"modelVerdict": decision.originalVerdict or f.verdict,
                               "modelReason": rubric_reason(f.text, head), "by": decision.by,
                               "reason": decision.reason, "at": decision.at}
                if f.reviewState == "corrected" and decision else None,
            })
        return {"version": version, "current": False, "reviewId": review.reviewId, "reviewState": review.state,
                "basePositionVersion": review.basePositionVersion,
                "positionVersion": review.committedPositionVersion, "questions": questions}

    @staticmethod
    def _positions(snapshots: list[PositionSnapshot]) -> list[Doc]:
        by_version = {s.version: s for s in snapshots}
        out = []
        for s in sorted(snapshots, key=lambda s: s.version):
            base = by_version.get(s.baseVersion) if s.baseVersion is not None else None
            out.append({
                "version": s.version, "state": s.state, "baseVersion": s.baseVersion, "origin": s.origin,
                "createdAt": s.createdAt, "evidenceCutoff": s.evidenceCutoff,
                "items": [i.model_dump(mode="json") for i in s.items],
                "changes": _changes(base, s) if base else [],
                "stamp": s.mechanismStamp.model_dump(mode="json"),
            })
        return out

    @staticmethod
    def _finding(f: Finding, decision: Correction | None) -> Doc:
        return {**f.model_dump(mode="json"), "correction": decision.model_dump(mode="json") if decision else None}

    def _review(self, r: ReviewRun, decisions: dict[tuple[str, str], Correction], runs: list[LineRun]) -> Doc:
        run = next((x for x in runs if x.lineRunId == r.lineRunId), None)
        return {
            "reviewId": r.reviewId, "lineRunId": r.lineRunId, "lineId": run.lineId if run else None,
            "question": r.question, "state": r.state, "basePositionVersion": r.basePositionVersion,
            "committedPositionVersion": r.committedPositionVersion, "evidenceCutoff": r.evidenceCutoff,
            "createdAt": r.createdAt, "validatedBy": r.validatedBy, "validatedAt": r.validatedAt,
            "decidedBy": r.decidedBy, "decidedAt": r.decidedAt, "decisionReason": r.decisionReason,
            "findings": [self._finding(f, decisions.get((r.reviewId, f.findingId))) for f in r.findings],
            "stamp": r.mechanismStamp.model_dump(mode="json"),
        }

    def _line_run(self, run: LineRun, executions: list[MoveExecution], deviations: list[Deviation]) -> Doc:
        line = self._repertoire.lines.get(run.lineId)
        moves = self._repertoire.moves
        return {
            "lineRunId": run.lineRunId, "lineId": run.lineId, "lineName": line.name if line else run.lineId,
            "lineVersion": run.lineVersion, "repertoireVersion": run.repertoireVersion,
            "chosenBy": run.chosenBy, "chosenRole": run.chosenRole, "reason": run.reason, "chosenAt": run.chosenAt,
            "state": run.state, "basePositionVersion": run.basePositionVersion,
            "plannedStages": [[{"moveId": m, "moveName": moves[m].name if m in moves else m} for m in stage]
                              for stage in run.plannedStages],
            "nextStage": run.nextStage, "reviewId": run.reviewId,
            "recommendation": run.recommendation.model_dump(mode="json"),
            "executions": [{
                "stage": e.stageIndex + 1, "moveId": e.moveId,
                "moveName": moves[e.moveId].name if e.moveId in moves else e.moveId,
                "effectClasses": e.effectClasses, "status": e.status, "gate": e.gate, "note": e.note,
                "error": e.error, "models": e.models, "newItems": [i.itemId for i in e.newItems],
                "transitions": [t.model_dump(mode="json") for t in e.transitions], "produced": e.produced,
                "startedAt": e.startedAt, "endedAt": e.endedAt,
            } for e in executions if e.lineRunId == run.lineRunId],
            "deviations": [d.model_dump(mode="json") for d in deviations if d.lineRunId == run.lineRunId],
        }

    @staticmethod
    def _evidence(e: EvidenceRecord) -> Doc:
        text, truncated = _content(e)
        return {
            "evidenceId": e.evidenceId, "kind": e.kind, "source": e.source, "sourceRef": e.sourceRef,
            "capturedAt": e.capturedAt, "verificationState": e.verificationState, "uncertainty": e.uncertainty,
            "provenance": e.provenance.model_dump(), "content": text, "truncated": truncated,
        }


class CampaignHandler(_Handler):
    """The campaign page's routes on the market viewer's read-only handler."""

    page = "campaign.html"
    store: CampaignView

    def _session(self) -> Doc:
        """A viewer cannot change anything (constitution XIII); the console overrides this."""
        return {"writable": False}

    def _route(self, head: bool = False) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/":
            self._serve_index(head)
            return
        if path == "/api/session":
            self._json_response(200, self._session())
            return
        if path == "/api/standards":
            self._json_response(200, self.store.standards())
            return
        m = re.match(r"^/vendor/([^/]+)$", path)
        if m:
            self._serve_vendor(m.group(1), head)
            return
        if path == "/api/launches":
            self._json_response(200, self.store.launches())
            return
        m = re.match(r"^/api/launches/([^/]+)/trace$", path)
        if m:
            self._json_response(200, self.store.trace(unquote(m.group(1))))
            return
        for pattern, read, what in ((r"^/api/launches/([^/]+)$", self.store.launch, "launch"),
                                    (r"^/api/blobs/([^/]+)$", self.store.blob, "blob")):
            m = re.match(pattern, path)
            if m:
                found = read(unquote(m.group(1)))
                if found is None:
                    self._json_error(404, f"{what} {m.group(1)} not found")
                else:
                    self._json_response(200, found)
                return
        self._json_error(404, f"unknown route: {path}")
