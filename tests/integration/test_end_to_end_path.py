"""T033: the thin end-to-end path on the `basic` replay scenario, every step through `cli.main`.

Scenario: tests/fixtures/scenarios/basic.yaml. Sockets are blocked, and a call with no recording
raises ReplayMissingError, so the run cannot reach anything the scenario does not define.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from hipstraw_mm.models import normalize_company_name
from tests.integration.harness import CANDIDATE_ID, POSITION_FILE, RUN_ID, STEPS, CompletedRun, run_basic

LISTING_URL = "https://list.example.test/atlanta-saas"
PROFILE_URL = "https://list.example.test/companies/beta"
REGISTRY_URL = "https://registry.example.test/ga/search"
EPSILON_URL = "https://epsilon-pay.test/"

EXPECTED_RECORD_IDS = {
    f"{RUN_ID}__alpha-ledger-test",
    f"{RUN_ID}__beta-billing-test",
    f"{RUN_ID}__gamma-ops-test",
    f"{RUN_ID}__delta-none-test",
    f"{RUN_ID}__sigma-scale-test",
    f"{RUN_ID}__theta-works-test",
    f"{RUN_ID}__epsilon-pay-test",
    f"{RUN_ID}__registry-zeta-holdings-llc",
}
STATUS_AFTER = {"discover": "discovered", "verify": "verified", "review": "reviewed", "report": "reported"}


def _headings(markdown: str) -> list[tuple[int, str]]:
    """(level, text) for each markdown heading, with any leading "6." style number removed."""
    out = []
    for line in markdown.splitlines():
        m = re.match(r"^(#{1,6})\s+(?:\d+\.\s*)?(.*\S)\s*$", line)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


def _section(markdown: str, title: str) -> str:
    """The text under the level-1 or level-2 heading that starts with `title`, up to the next one."""
    lines = markdown.splitlines()
    start = None
    for i, line in enumerate(lines):
        m = re.match(r"^#{1,2}\s+(?:\d+\.\s*)?(.*)$", line)
        if not m:
            continue
        if start is not None:
            return "\n".join(lines[start:i])
        if m.group(1).casefold().startswith(title.casefold()):
            start = i + 1
    return "\n".join(lines[start:]) if start is not None else ""


def test_every_command_succeeds_and_the_run_reaches_reported(harness_for):
    run = run_basic(harness_for("basic"))
    for command, result in run.results.items():
        assert result.code == 0, f"`{command}` exited with {result.code}: {result.stderr}"
    assert run.results["position"].json["runId"] == RUN_ID
    assert run.results["position"].json["status"] == "created"
    for step in STEPS:
        assert run.results[step].json["status"] == STATUS_AFTER[step]
    assert run.store.get_run(RUN_ID)["status"] == "reported"


def test_every_origin_kind_appears(basic_run: CompletedRun):
    assert basic_run.record("Alpha Ledger")["origin"]["kind"] == "listing_link"
    assert basic_run.record("Gamma Ops")["origin"]["kind"] == "listing_link"
    assert basic_run.record("Delta None")["origin"]["kind"] == "listing_link"
    assert basic_run.record("Sigma Scale")["origin"]["kind"] == "listing_link"
    assert basic_run.record("Theta Works")["origin"]["kind"] == "listing_link"

    beta = basic_run.record("Beta Billing")["origin"]
    assert beta["kind"] == "profile_hop"
    assert beta["resultUrl"] == LISTING_URL
    assert beta["profileUrl"] == PROFILE_URL

    epsilon = basic_run.record("Epsilon Pay")["origin"]
    assert epsilon["kind"] == "direct_homepage"
    assert epsilon["resultUrl"] == EPSILON_URL
    assert epsilon["searchQuery"] == "Atlanta recurring vendor invoice payments software"

    zeta = basic_run.record("Zeta Holdings LLC")["origin"]
    assert zeta["kind"] == "registry_only"
    assert zeta["resultUrl"] == REGISTRY_URL


def test_every_record_traces_to_a_passing_origin_citation(basic_run: CompletedRun):
    """FR-006: each company comes from a retrieved page, and its origin excerpt names it."""
    for record in basic_run.records():
        origin = record["origin"]
        evidence = basic_run.store.get_evidence(origin["listingEvidenceId"])
        assert evidence is not None, record["name"]
        assert evidence["claimField"] == "origin"
        assert evidence["check"]["status"] == "pass"
        assert record["name"].casefold() in evidence["excerpt"].casefold()
        assert evidence["url"] in {origin["resultUrl"], origin.get("profileUrl")}


def test_registry_only_record_has_explicit_unknowns(basic_run: CompletedRun):
    """FR-005 and FR-008: no website, no fit, no signals, no falsifier, and all of it stated as unknown."""
    zeta = basic_run.record("Zeta Holdings LLC")
    assert zeta["companyRecordId"] == f"{RUN_ID}__registry-zeta-holdings-llc"
    assert zeta["domain"] is None
    assert zeta["identifierCheck"]["status"] == "no_website"
    assert zeta["existenceEvidenceId"] is None
    assert zeta["falsifier"] is None
    assert zeta["fitClaims"] == []
    assert zeta["interestSignals"] == []
    unknown_fields = {u["field"] for u in zeta["unknowns"]}
    assert {"fit", "interestSignal", "falsifier"} <= unknown_fields


def test_merge_rule_keeps_only_the_website_record(basic_run: CompletedRun):
    """ "Alpha Ledger, Inc." on the registry page is the same company as alpha-ledger.test."""
    alphas = [r for r in basic_run.records() if normalize_company_name(r["name"]) == "alpha ledger"]
    assert len(alphas) == 1
    assert alphas[0]["domain"] == "alpha-ledger.test"
    assert alphas[0]["companyRecordId"] == f"{RUN_ID}__alpha-ledger-test"
    # Its registry entry was dropped before anything was written: no origin evidence names it.
    registry_evidence = [e for e in basic_run.evidence() if e["url"] == REGISTRY_URL]
    assert [e["claimValue"] for e in registry_evidence] == ["Zeta Holdings LLC"]


def test_run_counts_and_shortfall(basic_run: CompletedRun):
    discover_end = next(
        e for e in basic_run.harness.log_events(RUN_ID) if e["event"] == "step_end" and e["step"] == "discover"
    )
    assert discover_end["counts"]["searches"] == 3  # one per planned query
    run = basic_run.store.get_run(RUN_ID)
    assert run["counts"]["returned"] == 8
    assert run["counts"]["shortfall"] == 2
    assert run["shortfallReason"]


def test_each_step_logs_start_and_end_with_counts(basic_run: CompletedRun):
    events = basic_run.harness.log_events(RUN_ID)
    for step in STEPS:
        starts = [i for i, e in enumerate(events) if e["event"] == "step_start" and e["step"] == step]
        ends = [i for i, e in enumerate(events) if e["event"] == "step_end" and e["step"] == step]
        assert len(starts) == 1, f"{step}: {len(starts)} step_start events"
        assert len(ends) == 1, f"{step}: {len(ends)} step_end events"
        assert starts[0] < ends[0]
        counts = events[ends[0]].get("counts")
        assert isinstance(counts, dict) and counts, f"{step}: step_end has no counts"
        assert all(isinstance(v, int) for v in counts.values()), f"{step}: {counts}"
        assert all(e["runId"] == RUN_ID for e in events)


def test_every_loading_website_has_existence_evidence_naming_the_company(basic_run: CompletedRun):
    """FR-016: built from the homepage without a model; its excerpt contains the company name."""
    loading = [r for r in basic_run.records() if r["identifierCheck"]["status"] == "resolves"]
    assert {r["name"] for r in loading} == {
        "Alpha Ledger",
        "Beta Billing",
        "Gamma Ops",
        "Epsilon Pay",
        "Sigma Scale",
        "Theta Works",
    }
    for record in loading:
        evidence = basic_run.store.get_evidence(record["existenceEvidenceId"])
        assert evidence is not None, record["name"]
        assert evidence["claimField"] == "existence"
        assert evidence["companyRecordId"] == record["companyRecordId"]
        assert evidence["url"] == record["identifierCheck"]["finalUrl"] == f"https://{record['domain']}/"
        assert evidence["check"]["status"] == "pass"
        assert record["name"].casefold() in evidence["excerpt"].casefold()
        assert len(evidence["excerpt"]) <= 300


def test_records_are_findings_with_exactly_one_review_decision(basic_run: CompletedRun):
    records = basic_run.records()
    assert len(records) <= 10
    assert {r["companyRecordId"] for r in records} == EXPECTED_RECORD_IDS
    assert all(r["status"] == "finding" for r in records)

    decisions = basic_run.store.list_review_decisions(RUN_ID)
    assert sorted(d["companyRecordId"] for d in decisions) == sorted(EXPECTED_RECORD_IDS)
    assert all(d["reviewer"] == "market-manager/rules-v1+test-model" for d in decisions)
    assert all(d["reason"].strip() for d in decisions)

    # The three fully cited companies are the only includes.
    included = {basic_run.record_name(d["companyRecordId"]) for d in decisions if d["disposition"] == "include"}
    assert included == {"Alpha Ledger", "Beta Billing", "Epsilon Pay"}


def test_position_baseline_is_created_from_the_decisions(basic_run: CompletedRun):
    baseline = basic_run.store.get_position_baseline(RUN_ID)
    assert baseline is not None
    run = basic_run.store.get_run(RUN_ID)
    assert baseline["candidateId"] == CANDIDATE_ID
    assert baseline["position"] == run["position"]
    assert baseline["constraintsInForce"] == run["constraintsInForce"]
    decisions = {d["companyRecordId"]: d["disposition"] for d in basic_run.store.list_review_decisions(RUN_ID)}
    assert {c["companyRecordId"]: c["disposition"] for c in baseline["companies"]} == decisions


def test_report_has_sections_one_to_eight(basic_run: CompletedRun):
    report_path = basic_run.harness.reports_dir / f"{RUN_ID}.md"
    assert report_path.exists()
    markdown = report_path.read_text(encoding="utf-8")

    headings = _headings(markdown)
    assert headings[0] == (1, f"Invoice Alpha: first position report ({RUN_ID})")
    wanted = [
        "Run summary",
        "First position",
        "Constraints in force",
        "Hypothesis check",
        "Included companies",
        "Needs verification",
        "Excluded",
    ]
    texts = [text.casefold() for _, text in headings]
    position = 0
    for title in wanted:
        found = next((i for i in range(position, len(texts)) if texts[i].startswith(title.casefold())), None)
        assert found is not None, f"heading {title!r} missing or out of order in {[t for _, t in headings]}"
        position = found + 1

    included = _section(markdown, "Included companies")
    needs = _section(markdown, "Needs verification")
    excluded = _section(markdown, "Excluded")
    for name in ("Alpha Ledger", "Beta Billing", "Epsilon Pay"):
        assert name in included
    for name in ("Gamma Ops", "Zeta Holdings LLC"):
        assert name in needs
    for name in ("Delta None", "Sigma Scale", "Theta Works"):
        assert name in excluded

    meta = basic_run.store.get_demo_report(RUN_ID)
    assert meta is not None
    assert Path(meta["path"]).resolve() == report_path.resolve()
    assert meta["sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()


def test_run_command_executes_every_step(harness_for):
    harness = harness_for("basic")
    assert harness.cli("intake", "--program", "invoice_alpha").code == 0
    assert harness.cli("candidates", "--program", "invoice_alpha_genesis").code == 0
    result = harness.cli("run", "--candidate", CANDIDATE_ID, "--file", str(POSITION_FILE))
    assert result.code == 0, result.stderr
    assert result.json["runId"] == RUN_ID
    assert result.json["status"] == "reported"
    assert harness.store.get_position_baseline(RUN_ID) is not None
    assert (harness.reports_dir / f"{RUN_ID}.md").exists()


def test_review_cannot_run_twice(basic_run: CompletedRun):
    before = basic_run.store.list_review_decisions(RUN_ID)
    again = basic_run.harness.cli("review", "--run", RUN_ID)
    assert again.code == 2
    assert again.stderr.startswith("error:")
    assert basic_run.store.list_review_decisions(RUN_ID) == before


def test_a_failing_step_stops_the_run_and_marks_it_failed(harness_for):
    """T044: with no recordings, `run` stops at discover (exit 3) and records which step failed."""
    harness = harness_for("no_such_scenario")
    assert harness.cli("intake", "--program", "invoice_alpha").code == 0
    assert harness.cli("candidates", "--program", "invoice_alpha_genesis").code == 0
    result = harness.cli("run", "--candidate", CANDIDATE_ID, "--file", str(POSITION_FILE))
    assert result.code == 3
    assert result.json["error"]["code"] == 3
    run = harness.store.get_run(RUN_ID)
    assert run["status"] == "failed"
    assert run["errorStep"] == "discover"
    assert "ReplayMissingError" in run["errorMessage"]
    assert harness.store.list_company_records(RUN_ID) == []
