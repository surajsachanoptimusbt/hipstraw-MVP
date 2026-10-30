"""Small builders for campaign records, shared by the campaign tests."""

from __future__ import annotations

from datetime import date

from hipstraw_mm.campaign.models import (
    Asset,
    Audience,
    AuditEvent,
    Budget,
    Correction,
    Delta,
    Deviation,
    Escalation,
    EvidenceRecord,
    EvidenceRequest,
    Finding,
    Launch,
    LineRecommendation,
    LineRun,
    Mandate,
    MechanismStamp,
    MoveExecution,
    Objective,
    PositionItem,
    PositionSnapshot,
    Product,
    Provenance,
    ReportRecord,
    ReviewRun,
    Strategy,
    TestPlan,
    content_hash,
)

LAUNCH = "lch_20261101T000000"
AT = "2026-11-01T09:00:00+00:00"


def stamp() -> MechanismStamp:
    return MechanismStamp(codeVersion="0.1.0", repertoireVersion="campaign-repertoire.v0.2")


def launch() -> Launch:
    return Launch(launchId=LAUNCH, owner="Demo Sponsor", market="US", productName="LedgerLoop", createdAt=AT)


def mandate(version: int = 1) -> Mandate:
    return Mandate(
        launchId=LAUNCH, version=version, createdAt=AT, createdBy="Demo Sponsor",
        product=Product(name="LedgerLoop", description="Catches invoice errors"),
        audience=Audience(description="AP managers"),
        market="US", dayZero=date(2026, 11, 11),
        objective=Objective(statement="Book 40 demo calls"),
        strategy=Strategy(channels=["email"], message="Stop paying wrong invoices",
                          budget=Budget(amount=5000, currency="USD")),
        assets=[Asset(assetId="A1", kind="email_copy", channel="email", text="Subject: ...")],
    )


def evidence(n: int = 1) -> EvidenceRecord:
    text = f"asset text {n}"
    return EvidenceRecord(
        evidenceId=f"ev_{LAUNCH}_{n}", launchId=LAUNCH, kind="asset", source="customer_submission",
        sourceRef="mandate:v1", capturedAt=AT, provenance=Provenance(by="Demo Sponsor", method="submission"),
        verificationState="reported", contentHash=content_hash(text), content=text, accessClass="D2",
    )


def item(item_id: str = "C01") -> PositionItem:
    return PositionItem(itemId=item_id, kind="claim", area="strategy", text="Audience is AP managers",
                        state="reported", evidenceRefs=[f"ev_{LAUNCH}_1"], setBy="intake")


def position(version: int = 1, state: str = "proposed", base: int | None = None) -> PositionSnapshot:
    return PositionSnapshot(
        positionId=f"pos_{LAUNCH}_v{version}", launchId=LAUNCH, version=version, state=state,  # type: ignore[arg-type]
        baseVersion=base, evidenceCutoff=AT, createdAt=AT, origin="intake" if version == 1 else "rev_x",
        mechanismStamp=stamp(), items=[item()],
    )


def line_run() -> LineRun:
    return LineRun(
        lineRunId=f"lrun_{LAUNCH}_1", launchId=LAUNCH, lineId="L01", lineVersion=1,
        repertoireVersion="campaign-repertoire.v0.2", chosenBy="Demo CM", chosenRole="campaign_manager",
        reason="Day Zero in 10 days", chosenAt=AT,
        recommendation=LineRecommendation(positionVersion=1, facts={}, eligible=[], excluded=[]),
        basePositionVersion=1, plannedStages=[["M01"], ["M04", "M05"], ["M12"]],
    )


def every_record() -> list[object]:
    """One instance of every stored record type."""
    return [
        launch(), mandate(), evidence(), position(), line_run(),
        MoveExecution(executionId="ex1", lineRunId=f"lrun_{LAUNCH}_1", launchId=LAUNCH, stageIndex=0,
                      moveId="M01", moveVersion=1, effectClasses=["E0"], status="succeeded", gate="allowed",
                      startedAt=AT, endedAt=AT),
        Deviation(deviationId="dv1", lineRunId=f"lrun_{LAUNCH}_1", launchId=LAUNCH, beforeStage=1,
                  type="skipped", moveId="M05", by="Demo CM", role="campaign_manager", reason="dates confirmed",
                  at=AT),
        ReviewRun(reviewId=f"rev_{LAUNCH}_1", launchId=LAUNCH, lineRunId=f"lrun_{LAUNCH}_1",
                  question="Ready?", basePositionVersion=1, evidenceCutoff=AT, state="drafted",
                  findings=[Finding(findingId="F01", area="readiness", kind="blocker", text="No tracking plan",
                                    currentText="No tracking plan", uncertainty="none")],
                  scopeStatement="scope", mechanismStamp=stamp(), createdAt=AT),
        Correction(correctionId="co1", reviewId=f"rev_{LAUNCH}_1", launchId=LAUNCH, findingId="F01",
                   action="correct", originalText="No tracking plan", newText="Tracking plan incomplete",
                   by="Demo Reviewer", role="reviewer", reason="plan exists but lacks UTMs", at=AT),
        AuditEvent(eventId="au1", launchId=LAUNCH, at=AT, actor="Demo Sponsor", role="sponsor",
                   action="submit_launch", right="submit_launch", correlationId="c1"),
        TestPlan(testPlanId="tp1", launchId=LAUNCH, lineRunId=f"lrun_{LAUNCH}_1", hypothesisItemId="H01",
                 hypothesis="Subject line B lifts opens", cohort="10% of list", method="A/B",
                 successCriteria="opens +3pt", stopRule="7 days"),
        EvidenceRequest(requestId="er1", launchId=LAUNCH, assumptionItemId="A01", question="Proof AP owns this?",
                        requestedFrom="Demo Sponsor", createdAt=AT),
        Escalation(escalationId="es1", launchId=LAUNCH, itemRefs=["B01"], reason="blocker open", to="Demo Sponsor",
                   createdAt=AT),
        Delta(deltaId="de1", launchId=LAUNCH, hypothesisItemId="H01", expected="+3pt opens",
              observedEvidenceRefs=[f"ev_{LAUNCH}_1"], attributionNotes="one week only", createdAt=AT),
        ReportRecord(reportId="rp1", launchId=LAUNCH, positionVersion=2, renderedAt=AT, path="r.md", sha256="x"),
    ]
