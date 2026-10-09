"""Mapping a real feature 002 run (the recorded `basic` scenario) into market companies and evidence states."""

from __future__ import annotations

from hipstraw_mm.market import companies as comp
from hipstraw_mm.market.settings import load_pipeline_settings
from tests.integration.harness import RUN_ID, CompletedRun


def test_every_reviewed_record_maps_with_its_disposition(basic_run: CompletedRun) -> None:
    found = comp.companies_from_child_run(basic_run.store, RUN_ID)
    records = basic_run.records()
    assert {c["name"] for c in found} == {r["name"] for r in records}
    for c in found:
        decision = basic_run.store.get_review_decision(c["companyRecordId"])
        assert c["disposition"] == decision["disposition"]
        if c["disposition"] == "include":
            assert all(c["proofs"][p] is True for p in ("existence", "location", "size", "interest_signal"))
        for evidence_id in c["evidenceIds"]:
            assert basic_run.store.get_evidence(evidence_id)["check"]["status"] == "pass"


def test_evidence_states_and_packet_follow_the_reviewed_records(basic_run: CompletedRun) -> None:
    found = comp.companies_from_child_run(basic_run.store, RUN_ID)
    settings = load_pipeline_settings().evidenceStates.model_dump()
    states = comp.evidence_states(found, settings, {"evidence_sufficiency": "position_evaluation"})
    included = sum(1 for c in found if c["disposition"] == "include")
    assert (states["sufficiency"] == "insufficient") == (included == 0)
    assert states["detail"]["sufficiency"]["assessedBy"] == "position_evaluation"
    packet = comp.research_packet(RUN_ID, found)
    assert packet["found"] == len(found) and packet["included"] == included


def test_one_company_on_two_paths_keeps_both_dispositions(basic_run: CompletedRun) -> None:
    found = comp.companies_from_child_run(basic_run.store, RUN_ID)
    flipped = [{**c, "disposition": "exclude" if c["disposition"] != "exclude" else "include"} for c in found]
    merged = comp.merge_market_companies("mrun_x", [("p1", RUN_ID, found), ("p2", RUN_ID, flipped)])
    assert len(merged) == len(found)
    assert all(m["conflict"] for m in merged)
    assert all({link["pathId"] for link in m["links"]} == {"p1", "p2"} for m in merged)
