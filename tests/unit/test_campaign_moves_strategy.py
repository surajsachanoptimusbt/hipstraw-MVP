"""M06 judges the campaign rubric and M07 proposes variants, through the task router, with honest output."""

from __future__ import annotations

import json

from hipstraw_mm.campaign.llm_outputs import Judgement, QuoteOut, Synthesis, Variant, Variants
from hipstraw_mm.campaign.models import EvidenceRecord
from hipstraw_mm.campaign.rubric import load_rubric
from tests.unit.campaign_fake_model import CannedClient, CannedModels
from tests.unit.campaign_moves_support import CONFIG, context, launch, run

RUBRIC = load_rubric(CONFIG)
CHANNELS = ["email", "linkedin_ads"]  # tests/fixtures/campaign/launch_complete.yaml


def _brief(store: object, launch_id: str) -> EvidenceRecord:
    return next(e for e in store.list_for_launch(EvidenceRecord, launch_id)  # type: ignore[attr-defined]
                if e.sourceRef.endswith("#brief"))


def _synthesis(brief_id: str, *, fabricate: bool = False, skip_last: bool = False) -> Synthesis:
    """CR01 Message fits the audience is judged for email from the brief; everything else is unknown."""
    judgements = []
    for question_id, channel in RUBRIC.expected(CHANNELS):
        q = RUBRIC.question(question_id)
        assert q is not None
        if (question_id, channel) == ("CR01", "email"):
            quote = "the problem nobody has written" if fabricate else "Stop paying wrong invoices"
            judgements.append(Judgement(questionId=q.id, channel=channel, verdict="partly",
                                        reason="names the problem, not for AP",
                                        quotes=[QuoteOut(evidenceId=brief_id, quote=quote)],
                                        fix="name the AP manager's pain: duplicate and mispriced invoices"))
        else:
            judgements.append(Judgement(questionId=q.id, channel=channel, verdict="unknown",
                                        reason="not in the evidence", quotes=[], fix=q.fix))
    if skip_last:
        judgements = judgements[:-1]
    return Synthesis(judgements=judgements, assumptions=[], gaps=[])


def test_m06_judges_every_question_with_quotes() -> None:
    store, launch_id = launch()
    brief = _brief(store, launch_id)
    client = CannedClient({"Synthesis": _synthesis(brief.evidenceId)})
    out = run(context(store, launch_id, "M06", model=CannedModels(llm=client)))
    assert out.status == "succeeded" and out.transitions == [] and out.newItems == []
    rubric = [p for p in out.proposals if p["type"] == "rubric"]
    assert [(p["questionId"], p["channel"] or "") for p in rubric] == RUBRIC.expected(CHANNELS)
    cr01 = next(p for p in rubric if (p["questionId"], p["channel"]) == ("CR01", "email"))
    assert cr01["verdict"] == "partly" and cr01["quotes"][0]["evidenceId"] == brief.evidenceId
    assert cr01["fix"].startswith("name the AP") and cr01["rubricVersion"] == "campaign-rubric.v0.2"
    assert cr01["channelName"] == "Email"
    assert {p["channel"] for p in rubric if p["questionId"] == "CR06"} == {None}  # campaign-wide: judged once
    assert out.models == ["gpt-test"]
    payload = json.loads(client.prompts[0][1]["content"])
    assert {q["id"] for q in payload["rubric"]} == {q.id for q in RUBRIC.questions}
    assert brief.evidenceId in {e["evidenceId"] for e in payload["evidence"]}
    email, linkedin = payload["channels"]
    assert (email["channel"], email["name"], linkedin["name"]) == ("email", "Email", "LinkedIn ads")
    assert email["audienceOnChannel"].startswith("1,800 AP managers") and email["reach"]["fitsPoorly"]
    assert len(email["assets"]) == 1 and len(linkedin["assets"]) == 1


def test_m06_downgrades_an_unverifiable_quote_to_unknown() -> None:
    store, launch_id = launch()
    client = CannedClient({"Synthesis": _synthesis(_brief(store, launch_id).evidenceId, fabricate=True)})
    out = run(context(store, launch_id, "M06", model=CannedModels(llm=client)))
    cr01 = next(p for p in out.proposals if (p.get("questionId"), p.get("channel")) == ("CR01", "email"))
    assert cr01["verdict"] == "unknown" and cr01["quotes"] == []
    assert "could not be found word for word" in cr01["reason"]


def test_m06_marks_an_unjudged_question_unknown() -> None:
    store, launch_id = launch()
    client = CannedClient({"Synthesis": _synthesis(_brief(store, launch_id).evidenceId, skip_last=True)})
    out = run(context(store, launch_id, "M06", model=CannedModels(llm=client)))
    last = next(p for p in out.proposals if p.get("questionId") == RUBRIC.questions[-1].id)
    assert last["verdict"] == "unknown" and "not judged" in last["reason"]


def test_m06_without_a_model_is_blocked_not_guessed() -> None:
    store, launch_id = launch()
    out = run(context(store, launch_id, "M06"))
    assert out.status == "blocked" and "no model" in (out.note or "")


def test_m07_proposes_variants_as_hypotheses() -> None:
    store, launch_id = launch()
    brief = _brief(store, launch_id)
    variants = Variants(variants=[Variant(
        dimension="message", text="Your AP team pays 1 in 100 invoices wrong. Find out which, free.",
        rationale="names the buyer and the pain", evidenceRefs=[brief.evidenceId],
        hypothesis="A message naming AP managers' duplicate payments lifts demo bookings")])
    out = run(context(store, launch_id, "M07", model=CannedModels(llm=CannedClient({"Variants": variants}))))
    assert [(i.kind, i.state, i.setBy) for i in out.newItems] == [("hypothesis", "proposed", "M07")]
    assert out.newItems[0].text.startswith("message:") and out.newItems[0].evidenceRefs == [brief.evidenceId]
    assert [p["type"] for p in out.proposals] == ["variant"]


def test_m06_does_not_repeat_assumptions_the_position_already_holds() -> None:
    from hipstraw_mm.campaign.llm_outputs import AssumptionOut

    store, launch_id = launch()
    brief = _brief(store, launch_id)
    synthesis = _synthesis(brief.evidenceId).model_copy(update={"assumptions": [
        AssumptionOut(text="The stated audience has the problem the message names.", core=True, evidenceRefs=[]),
        AssumptionOut(text="AP teams can share 90 days of invoices without legal review", core=True,
                      evidenceRefs=[brief.evidenceId]),
    ]})
    out = run(context(store, launch_id, "M06", model=CannedModels(llm=CannedClient({"Synthesis": synthesis}))))
    assert [p["text"] for p in out.proposals if p["type"] == "assumption"] == [
        "AP teams can share 90 days of invoices without legal review"]


def test_m06_does_not_repeat_open_unknowns_as_gaps() -> None:
    from hipstraw_mm.campaign.llm_outputs import GapOut

    store, launch_id = launch("launch_missing_landing.yaml")
    brief = _brief(store, launch_id)
    synthesis = _synthesis(brief.evidenceId).model_copy(update={"gaps": [
        GapOut(text="Landing page not provided.", area="readiness", itemRefs=["U01"], evidenceRefs=[]),
        GapOut(text="No proof points", area="strategy", itemRefs=[], evidenceRefs=[]),
    ]})
    out = run(context(store, launch_id, "M06", model=CannedModels(llm=CannedClient({"Synthesis": synthesis}))))
    assert [p["text"] for p in out.proposals if p["type"] == "gap"] == ["No proof points"]
