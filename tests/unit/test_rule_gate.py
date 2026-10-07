"""T079: the Review rule gate rows that changed after the first live run (research R9, 2026-10-07).

T059 adds one case for each remaining row of the research R9 table. Each test starts from a record
that passes every rule and changes one thing.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from hipstraw_mm.steps.review import rule_gate

RECORD_ID = "run_1__alpha-ledger-test"


def _ev(evidence_id: str, field: str, value: str, status: str = "pass") -> dict[str, Any]:
    return {
        "evidenceId": evidence_id,
        "companyRecordId": RECORD_ID,
        "claimField": field,
        "claimValue": value,
        "check": {"status": status, "reason": None if status == "pass" else "excerpt_not_found"},
        "reliability": "medium",
    }


BASE_EVIDENCE = {
    "ev1": _ev("ev1", "existence", "Alpha Ledger"),
    "ev2": _ev("ev2", "hq", "Atlanta, GA"),
    "ev3": _ev("ev3", "employees", "120"),
    "ev4": _ev("ev4", "signal_pain", "Accounts Payable Specialist hiring"),
}

BASE_RECORD: dict[str, Any] = {
    "companyRecordId": RECORD_ID,
    "name": "Alpha Ledger",
    "domain": "alpha-ledger.test",
    "identifierCheck": {
        "status": "resolves",
        "httpStatus": 200,
        "finalUrl": "https://alpha-ledger.test/",
        "failReason": None,
        "nameMatchesDomain": True,
    },
    "existenceEvidenceId": "ev1",
    "hq": {"city": "Atlanta", "state": "GA", "status": "met", "evidenceIds": ["ev2"]},
    "size": {"signals": [{"kind": "employees", "low": 120, "high": 120, "evidenceId": "ev3"}], "status": "under"},
    "parent": None,
    "interestSignals": [{"kind": "pain", "statement": "Hiring AP staff.", "evidenceIds": ["ev4"]}],
}


def _gate(record_changes: dict[str, Any] | None = None, evidence_changes: dict[str, Any] | None = None):
    record = copy.deepcopy(BASE_RECORD)
    record.update(record_changes or {})
    evidence = copy.deepcopy(BASE_EVIDENCE)
    evidence.update(evidence_changes or {})
    return rule_gate(record, evidence)


def _outcome(gate, rule: str) -> str:
    matches = [r["outcome"] for r in gate.rule_results if r["rule"] == rule]
    assert len(matches) == 1, f"expected one {rule!r} rule result, got {gate.rule_results}"
    return matches[0]


def _website(status: str, http_status: int | None, fail_reason: str | None, final_url: str | None = None) -> dict:
    return {
        "identifierCheck": {
            "status": status,
            "httpStatus": http_status,
            "finalUrl": final_url or "https://alpha-ledger.test/",
            "failReason": fail_reason,
            "nameMatchesDomain": True,
        },
        "existenceEvidenceId": None,
    }


def test_a_record_that_passes_every_rule_goes_on_to_judgement():
    gate = _gate()
    assert gate.disposition is None
    assert {r["rule"]: r["outcome"] for r in gate.rule_results} == {
        "existence": "pass",
        "hq": "pass",
        "size": "pass",
        "large_enterprise": "pass",
        "interest_signal": "pass",
    }


class TestWebsiteDoesNotExist:
    @pytest.mark.parametrize(
        ("http_status", "fail_reason", "cause"),
        [(404, "http_error", "HTTP 404"), (410, "http_error", "HTTP 410"), (None, "dns_error", "does not resolve")],
    )
    def test_excluded(self, http_status, fail_reason, cause):
        gate = _gate(_website("fails", http_status, fail_reason))
        assert gate.disposition == "exclude"
        assert _outcome(gate, "existence") == "fail"
        assert "does not exist" in gate.reason
        assert cause in gate.reason


class TestWebsiteCannotBeRead:
    @pytest.mark.parametrize(
        ("http_status", "fail_reason", "cause"),
        [
            (None, "robots_disallowed", "robots.txt"),
            (403, "http_error", "HTTP 403"),
            (429, "http_error", "HTTP 429"),
            (503, "http_error", "HTTP 503"),
        ],
    )
    def test_needs_verification_with_the_cause(self, http_status, fail_reason, cause):
        gate = _gate(_website("unreadable", http_status, fail_reason))
        assert gate.disposition == "needs_verification"
        assert _outcome(gate, "existence") == "unknown"
        assert "could not be read" in gate.reason
        assert cause in gate.reason

    def test_a_redirect_to_another_domain_names_where_it_went(self):
        gate = _gate(_website("unreadable", 301, "redirect_off_site", final_url="https://kappa-cloud.test/"))
        assert gate.disposition == "needs_verification"
        assert "redirect" in gate.reason
        assert "kappa-cloud.test" in gate.reason


class TestHeadquarters:
    def test_a_cited_city_outside_the_metros_in_a_metro_state_is_excluded(self):
        gate = _gate(
            {"hq": {"city": "Buffalo", "state": "NY", "status": "not_met", "evidenceIds": ["ev2"]}},
            {"ev2": _ev("ev2", "hq", "Buffalo, NY")},
        )
        assert gate.disposition == "exclude"
        assert _outcome(gate, "hq") == "fail"
        assert "Buffalo, NY" in gate.reason
        assert "outside" in gate.reason

    def test_citations_inside_and_outside_are_a_conflict_naming_both(self):
        gate = _gate(
            {"hq": {"city": "Atlanta", "state": "GA", "status": "conflict", "evidenceIds": ["ev2", "ev5"]}},
            {"ev5": _ev("ev5", "hq", "Austin, TX")},
        )
        assert gate.disposition == "needs_verification"
        assert _outcome(gate, "hq") == "conflict"
        assert "Atlanta, GA" in gate.reason
        assert "Austin, TX" in gate.reason

    def test_no_headquarters_citation_is_unknown(self):
        gate = _gate({"hq": {"city": None, "state": None, "status": "unknown", "evidenceIds": []}})
        assert gate.disposition == "needs_verification"
        assert _outcome(gate, "hq") == "unknown"
        assert "no passing headquarters citation" in gate.reason


class TestNameDomainMismatch:
    MISMATCH = {
        "name": "Addison Health Systems",
        "domain": "writepad.test",
        "identifierCheck": {
            "status": "resolves",
            "httpStatus": 200,
            "finalUrl": "https://writepad.test/",
            "failReason": None,
            "nameMatchesDomain": False,
        },
    }

    def test_a_homepage_citation_naming_the_company_passes_existence(self):
        gate = _gate(self.MISMATCH, {"ev1": _ev("ev1", "existence", "Addison Health Systems")})
        assert _outcome(gate, "existence") == "pass"
        assert gate.disposition is None

    def test_without_it_the_reason_names_the_website_and_the_company(self):
        failed = _ev("ev1", "existence", "Addison Health Systems", status="fail")
        gate = _gate(self.MISMATCH, {"ev1": failed})
        assert gate.disposition == "needs_verification"
        assert _outcome(gate, "existence") == "unknown"
        assert "writepad.test" in gate.reason
        assert "Addison Health Systems" in gate.reason


class TestParentCompany:
    def test_a_large_parent_excludes(self):
        parent = {"name": "Omega Conglomerate", "evidenceIds": ["ev6"], "status": "large"}
        gate = _gate({"parent": parent}, {"ev6": _ev("ev6", "parent", "Omega Conglomerate")})
        assert gate.disposition == "exclude"
        assert _outcome(gate, "large_enterprise") == "fail"
        assert "Omega Conglomerate" in gate.reason

    def test_a_parent_of_unknown_size_needs_verification(self):
        parent = {"name": "Pelican Group", "evidenceIds": ["ev6"], "status": "unknown_size"}
        gate = _gate({"parent": parent}, {"ev6": _ev("ev6", "parent", "Pelican Group")})
        assert gate.disposition == "needs_verification"
        assert _outcome(gate, "large_enterprise") == "unknown"
        assert "Pelican Group" in gate.reason

    def test_a_small_parent_passes(self):
        parent = {"name": "Wren Partners", "evidenceIds": ["ev6"], "status": "small"}
        gate = _gate({"parent": parent}, {"ev6": _ev("ev6", "parent", "Wren Partners")})
        assert gate.disposition is None
        assert _outcome(gate, "large_enterprise") == "pass"
