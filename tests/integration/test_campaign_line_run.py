"""T053/T060: L02 Strategy validation end to end with a canned model: M02 reads the pages, M06 judges the
rubric, M07 proposes a variant, M09 drafts its Test Plan, and the Review carries it all as findings."""

from __future__ import annotations

from hipstraw_mm.campaign.llm_outputs import Judgement, QuoteOut, Synthesis, Variant, Variants
from hipstraw_mm.campaign.models import EvidenceRecord, LineRun, ReviewRun, TestPlan
from hipstraw_mm.campaign.moves.common import PageRead
from hipstraw_mm.campaign.rubric import load_rubric
from hipstraw_mm.campaign.runner import run_line
from hipstraw_mm.campaign.selection import choose_line
from tests.unit.campaign_fake_model import CannedClient, CannedModels
from tests.unit.campaign_moves_support import CONFIG, NOW, launch

PAGE = "LedgerLoop flags invoice errors before payment. Book a free 90-day invoice audit."


def _page(url: str) -> PageRead:
    return PageRead(url=url, ok=True, text=PAGE)


def _synthesis(messages: list[dict[str, str]]) -> Synthesis:
    import json

    payload = json.loads(messages[1]["content"])
    page = next(e["evidenceId"] for e in payload["evidence"] if e["kind"] == "page_read")
    rubric = load_rubric(CONFIG)
    channels = [c["channel"] for c in payload["channels"]]
    judgements = [
        Judgement(questionId=qid, channel=channel, verdict="partly" if qid == "CR03" else "unknown",
                  reason="offer is concrete; next step is clear" if qid == "CR03" else "not in the evidence",
                  quotes=[QuoteOut(evidenceId=page, quote="Book a free 90-day invoice audit")] if qid == "CR03"
                  else [], fix=rubric.question(qid).fix)  # type: ignore[union-attr]
        for qid, channel in rubric.expected(channels)
    ]
    return Synthesis(judgements=judgements, assumptions=[], gaps=[])


def _variants(messages: list[dict[str, str]]) -> Variants:
    import json

    brief = json.loads(messages[1]["content"])["evidence"][0]["evidenceId"]
    return Variants(variants=[Variant(dimension="audience", text="Controllers at 200-2,000 person companies",
                                      rationale="they own payment accuracy", evidenceRefs=[brief],
                                      hypothesis="Targeting controllers lifts demo bookings")])


def test_l02_runs_to_a_review_with_rubric_findings_and_a_draft_test_plan() -> None:
    store, launch_id = launch()
    client = CannedClient({"Synthesis": _synthesis, "Variants": _variants})
    run = choose_line(store, CONFIG, launch_id, "L02", reason="assumptions unverified", by="Demo CM",
                      role="campaign_manager", now=NOW)
    run_line(store, CONFIG, run.lineRunId, by="Demo CM", role="campaign_manager", now=NOW, fetch=_page,
             model=CannedModels(llm=client))

    assert client.calls == 2
    assert [e.kind for e in store.list_for_launch(EvidenceRecord, launch_id)].count("page_read") == 2
    plans = store.list_for_launch(TestPlan, launch_id)
    assert len(plans) == 1 and plans[0].state == "draft"

    finished = store.get(LineRun, run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None and review.state == "drafted"
    rubric = [f for f in review.findings if f.kind == "rubric"]
    assert len(rubric) == 14 and all(f.isProposal for f in rubric)  # 5 per channel x 2, plus 4 campaign-wide
    cr03 = next(f for f in rubric if f.questionId == "CR03" and f.channel == "email")
    assert cr03.verdict == "partly" and cr03.quotes[0].quote == "Book a free 90-day invoice audit"
    assert cr03.currentText.startswith("CR03 Offer and one next step (Email): partly met.")
    assert any(f.kind == "proposal" for f in review.findings)
    assert any(f.kind == "test_plan" for f in review.findings)
    assert review.mechanismStamp.rubricVersion == "campaign-rubric.v0.2"
    assert "campaign_synthesis.v2" in review.mechanismStamp.promptVersions

    calls = [s for s in store.list_trace_steps(launch_id) if s["operation"] == "call_model"]
    assert len(calls) == 2 and all(s["promptBlobId"] and s["responseBlobId"] for s in calls)
    assert all(s["layer"] == "workers" and s["cost"]["inputTokens"] == 1200 for s in calls)
