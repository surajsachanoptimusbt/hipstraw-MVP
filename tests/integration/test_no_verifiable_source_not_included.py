"""T034: a company without a verifiable source is never included (planning input, FR-007, FR-008, FR-013).

Runs the `basic` scenario (tests/fixtures/scenarios/basic.yaml) and checks the three companies that
cannot be verified, the two the rule checks exclude, and the invariant every `include` must satisfy.
None of these five has a judgement recording, so a judgement call for any of them fails the run.
"""

from __future__ import annotations

from tests.integration.harness import CompletedRun

# Which `unknowns` field covers a claim of each kind (data-model.md, companyRecords).
UNKNOWN_FIELD_FOR_CLAIM = {
    "hq": "hq",
    "employees": "size",
    "revenue": "size",
    "parent": "parent",
    "fit_buyer": "fit",
    "fit_problem": "fit",
    "fit_trigger": "fit",
    "signal_pain": "interestSignal",
    "signal_exploration": "interestSignal",
}


def _rule(decision: dict, rule: str) -> dict:
    matches = [r for r in decision["ruleResults"] if r["rule"] == rule]
    assert len(matches) == 1, f"expected one {rule!r} rule result, got {decision['ruleResults']}"
    return matches[0]


def test_website_that_does_not_load_is_excluded(basic_run: CompletedRun):
    """delta-none.test returns 404: existence fails, so Review excludes it without a judgement."""
    delta = basic_run.record("Delta None")
    assert delta["identifierCheck"]["status"] == "fails"
    assert delta["identifierCheck"]["httpStatus"] == 404
    assert delta["existenceEvidenceId"] is None

    decision = basic_run.decision(delta)
    assert decision["disposition"] == "exclude"
    assert _rule(decision, "existence")["outcome"] == "fail"
    assert decision["judgement"] is None


def test_every_failed_citation_becomes_an_unknown(basic_run: CompletedRun):
    """gamma-ops.test loads, but every evidence excerpt is a paraphrase, so no claim is stated as fact."""
    gamma = basic_run.record("Gamma Ops")
    assert gamma["identifierCheck"]["status"] == "resolves"

    claims = [
        e
        for e in basic_run.evidence()
        if e["companyRecordId"] == gamma["companyRecordId"] and e["claimField"] not in ("origin", "existence")
    ]
    assert claims, "the CompanyEvidence claims were not stored as evidence"
    for evidence in claims:
        assert evidence["check"] == {"status": "fail", "reason": "excerpt_not_found"}, evidence

    assert gamma["fitClaims"] == []
    assert gamma["interestSignals"] == []
    unknown_fields = {u["field"] for u in gamma["unknowns"]}
    for evidence in claims:
        assert UNKNOWN_FIELD_FOR_CLAIM[evidence["claimField"]] in unknown_fields, (
            evidence["claimField"],
            unknown_fields,
        )

    decision = basic_run.decision(gamma)
    assert decision["disposition"] == "needs_verification"
    assert decision["judgement"] is None


def test_registry_only_company_needs_verification(basic_run: CompletedRun):
    """Zeta Holdings LLC has no website: existence is unknown, and it is never fetched or judged."""
    zeta = basic_run.record("Zeta Holdings LLC")
    decision = basic_run.decision(zeta)
    assert decision["disposition"] == "needs_verification"
    assert _rule(decision, "existence")["outcome"] == "unknown"
    assert decision["judgement"] is None
    own_evidence = [
        e
        for e in basic_run.evidence()
        if e["companyRecordId"] == zeta["companyRecordId"] and e["claimField"] != "origin"
    ]
    assert own_evidence == [], "a registry-only company gets no existence or claim evidence"


def test_size_over_the_threshold_is_excluded_by_the_rule_checks(basic_run: CompletedRun):
    """sigma-scale.test cites "5,000+ employees": every other rule passes, but size fails (R6, R9)."""
    sigma = basic_run.record("Sigma Scale")
    assert sigma["size"]["status"] == "over"
    decision = basic_run.decision(sigma)
    assert decision["disposition"] == "exclude"
    assert _rule(decision, "size")["outcome"] == "fail"
    assert _rule(decision, "existence")["outcome"] == "pass"
    assert _rule(decision, "hq")["outcome"] == "pass"
    assert decision["judgement"] is None


def test_headquarters_outside_the_metros_is_excluded_by_the_rule_checks(basic_run: CompletedRun):
    """theta-works.test is headquartered in Chicago, IL: IL is outside every metro's states (R5, R9)."""
    theta = basic_run.record("Theta Works")
    assert theta["hq"]["city"] == "Chicago"
    assert theta["hq"]["state"] == "IL"
    assert theta["hq"]["status"] == "not_met"
    decision = basic_run.decision(theta)
    assert decision["disposition"] == "exclude"
    assert _rule(decision, "hq")["outcome"] == "fail"
    assert _rule(decision, "size")["outcome"] == "pass"
    assert decision["judgement"] is None


def test_no_include_without_a_verifiable_source(basic_run: CompletedRun):
    """Every include has a loading website, passing existence evidence, and a clean judgement (R9)."""
    decisions = basic_run.store.list_review_decisions(basic_run.run_id)
    by_name = {basic_run.record_name(d["companyRecordId"]): d for d in decisions}
    for name in ("Delta None", "Gamma Ops", "Zeta Holdings LLC", "Sigma Scale", "Theta Works"):
        assert by_name[name]["disposition"] != "include", name

    for decision in decisions:
        if decision["disposition"] != "include":
            continue
        record = basic_run.store.get_company_record(decision["companyRecordId"])
        assert record["identifierCheck"]["status"] == "resolves"
        existence = basic_run.store.get_evidence(record["existenceEvidenceId"])
        assert existence["check"]["status"] == "pass"
        assert all(r["outcome"] == "pass" for r in decision["ruleResults"]), decision["ruleResults"]
        judgement = decision["judgement"]
        assert judgement is not None
        assert judgement["falsifierMet"] is False
        assert judgement["fitHolds"] is True
        cited = [*judgement["citedEvidenceIds"]]
        for item in record["fitClaims"] + record["interestSignals"]:
            cited.extend(item["evidenceIds"])
        for evidence_id in cited:
            evidence = basic_run.store.get_evidence(evidence_id)
            assert evidence is not None and evidence["check"]["status"] == "pass", evidence_id

        # The system, not the model, attaches the record's passing evidence to the include decision.
        assert decision["evidenceIds"], "an include needs at least one passing evidence document"
        own = {record["companyRecordId"]}
        for evidence_id in decision["evidenceIds"]:
            evidence = basic_run.store.get_evidence(evidence_id)
            assert evidence is not None and evidence["check"]["status"] == "pass", evidence_id
            assert evidence["companyRecordId"] in own or evidence_id == record["origin"]["listingEvidenceId"]
        assert record["existenceEvidenceId"] in decision["evidenceIds"]
