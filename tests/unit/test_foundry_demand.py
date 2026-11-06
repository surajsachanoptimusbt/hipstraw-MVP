"""Demand evidence rubric (Blueprint v0.1 section 07; Nov 4 meeting: validate that a market demands a product from
several kinds of evidence, never one score). Each dimension is judged on its own, gates block whatever the
dimensions say, simulations and clicks never count as demand, and the rubric may abstain."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, NoReturn

import pytest
import yaml

from hipstraw_mm import cli
from hipstraw_mm.errors import ConfigError, UsageError
from hipstraw_mm.foundry.demand import (
    DemandCase,
    DemandRubric,
    assess,
    load_case,
    load_demand_rubric,
    raw_demand_rubric,
    render_markdown,
    run_lab,
    scorecard,
)

CONFIG = Path("config")
LAB = CONFIG / "foundry" / "lab" / "demand_evidence"
RUBRIC = load_demand_rubric(CONFIG)
HIPSTRAW_CASE = Path("input/demand/hipstraw_small_business_shadow_launch.yaml")


def _case(evidence: list[dict[str, Any]], gates: dict[str, Any] | None = None, **extra: Any) -> DemandCase:
    return DemandCase.model_validate({
        "case": "t", "question": "Do small clinics want it?", "asOf": "2026-11-04",
        "offering": {"name": "Thing", "priceFloor": {"amount": 100}},
        "segment": {"name": "US clinics", "profile": "small_business"},
        "gates": gates if gates is not None else {"truthAndConsent": True, "supplyFeasible": True,
                                                   "rubricRecordedBefore": True},
        "evidence": evidence, **extra,
    })


def _item(i: str, type_: str, count: int = 1, **kw: Any) -> dict[str, Any]:
    return {"id": i, "type": type_, "summary": i, "source": kw.pop("source", f"src-{i}"), "segment": True,
            "count": count, **kw}


def _states(case: DemandCase) -> dict[str, str]:
    return {d.id: d.state for d in assess(case, RUBRIC).dimensions}


def test_the_shipped_rubric_loads_lints_and_is_a_candidate() -> None:
    assert RUBRIC.qualification == "candidate"
    assert [d.id for d in RUBRIC.dimensions] == [f"DE{n:02d}" for n in range(1, 11)]
    assert [g.name for g in RUBRIC.demandDimensions] == ["Problem demand", "Buyer demand", "Solution demand",
                                                         "Payment demand", "Recurring demand", "Reachable demand"]
    assert RUBRIC.repertoireVersion and {line.id for line in RUBRIC.lines} >= {"LD1", "LD2", "LD3", "LD4", "LD5"}
    assert RUBRIC.decisions[-1].id == "not_validated"


def test_lint_rejects_unknown_references(tmp_path: Path) -> None:
    raw = raw_demand_rubric(CONFIG)
    raw["evidenceTypes"]["rumour"] = "L9"
    raw["dimensions"][0]["whenMet"][0]["atLeast"] = "nosuchkey"
    raw["dimensions"][1]["gatheredBy"] = ["DV99"]
    raw["decisions"].append({"id": "late", "text": "x", "allMet": ["DE01"]})
    raw["lines"][0]["useWhen"] = {"weather": ["sunny"]}
    raw["scorecard"][0]["target"] = "nosuchtarget"
    raw["moves"][0]["records"] = ["gossip"]
    raw["demandDimensions"][0]["questions"].append("DE10")  # DE10 is in Buyer demand already
    raw["demandDimensions"][1]["questions"].append("DE42")
    with pytest.raises(ValueError) as err:
        DemandRubric.model_validate(raw)
    text = str(err.value)
    for expected in ("'L9'", "'nosuchkey'", "'DV99'", "last decision must have no conditions", "'weather'",
                     "'nosuchtarget'", "'gossip'", "DE10: in more than one demand dimension", "'DE42'"):
        assert expected in text
    raw["demandDimensions"][0]["questions"].remove("DE10")
    raw["demandDimensions"][1]["questions"].remove("DE42")
    (tmp_path / "foundry").mkdir()
    repertoire = {"version": raw["repertoireVersion"], "moves": raw.pop("moves"), "lines": raw.pop("lines")}
    raw.pop("repertoireVersion")
    raw.pop("phases")
    (tmp_path / "foundry" / "demand_evidence.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (tmp_path / "foundry" / "demand_repertoire.yaml").write_text(yaml.safe_dump(repertoire), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_demand_rubric(tmp_path)


def test_a_case_with_unknown_types_or_dimensions_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    raw = _case([_item("E1", "signup")]).model_dump(mode="json")
    raw["evidence"][0]["type"] = "gut_feeling"
    raw["evidence"][0]["supports"] = ["DE42"]
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(UsageError, match="gut_feeling.*DE42"):
        load_case(path, RUBRIC)


def test_simulations_never_count_as_demand() -> None:
    a = assess(_case([_item("S", "simulation", 500, supports=["DE01", "DE05", "DE06"])], gates={}), RUBRIC)
    assert a.decision == "abstain"
    assert {d.state for d in a.dimensions} == {"unknown", "not_applicable"}
    assert any("never count as demand" in w for w in a.warnings)


def test_clicks_are_attention_not_intent() -> None:
    case = _case([_item("C", "ad_click", 2000, supports=["DE05"]), _item("V", "page_visit", 900)])
    a = assess(case, RUBRIC)
    state = {d.id: d.state for d in a.dimensions}
    assert state["DE05"] == "not_met"  # 2,900 of the segment saw it, nobody acted
    assert a.decision == "not_validated"
    assert any(w.startswith("Attention is not intent") for w in a.warnings)


def test_a_gate_blocks_whatever_the_dimensions_say() -> None:
    lab = load_case(LAB / "04_validated.yaml", RUBRIC)
    assert assess(lab, RUBRIC).decision == "validated"
    unconfirmed = lab.model_copy(update={"gates": {"supplyFeasible": True, "rubricRecordedBefore": True}})
    a = assess(unconfirmed, RUBRIC)
    assert a.decision == "blocked" and a.nextMoves == []
    assert {g.id: g.state for g in a.gates}["GX1"] == "not_confirmed"
    refused = lab.model_copy(update={"gates": {**lab.gates, "truthAndConsent": False}})
    assert {g.id: g.state for g in assess(refused, RUBRIC).gates}["GX1"] == "failed"


def test_gates_apply_only_once_the_evidence_reaches_their_rung() -> None:
    a = assess(_case([_item("D", "desk_research", supports=["DE01"])], gates={}), RUBRIC)
    assert {g.state for g in a.gates} == {"not_applicable"}
    assert a.decision == "abstain"


def test_evidence_on_both_sides_is_contested_not_averaged() -> None:
    case = _case([_item("Y", "problem_interview", 7, supports=["DE01"]),
                  _item("N", "problem_interview", 6, contradicts=["DE01"])])
    a = assess(case, RUBRIC)
    de01 = a.dimensions[0]
    assert de01.state == "partly" and de01.contested and (de01.support, de01.contra) == (7, 6)
    assert any("DE01 is contested" in w for w in a.warnings)


def test_independence_reads_sources_channels_and_share() -> None:
    own = [_item("F", "signup", 30, independent=False, channel="linkedin", supports=["DE05"])]
    de08 = next(d for d in assess(_case(own), RUBRIC).dimensions if d.id == "DE08")
    assert de08.state == "not_met" and (de08.support, de08.contra) == (0, 30) and de08.evidence == ["F"]
    varied = [_item("A", "signup", 10, channel="email"), _item("B", "signup", 10, channel="search"),
              _item("C", "problem_interview", 10, channel="interview")]
    assert _states(_case(varied))["DE08"] == "met"
    one_channel = [_item(x, "signup", 10, channel="email") for x in "ABC"]
    assert _states(_case(one_channel))["DE08"] == "partly"


def test_price_is_judged_against_the_floor() -> None:
    below = [_item("P", "pre_order", 5, price=40)]
    assert _states(_case(below))["DE07"] == "not_met"
    at = [_item("P", "deposit", 3, price=100)]
    assert _states(_case(at))["DE07"] == "met"
    stated = [_item("S", "price_test_response", 4, price=120, supports=["DE07"])]
    assert _states(_case(stated))["DE07"] == "partly"
    no_floor = _case(at).model_copy(update={"offering": _case(at).offering.model_copy(update={"priceFloor": None})})
    assert _states(no_floor)["DE07"] == "unknown"


def test_next_moves_follow_the_unmet_dimensions_in_line_order() -> None:
    a = assess(load_case(LAB / "09_promising.yaml", RUBRIC), RUBRIC)
    assert a.decision == "promising"
    ids = [m.id for m in a.nextMoves]
    assert ids[-1] == "DV07" and ids.index("DV05") < ids.index("DV06")
    assert next(m for m in a.nextMoves if m.id == "DV05").forDimensions == ["DE06", "DE07"]


def test_there_is_no_score_and_the_assessment_is_deterministic() -> None:
    case = load_case(LAB / "04_validated.yaml", RUBRIC)
    first, second = assess(case, RUBRIC), assess(case, RUBRIC)
    assert first == second
    keys = json.dumps(first.model_dump(mode="json")).lower()
    assert "score" not in keys and "total" not in keys


def test_the_report_carries_scope_dimensions_gates_and_missing() -> None:
    case = load_case(LAB / "09_promising.yaml", RUBRIC)
    text = render_markdown(assess(case, RUBRIC), case, RUBRIC)
    assert "It is not a forecast of sales" in text
    for heading in ("## Dimensions", "## Gates", "## Evidence ladder", "## What is missing", "## Next Moves"):
        assert heading in text
    assert "| DE06 | Concrete commitment | unknown |" in text


def test_every_lab_case_agrees_with_its_expected_result() -> None:
    results = run_lab(LAB, RUBRIC)
    assert len(results) >= 9
    assert [r for r in results if not r.agrees] == []


def test_the_hipstraw_case_is_well_formed() -> None:
    case = load_case(HIPSTRAW_CASE, RUBRIC)
    a = assess(case, RUBRIC)
    assert case.segment.profile == "small_business"
    assert a.decision in {r.id for r in RUBRIC.decisions}
    assert a.decision == "abstain"  # desk research alone says the problem may exist, not that the segment acts
    assert {d.id: d.state for d in a.dimensions}["DE01"] == "partly"
    assert [m.id for m in a.nextMoves][0] == "DV02"  # the desk scan (DV01) has run; interviews come next


def test_cli_assess_writes_the_report_without_the_market_context(tmp_path: Path) -> None:
    def refuse(_config: object) -> NoReturn:
        raise AssertionError("demand commands must not build the market context")

    out = io.StringIO()
    report = tmp_path / "r.md"
    code = cli.main(["demand", "assess", "--case", str(LAB / "02_clicks_only.yaml"), "--out", str(report), "--json"],
                    context_factory=refuse, stdout=out, stderr=io.StringIO())
    assert code == 0
    data = json.loads(out.getvalue())
    assert data["command"] == "demand assess" and data["status"] == "not_validated"
    assert report.read_text(encoding="utf-8").startswith("# Demand evidence:")
    out = io.StringIO()
    assert cli.main(["demand", "lab"], context_factory=refuse, stdout=out, stderr=io.StringIO()) == 0
    assert "lab cases agree" in out.getvalue()


def test_recurring_demand_applies_only_to_offerings_bought_again() -> None:
    once = _case([_item("P", "paid_order", 3, price=100)])
    a = assess(once, RUBRIC)
    de09 = next(d for d in a.dimensions if d.id == "DE09")
    assert de09.state == "not_applicable" and de09.missing is None
    assert "DV11" not in [m.id for m in a.nextMoves]
    recurring = once.model_copy(update={"offering": once.offering.model_copy(update={"recurring": True})})
    assert _states(recurring)["DE09"] == "unknown"
    tagged = recurring.model_copy(update={"evidence": [
        *recurring.evidence, *_case([_item("R", "renewal", 2, supports=["DE09"])]).evidence]})
    assert _states(tagged)["DE09"] == "met"


def test_a_validated_one_time_offer_is_not_held_back_by_recurring_demand() -> None:
    assert assess(load_case(LAB / "04_validated.yaml", RUBRIC), RUBRIC).decision == "validated"


def test_case_targets_replace_the_profile_thresholds() -> None:
    interviews = [_item("I", "problem_interview", 8, supports=["DE01"])]
    assert _states(_case(interviews))["DE01"] == "partly"  # 8 of the profile's 10 interviews
    assert _states(_case(interviews, targets={"interviews": 8}))["DE01"] == "met"
    with pytest.raises(UsageError, match="nosuchkey"):
        assess(_case(interviews, targets={"nosuchkey": 1}), RUBRIC)


def test_the_scorecard_counts_evidence_against_targets_and_never_sums() -> None:
    case = _case([_item("T", "trigger_observed", 40), _item("I", "problem_interview", 7, supports=["DE01"]),
                  _item("S", "signup", 12, channel="email", supports=["DE05"]),
                  _item("L", "outreach_reply", 9, channel="linkedin", supports=["DE05"])])
    cards = {i.id: i for i in scorecard(case, RUBRIC)}
    assert (cards["SC01"].current, cards["SC01"].target) == (40, 150)
    assert (cards["SC03"].current, cards["SC03"].state) == (7, "reached")
    assert cards["SC06"].current == 21 and cards["SC10"].current == 2 and cards["SC10"].state == "reached"
    assert cards["SC09"].state == "not_applicable"
