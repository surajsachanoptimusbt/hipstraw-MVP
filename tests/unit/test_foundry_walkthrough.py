"""Demand validation walkthrough (Nov 5 meeting): a market thesis in, a demand validation program out. The Lines
(strategies) that fit each hypothesis are chosen by their conditions, every Line considered and every Move picked
is logged with why, the Moves carry what they do for this market, how, and what they record and must reach, each
of the six demand dimensions is mapped to the Lines, Moves and evidence that test it, and the scorecard sets each
indicator against its target."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from hipstraw_mm import cli
from hipstraw_mm.errors import UsageError
from hipstraw_mm.foundry.demand import load_demand_rubric
from hipstraw_mm.foundry.program_report import render_program_html, render_program_markdown
from hipstraw_mm.foundry.walkthrough import Thesis, load_thesis, run_walkthrough

RUBRIC = load_demand_rubric(Path("config"))
ZIMPLII = Path("input/demand/theses/zimplii_technical_assurance.yaml")
HIPSTRAW = Path("input/demand/theses/hipstraw_shadow_launch.yaml")


def _thesis(hypothesis: dict[str, Any], **extra: Any) -> Thesis:
    return Thesis.model_validate({
        "thesis": "t", "product": "P", "statement": "s", "market": "m", "asOf": "2026-11-05", "buyer": "b2b",
        "motion": "sales_led",
        "hypotheses": [{"id": "H1", "name": "h", "demand": "d",
                        "segment": {"name": "seg", "profile": "small_business"},
                        "offering": {"name": "off"}, **hypothesis}], **extra,
    })


def _program(thesis: Thesis) -> list[str]:
    return [pl.id for pl in run_walkthrough(thesis, RUBRIC).hypotheses[0].program]


def test_the_zimplii_thesis_gets_lines_that_fit_each_hypothesis() -> None:
    w = run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC)
    programs = {p.id: [pl.id for pl in p.program] for p in w.hypotheses}
    assert programs == {"H1": ["LD1", "LD2", "LD4", "LD5"],  # sales-led, recurring
                        "H2": ["LD1", "LD3", "LD5"],  # self-serve, bought once
                        "H3": ["LD1", "LD2", "LD4", "LD5"]}
    h2 = next(p for p in w.hypotheses if p.id == "H2")
    ld2 = next(c for c in h2.lines if c.id == "LD2")
    assert not ld2.fits and "motion is self_serve, needs sales_led" in ld2.reasons
    assert all(p.assessment.decision == "abstain" for p in w.hypotheses)  # desk evidence only


def test_moves_are_filled_in_for_the_market_and_done_moves_are_marked() -> None:
    w = run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC)
    h1 = w.hypotheses[0]
    moves = h1.moves()
    assert all("{" not in text for m in moves for text in (m.does, m.needs, *m.how))
    dv09 = next(m for m in moves if m.id == "DV09")
    assert "150 named organisations" in dv09.does and "a delayed milestone" in dv09.does
    assert "approves the provider's milestones" in dv09.does  # who decides and pays, from the thesis
    assert dv09.how[0].startswith("Start from the existing Metro Atlanta market plan")
    assert dv09.tests == ["DE03", "DE10"] and dv09.dimensions == ["Buyer demand", "Reachable demand"]
    assert [(k.type, k.level, k.demand) for k in dv09.records] == [("trigger_observed", "L1", False)]
    assert dv09.passWhen == ["Accounts mapped with a live buying trigger: 0 of 150"] and dv09.status == "next"
    dv01 = next(m for m in moves if m.id == "DV01")
    assert dv01.done and dv01.status == "done"  # the discovery output's desk research
    assert h1.firstAction.startswith("DV09")
    assert all(m.needsCharter == (m.effect == "E3") for m in moves)
    assert next(pl for pl in h1.program if pl.id == "LD2").why == ["buyer is b2b, as needed",
                                                                   "motion is sales_led, as needed"]


def test_each_demand_dimension_is_mapped_to_its_lines_moves_and_evidence() -> None:
    w = run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC)
    h1, h2 = (next(p for p in w.hypotheses if p.id == x) for x in ("H1", "H2"))
    dims = {d.name: d for d in h1.dimensions}
    assert list(dims) == ["Problem demand", "Buyer demand", "Solution demand", "Payment demand",
                          "Recurring demand", "Reachable demand"]
    payment = dims["Payment demand"]
    assert payment.lines == ["LD2 Paid pilot", "LD5 Economics and reach"]
    assert [m.split()[0] for m in payment.moves] == ["DV10", "DV06", "DV04", "DV12"]
    assert {k.type for k in payment.evidence} >= {"pilot_signed", "paid_order"}
    assert [i.id for i in payment.indicators] == ["SC07", "SC08"]
    assert [q.id for q in dims["Buyer demand"].questions] == ["DE10"]
    assert dims["Recurring demand"].lines == ["LD4 Recurring conversion"]
    recurring = next(d for d in h2.dimensions if d.name == "Recurring demand")  # bought once
    assert recurring.lines == [] and recurring.questions[0].state == "not_applicable"


def test_the_log_shows_every_line_considered_and_every_move_picked() -> None:
    w = run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC)
    lines_step = next(s for s in w.steps if s.title.startswith("Choose the Lines"))
    considered = [x for x in lines_step.lines if x.depth == 1]
    assert len(considered) == len(w.hypotheses) * len(RUBRIC.lines)
    assert {x.tag for x in considered} == {"chosen", "not chosen"}
    assert "motion is self_serve, needs sales_led" in [x.text for x in lines_step.lines if x.depth == 2]
    moves_step = next(s for s in w.steps if s.title.startswith("Pick the Moves"))
    picked = [x for x in moves_step.lines if x.depth == 2]
    assert len(picked) == sum(len(p.moves()) for p in w.hypotheses)
    assert picked[1].text.startswith("Stage 1. DV09 Map reachable buyers") and picked[1].tag == "next"
    assert "Pass when Accounts mapped with a live buying trigger: 0 of 150" in [x.text for x in moves_step.lines]
    assert w.lines[0].id == "LD0" and w.lines[0].usedBy == []
    assert next(x for x in w.moves if x.id == "DV05").usedBy == ["H2"]


def test_a_rejected_problem_ends_the_program_after_review() -> None:
    contra = [{"id": "N", "type": "problem_interview", "summary": "no", "source": "s", "segment": True,
               "count": 7, "contradicts": ["DE01"]}]
    gates = {"truthAndConsent": True, "rubricRecordedBefore": True}
    w = run_walkthrough(_thesis({"evidence": contra, "gates": gates}), RUBRIC)
    plan = w.hypotheses[0]
    assert [pl.id for pl in plan.program] == ["LD0"]
    assert plan.assessment.decision == "disproved" and plan.checkpoint == "Stop or reframe"
    assert all("not reached" in c.reasons[0] for c in plan.lines if c.phase > 1)


def test_a_confirmed_problem_skips_the_problem_line() -> None:
    confirmed = [{"id": "Y", "type": "problem_interview", "summary": "yes", "source": "s", "segment": True,
                  "count": 10, "supports": ["DE01"]}]
    assert _program(_thesis({"evidence": confirmed, "gates": {"truthAndConsent": True,
                                                              "rubricRecordedBefore": True}})) == ["LD2", "LD5"]


def test_hypothesis_targets_and_shared_case_evidence() -> None:
    w = run_walkthrough(load_thesis(HIPSTRAW, RUBRIC), RUBRIC)
    h1 = w.hypotheses[0]
    assert sum(r.items for r in h1.assessment.ladder) == 27  # the desk scan's evidence, shared from the case file
    assert next(m for pl in h1.program for s in pl.stages for m in s if m.id == "DV01").done
    tight = _thesis({"targets": {"interviews": 18}, "targetsWhy": "the discovery plan's 18"})
    plan = run_walkthrough(tight, RUBRIC).hypotheses[0]
    assert next(i for i in plan.scorecard if i.id == "SC02").target == 18


def test_the_log_records_every_step_in_order() -> None:
    w = run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC)
    assert [s.title for s in w.steps][:5] == ["Read the market thesis", "Set what demand validation must show",
                                              "Frame one demand question per hypothesis",
                                              "Place the evidence so far on the ladder",
                                              "Judge each hypothesis on the six demand dimensions (DV07)"]
    assert w.steps[-1].title == "List what needs a decision"
    assert any("price floor" in d for d in w.openDecisions)
    assert all(s.summary for s in w.steps)
    assert run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC) == w  # same thesis, same program


def test_a_bad_thesis_is_refused(tmp_path: Path) -> None:
    raw = yaml.safe_load(ZIMPLII.read_text(encoding="utf-8"))
    raw["hypotheses"][1]["id"] = "H1"
    raw["hypotheses"][0]["segment"]["profile"] = "galactic"
    path = tmp_path / "t.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(UsageError, match="duplicate hypothesis H1.*galactic|galactic.*duplicate"):
        load_thesis(path, RUBRIC)


def test_the_page_and_markdown_show_log_lines_and_scorecard() -> None:
    w = run_walkthrough(load_thesis(ZIMPLII, RUBRIC), RUBRIC)
    page = render_program_html(w)
    for text in ("Walkthrough log", "Demand dimensions: the Lines, Moves and evidence", "Lines considered",
                  "Buyer demand", "Pass when", "Demand scorecard", "LD2</span> Paid pilot", "Repertoire",
                  "Decisions needed"):
        assert text in page
    assert "<script" not in page
    assert page.count("<details") == page.count("</details>") and page.count("<ul") == page.count("</ul>")
    markdown = render_program_markdown(w)
    for text in ("### Demand dimensions: Lines, Moves and evidence", "### Lines considered", "### Scorecard",
                 "- Pass when: Accounts mapped with a live buying trigger: 0 of 150", "### Moves (methods)"):
        assert text in markdown


def test_cli_program_writes_page_markdown_and_trace(tmp_path: Path) -> None:
    out = io.StringIO()
    code = cli.main(["demand", "program", "--thesis", str(ZIMPLII), "--out-dir", str(tmp_path), "--json"],
                    stdout=out, stderr=io.StringIO())
    assert code == 0
    data = json.loads(out.getvalue())
    assert data["command"] == "demand program" and len(data["hypotheses"]) == 3
    for key in ("page", "markdown", "trace"):
        assert Path(data[key]).exists()
