"""T050: complete, evidenced company records (US1 acceptance scenarios 1-8, US2 scenarios 9-10).

Scenarios: tests/fixtures/scenarios/us1.yaml (evidence, parents, signal searches, confidence, cited
IDs) and us1_sites.yaml (websites that exist but cannot be read, websites that do not exist, and
name-domain mismatches). Recordings that must never be used are deliberately absent, so any denylisted,
robots-disallowed, or unexpected fetch, search, or model call fails the run.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.harness import CompletedRun, require_success, run_basic, step_counts

KNOWN_INTERESTS = {
    "continuous_obligation_intelligence",
    "invoice_accuracy_entitlement",
    "scope_drift_prevention",
    "payment_timing_working_capital",
    "supplier_commercial_position",
    "agent_governance_autonomy",
}
FR005_FIELDS = (
    "name",
    "domain",
    "origin",
    "identifierCheck",
    "existenceEvidenceId",
    "hq",
    "size",
    "parent",
    "fitClaims",
    "interestSignals",
    "unknowns",
    "falsifier",
    "confidence",
    "status",
)


@pytest.fixture
def us1_run(harness_for) -> CompletedRun:
    return require_success(run_basic(harness_for("us1")))


@pytest.fixture
def sites_run(harness_for) -> CompletedRun:
    return require_success(run_basic(harness_for("us1_sites")))


def _decision(run: CompletedRun, name: str) -> dict[str, Any]:
    return run.decision(run.record(name))


def _evidence(run: CompletedRun) -> dict[str, dict[str, Any]]:
    return {e["evidenceId"]: e for e in run.evidence()}


def _unknown_fields(record: dict[str, Any]) -> set[str]:
    return {u["field"] for u in record["unknowns"]}


class TestCompleteRecords:
    def test_every_record_has_the_fr005_fields_and_is_a_finding(self, us1_run):
        assert len(us1_run.records()) == 10
        for record in us1_run.records():
            for field in FR005_FIELDS:
                assert field in record, f"{record['name']}: missing {field}"
            assert record["status"] == "finding"
            assert 0 <= record["confidence"]["value"] <= 1
            assert record["confidence"]["band"] in {"High", "Medium", "Low"}
            for fit in record["fitClaims"]:
                assert fit["primaryInterestIds"], record["name"]
                assert set(fit["primaryInterestIds"]) <= KNOWN_INTERESTS

    def test_each_origin_traces_to_a_retrieved_page(self, us1_run):
        evidence = _evidence(us1_run)
        for record in us1_run.records():
            origin = evidence[record["origin"]["listingEvidenceId"]]
            assert origin["url"] == record["origin"]["resultUrl"]
            assert origin["check"]["status"] == "pass"
            assert record["name"] in origin["excerpt"]

    def test_confidence_is_computed_and_shown_in_the_report(self, us1_run):
        # Palisade Ledger: existence, location, size, and signal each rest on a medium-reliability page.
        assert us1_run.record("Palisade Ledger")["confidence"] == {"value": pytest.approx(0.7), "band": "Medium"}
        report = (us1_run.harness.reports_dir / f"{us1_run.run_id}.md").read_text(encoding="utf-8")
        assert "- Confidence: Medium" in report
        assert "not computed" not in report


class TestEvidenceHandling:
    def test_conflicting_employee_counts_are_both_kept(self, us1_run):
        quarry = us1_run.record("Quarry Spend")
        assert quarry["size"]["status"] == "conflict"
        assert sorted(s["low"] for s in quarry["size"]["signals"]) == [450, 620]
        decision = _decision(us1_run, "Quarry Spend")
        assert decision["disposition"] == "needs_verification"
        assert "450" in decision["reason"] and "620" in decision["reason"]

    def test_a_missing_interest_signal_is_an_explicit_unknown(self, us1_run):
        ridge = us1_run.record("Ridge Books")
        assert ridge["interestSignals"] == []
        assert "interestSignal" in _unknown_fields(ridge)
        assert _decision(us1_run, "Ridge Books")["disposition"] == "needs_verification"

    def test_the_unsourced_heavy_spend_signal_is_dropped(self, us1_run):
        saffron = us1_run.record("Saffron Bill")
        assert [s["kind"] for s in saffron["interestSignals"]] == ["pain"]
        assert not any("heavy" in s["statement"].casefold() for s in saffron["interestSignals"])
        failed = [e for e in us1_run.evidence() if e["claimValue"] == "heavy recurring SaaS spend"]
        assert len(failed) == 1 and failed[0]["check"] == {"status": "fail", "reason": "excerpt_not_found"}

    def test_every_kept_signal_and_fit_claim_rests_on_a_passing_citation(self, us1_run):
        evidence = _evidence(us1_run)
        for record in us1_run.records():
            for item in record["interestSignals"] + record["fitClaims"]:
                assert item["evidenceIds"], record["name"]
                assert all(evidence[i]["check"]["status"] == "pass" for i in item["evidenceIds"]), record["name"]

    def test_an_excerpt_with_an_email_address_is_withheld(self, us1_run):
        contact = [e for e in us1_run.evidence() if e["check"]["reason"] == "contains_contact_data"]
        assert len(contact) == 1
        assert contact[0]["excerpt"] == "[withheld: contact data]"
        assert not any("@" in e["excerpt"] for e in us1_run.evidence())

    def test_a_press_excerpt_naming_a_person_passes(self, us1_run):
        quote = [e for e in us1_run.evidence() if "Dana Whitfield" in e["excerpt"]]
        assert len(quote) == 1 and quote[0]["check"]["status"] == "pass"

    def test_an_office_is_not_the_headquarters(self, us1_run):
        hq = us1_run.record("Palisade Ledger")["hq"]
        assert (hq["city"], hq["state"], hq["status"]) == ("Palo Alto", "CA", "met")
        assert len(hq["evidenceIds"]) == 1


class TestSignalSearches:
    def test_a_job_board_signal_found_by_a_signal_search_is_kept(self, us1_run):
        tamarack = us1_run.record("Tamarack AP")
        evidence = _evidence(us1_run)
        (signal,) = tamarack["interestSignals"]
        (source,) = (evidence[i] for i in signal["evidenceIds"])
        assert source["url"] == "https://jobs.example.test/tamarack-ap/accounts-payable-specialist"
        assert source["sourceType"] == "job_board"
        assert source["reliability"] == "medium"
        assert _decision(us1_run, "Tamarack AP")["disposition"] == "include"

    def test_three_signal_searches_per_loading_website(self, us1_run):
        assert step_counts(us1_run, "verify")["signalSearches"] == 30  # ten loading websites

    def test_no_signal_searches_for_websites_that_did_not_load(self, sites_run):
        # Only Larch Health Systems, Sorrel Analytics, and Teasel Systems load; the others have no
        # search recordings.
        assert step_counts(sites_run, "verify")["signalSearches"] == 9


class TestHeadquartersAndParents:
    def test_a_cited_headquarters_outside_the_metros_excludes(self, us1_run):
        umber = us1_run.record("Umber Freight")
        assert (umber["hq"]["city"], umber["hq"]["state"], umber["hq"]["status"]) == ("Buffalo", "NY", "not_met")
        decision = _decision(us1_run, "Umber Freight")
        assert decision["disposition"] == "exclude"
        assert "Buffalo, NY" in decision["reason"]

    def test_a_parent_on_the_configured_list_excludes(self, us1_run):
        assert us1_run.record("Vetch Payments")["parent"]["status"] == "large"
        decision = _decision(us1_run, "Vetch Payments")
        assert decision["disposition"] == "exclude"
        assert "Omega Conglomerate" in decision["reason"]

    def test_a_parent_shown_over_the_thresholds_excludes(self, us1_run):
        parent = us1_run.record("Xenon Contracts")["parent"]
        assert (parent["name"], parent["status"]) == ("Heron Holdings", "large")
        assert _decision(us1_run, "Xenon Contracts")["disposition"] == "exclude"

    def test_a_parent_of_unknown_size_needs_verification(self, us1_run):
        assert us1_run.record("Willow Invoice")["parent"]["status"] == "unknown_size"
        decision = _decision(us1_run, "Willow Invoice")
        assert decision["disposition"] == "needs_verification"
        assert "Pelican Group" in decision["reason"]


class TestReview:
    def test_a_judgement_citing_unknown_evidence_is_not_included(self, us1_run):
        decision = _decision(us1_run, "Yucca Procure")
        assert decision["disposition"] == "needs_verification"
        assert "judgement cited unknown evidence" in decision["reason"]

    def test_dispositions(self, us1_run):
        dispositions = {r["name"]: _decision(us1_run, r["name"])["disposition"] for r in us1_run.records()}
        assert dispositions == {
            "Palisade Ledger": "include",
            "Quarry Spend": "needs_verification",
            "Ridge Books": "needs_verification",
            "Saffron Bill": "include",
            "Tamarack AP": "include",
            "Umber Freight": "exclude",
            "Vetch Payments": "exclude",
            "Willow Invoice": "needs_verification",
            "Xenon Contracts": "exclude",
            "Yucca Procure": "needs_verification",
        }

    def test_counts_stay_within_every_budget(self, us1_run, test_config):
        budgets = test_config.run.budgets
        discover = step_counts(us1_run, "discover")
        verify = step_counts(us1_run, "verify")
        assert discover["searches"] <= budgets.discoveryQueries
        assert discover["pagesRead"] <= budgets.listingPagesFetched
        assert verify["fetches"] <= budgets.verifyFetchesPerRun
        assert verify["modelCalls"] <= budgets.verifyModelCallsPerRun
        assert us1_run.store.get_run(us1_run.run_id)["counts"]["returned"] <= budgets.companiesKept


class TestWebsites:
    """us1_sites: a website that exists but cannot be read is needs verification; one that does not
    exist is excluded (FR-008, FR-013, 2026-10-07)."""

    @pytest.mark.parametrize(
        ("name", "http_status", "fail_reason", "cause"),
        [
            ("Lark Robots", None, "robots_disallowed", "robots.txt"),
            ("Maple Forbidden", 403, "http_error", "HTTP 403"),
            ("Nettle Throttle", 429, "http_error", "HTTP 429"),
            ("Rowan Down", 503, "http_error", "HTTP 503"),
        ],
    )
    def test_unreadable_websites_need_verification(self, sites_run, name, http_status, fail_reason, cause):
        record = sites_run.record(name)
        check = record["identifierCheck"]
        assert (check["status"], check["httpStatus"], check["failReason"]) == ("unreadable", http_status, fail_reason)
        assert record["existenceEvidenceId"] is None
        existence = [u for u in record["unknowns"] if u["field"] == "existence"]
        assert len(existence) == 1 and cause in existence[0]["reason"]
        decision = _decision(sites_run, name)
        assert decision["disposition"] == "needs_verification"
        assert "could not be read" in decision["reason"]
        assert cause in decision["reason"]

    @pytest.mark.parametrize(
        ("name", "fail_reason", "cause"),
        [("Oxbow Gone", "http_error", "HTTP 410"), ("Pine Nowhere", "dns_error", "does not resolve")],
    )
    def test_websites_that_do_not_exist_are_excluded(self, sites_run, name, fail_reason, cause):
        record = sites_run.record(name)
        assert (record["identifierCheck"]["status"], record["identifierCheck"]["failReason"]) == ("fails", fail_reason)
        decision = _decision(sites_run, name)
        assert decision["disposition"] == "exclude"
        assert "does not exist" in decision["reason"]
        assert cause in decision["reason"]

    def test_no_evidence_is_gathered_for_websites_that_did_not_load(self, sites_run):
        names = ("Larch Health Systems", "Sorrel Analytics", "Teasel Systems")
        loaded = {sites_run.record(n)["companyRecordId"] for n in names}
        own = {e["companyRecordId"] for e in sites_run.evidence() if e["companyRecordId"] is not None}
        assert own == loaded

    def test_a_mismatched_domain_that_names_the_company_passes_existence(self, sites_run):
        larch = sites_run.record("Larch Health Systems")
        assert larch["identifierCheck"]["nameMatchesDomain"] is False
        existence = _evidence(sites_run)[larch["existenceEvidenceId"]]
        assert existence["check"]["status"] == "pass"
        assert "Larch Health Systems" in existence["excerpt"]
        assert _decision(sites_run, "Larch Health Systems")["disposition"] == "include"

    def test_an_about_page_already_fetched_can_supply_the_existence_citation(self, sites_run):
        # Added at the T051 review (FR-016): brightform.test's homepage never names Teasel Systems.
        teasel = sites_run.record("Teasel Systems")
        assert teasel["identifierCheck"]["nameMatchesDomain"] is False
        existence = _evidence(sites_run)[teasel["existenceEvidenceId"]]
        assert existence["url"] == "https://brightform.test/about"
        assert existence["excerpt"] == "BrightForm is built by Teasel Systems, Inc."
        assert existence["check"]["status"] == "pass"
        assert _decision(sites_run, "Teasel Systems")["disposition"] == "include"

    def test_a_mismatched_domain_that_does_not_name_the_company_needs_verification(self, sites_run):
        sorrel = sites_run.record("Sorrel Analytics")
        assert sorrel["identifierCheck"]["nameMatchesDomain"] is False
        decision = _decision(sites_run, "Sorrel Analytics")
        assert decision["disposition"] == "needs_verification"
        assert "tallyhub.test" in decision["reason"]
        assert "Sorrel Analytics" in decision["reason"]

    def test_the_shortfall_is_recorded(self, sites_run):
        run = sites_run.store.get_run(sites_run.run_id)
        assert (run["counts"]["returned"], run["counts"]["shortfall"]) == (9, 1)
        assert run["shortfallReason"]

    def test_denylisted_and_robots_disallowed_results_are_never_fetched(self, sites_run):
        # Neither URL has a page recording, so fetching either would have failed the run.
        assert {r["origin"]["resultUrl"] for r in sites_run.records()} == {"https://list.example.test/ny-saas"}
