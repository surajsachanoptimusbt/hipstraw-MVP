"""T081: discovery keeps the candidates that best match the first position (FR-022, research R19,
US1 acceptance scenario 9). Added after the first live run on 2026-10-07, which kept the first 10
entries of an alphabetical directory.

Scenario: tests/fixtures/scenarios/us1_targeting.yaml (discovery only).
"""

from __future__ import annotations

import pytest

from tests.integration.harness import CompletedRun, require_success, run_steps, step_counts

KEPT = {
    "Agate Billing",
    "Birch Payables",
    "Cobalt Contracts",
    "Yarrow Spend",
    "Fennel Invoice",
    "Garnet Procure",
    "Hazel Spend",
    "Iris Ledger",
    "Juniper Payables",
    "Lupine Labs",
}
DIRECTORY_FIRST_ENTRIES = {"Aardvark Rides", "Abacus Arcade", "Acorn Freight", "Adder Analytics", "Albatross Apps"}
PAGES = {
    "https://list.example.test/software-a-z",
    "https://list.example.test/atlanta-startups",
    "https://news.example.test/bay-area-saas-2026",
    "https://news.example.test/new-york-saas-2026",
}


@pytest.fixture
def targeting_run(harness_for) -> CompletedRun:
    return require_success(run_steps(harness_for("us1_targeting"), ("discover",)))


def _names(run: CompletedRun) -> set[str]:
    return {r["name"] for r in run.records()}


def test_the_ten_best_matching_candidates_are_kept(targeting_run):
    assert _names(targeting_run) == KEPT


def test_the_alphabetical_directory_s_off_target_first_entries_are_not_kept(targeting_run):
    assert not _names(targeting_run) & DIRECTORY_FIRST_ENTRIES


def test_a_location_that_is_not_in_the_entry_s_excerpt_does_not_count(targeting_run):
    # Nimbus Ledger's model output claims "Atlanta, GA", which is only in Agate Billing's line. Counted
    # as in-metro, Nimbus would outrank Lupine Labs for the tenth place.
    names = _names(targeting_run)
    assert "Nimbus Ledger" not in names
    assert "Lupine Labs" in names


def test_a_cited_place_outside_the_metros_overrides_the_model(targeting_run):
    # The model says Acorn Freight ("HQ Buffalo, NY") is in-metro and a strong match.
    names = _names(targeting_run)
    assert "Acorn Freight" not in names
    assert "Lupine Labs" in names


def test_origin_match_records_the_checked_ranking_inputs(targeting_run):
    assert targeting_run.record("Agate Billing")["origin"]["match"] == {
        "location": "Atlanta, GA",
        "metroMatch": "in",
        "positionMatch": "strong",
    }
    assert targeting_run.record("Garnet Procure")["origin"]["match"]["location"] == "Alpharetta, GA"
    assert targeting_run.record("Lupine Labs")["origin"]["match"]["positionMatch"] == "partial"


def test_every_planned_query_is_searched_and_the_cap_drops_nine(targeting_run):
    counts = step_counts(targeting_run, "discover")
    assert counts["searches"] == 4
    assert counts["candidatesFound"] == 19
    assert counts["kept"] == 10
    assert counts["droppedOverCap"] == 9
    run = targeting_run.store.get_run(targeting_run.run_id)
    assert run["counts"]["returned"] == 10
    assert run["counts"]["shortfall"] == 0
    assert run["shortfallReason"] is None


def test_listing_pages_are_capped_per_site_and_per_query(targeting_run):
    # Added at the T051 review. The test config caps listing pages at 2 per site and 3 per query.
    counts = step_counts(targeting_run, "discover")
    assert counts["pagesRead"] == 6
    assert counts["resultsOverSiteCap"] == 2  # list.example.test/software-a-z?page=2 and ?page=3
    assert counts["resultsOverQueryCap"] == 1  # atl-biz.test, the fourth Atlanta result


def test_every_kept_company_is_a_finding_traced_to_a_retrieved_page(targeting_run):
    evidence = {e["evidenceId"]: e for e in targeting_run.evidence()}
    for record in targeting_run.records():
        assert record["status"] == "finding"
        assert record["origin"]["resultUrl"] in PAGES
        origin = evidence[record["origin"]["listingEvidenceId"]]
        assert origin["url"] in PAGES
        assert origin["check"]["status"] == "pass"
        assert targeting_run.store.get_review_decision(record["companyRecordId"]) is None
