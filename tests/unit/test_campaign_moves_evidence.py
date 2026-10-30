"""T040: M01, M02 (read part), M03, M08, M09, M10, M11 and M12."""

from __future__ import annotations

from pathlib import Path

import yaml

from hipstraw_mm.campaign.intake import amend_mandate
from hipstraw_mm.campaign.models import Delta, Escalation, EvidenceRecord, EvidenceRequest, TestPlan
from hipstraw_mm.campaign.moves.common import PageRead
from tests.unit.campaign_moves_support import CONFIG, FIX, NOW, context, item, launch, run


def test_m01_adds_claims_for_assets_added_by_an_amendment(tmp_path: Path) -> None:
    store, launch_id = launch()
    assert run(context(store, launch_id, "M01")).newItems == []
    raw = yaml.safe_load((FIX / "launch_complete.yaml").read_text(encoding="utf-8"))
    raw["assets"].append({"kind": "creative", "channel": "paid_social", "text": "Hero image: invoice with red flags"})
    amended = tmp_path / "amended.yaml"
    amended.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    amend_mandate(store, CONFIG, launch_id, amended, by="Demo Sponsor", role="sponsor", now=NOW)
    out = run(context(store, launch_id, "M01"))
    assert [(i.kind, i.state, i.setBy) for i in out.newItems] == [("claim", "reported", "M01")]
    assert "Creative provided for paid_social" in out.newItems[0].text
    creative = [e for e in store.list_for_launch(EvidenceRecord, launch_id) if "Hero image" in str(e.content)]
    assert out.newItems[0].evidenceRefs == [creative[0].evidenceId]


def test_m02_reads_only_mandate_addresses_and_records_what_it_read() -> None:
    store, launch_id = launch()
    asked: list[str] = []

    def fake_fetch(url: str) -> PageRead:
        asked.append(url)
        if url.endswith("/launch"):
            return PageRead(url=url, ok=True, text="LedgerLoop flags invoice errors before payment.")
        return PageRead(url=url, ok=False, reason="network_error")

    out = run(context(store, launch_id, "M02", fetch=fake_fetch))
    assert sorted(asked) == ["https://example.com/ledgerloop", "https://example.com/ledgerloop/launch"]
    reads = [e for e in store.list_for_launch(EvidenceRecord, launch_id) if e.kind == "page_read"]
    assert [(e.source, e.sourceRef, e.verificationState) for e in reads] == [
        ("mandate_url", "https://example.com/ledgerloop/launch", "observed")]
    assert out.produced == [reads[0].evidenceId]
    unknowns = [i for i in out.newItems if i.kind == "unknown"]
    assert len(unknowns) == 1 and "https://example.com/ledgerloop" in unknowns[0].text
    assert "network_error" in unknowns[0].text and unknowns[0].key == "page:https://example.com/ledgerloop"


def test_m03_marks_complete_fresh_rows_observed_and_others_stale() -> None:
    store, launch_id = launch("launch_live.yaml")
    out = run(context(store, launch_id, "M03"))
    obs = {i.text.split(" =")[0]: i for i in out.newItems if i.kind == "observation"}
    assert obs["landing_page_sessions"].state == "observed"
    assert obs["demo_bookings"].state == "stale" and "definition" in (obs["demo_bookings"].note or "")


def test_m08_requests_evidence_for_open_core_assumptions() -> None:
    store, launch_id = launch()
    out = run(context(store, launch_id, "M08"))
    assert {(t.fromState, t.toState) for t in out.transitions} == {("open", "awaiting_evidence")}
    assert len(out.transitions) == 4
    requests = store.list_for_launch(EvidenceRequest, launch_id)
    assert len(requests) == 4 and all(r.requestedFrom == "Demo Sponsor" for r in requests)
    assert out.produced == [r.requestId for r in requests]


def test_m09_drafts_a_test_plan_for_each_proposed_hypothesis() -> None:
    store, launch_id = launch()
    position = store.head_position(launch_id)
    assert position is not None
    hyp = item("H01", "hypothesis", "proposed", "Subject line B lifts opens")
    out = run(context(store, launch_id, "M09", items=[*position.items, hyp]))
    plans = store.list_for_launch(TestPlan, launch_id)
    assert [(p.hypothesisItemId, p.state) for p in plans] == [("H01", "draft")]
    assert [(t.itemId, t.fromState, t.toState) for t in out.transitions] == [("H01", "proposed", "planned")]


def test_m09_without_hypotheses_does_nothing() -> None:
    store, launch_id = launch()
    out = run(context(store, launch_id, "M09"))
    assert out.status == "succeeded" and out.transitions == [] and store.list_for_launch(TestPlan, launch_id) == []


def test_m10_handler_never_dispatches() -> None:
    store, launch_id = launch()
    out = run(context(store, launch_id, "M10"))
    assert out.status == "blocked" and "no approved Test Plan" in (out.note or "")


def test_m11_without_a_running_hypothesis_records_nothing() -> None:
    store, launch_id = launch("launch_live.yaml")
    out = run(context(store, launch_id, "M11"))
    assert out.status == "succeeded" and store.list_for_launch(Delta, launch_id) == []


def test_m11_records_a_delta_that_is_never_causal() -> None:
    store, launch_id = launch("launch_live.yaml")
    position = store.head_position(launch_id)
    assert position is not None
    hyp = item("H01", "hypothesis", "running", "The free audit offer lifts demo bookings")
    out = run(context(store, launch_id, "M11", items=[*position.items, hyp]))
    deltas = store.list_for_launch(Delta, launch_id)
    assert len(deltas) == 1 and deltas[0].causal is False and deltas[0].observedEvidenceRefs
    assert [(t.itemId, t.toState) for t in out.transitions] == [("H01", "inconclusive")]


def test_m12_escalates_open_blockers_and_unknowns() -> None:
    store, launch_id = launch("launch_missing_landing.yaml")
    position = store.head_position(launch_id)
    assert position is not None
    blocker = item("B01", "blocker", "open", "Landing page address given: not met", area="readiness")
    out = run(context(store, launch_id, "M12", items=[*position.items, blocker]))
    escalations = store.list_for_launch(Escalation, launch_id)
    assert len(escalations) == 1 and set(escalations[0].itemRefs) == {"B01", "U01"}
    assert escalations[0].to == "Demo Sponsor" and out.produced == [escalations[0].escalationId]
