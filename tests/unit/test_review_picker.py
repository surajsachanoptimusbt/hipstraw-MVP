"""Market Manager Review: the playbook quick picker, by rules only."""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market import review as rv
from hipstraw_mm.market.playbook import load_playbook

PB = load_playbook()
DESK_PERFORMED = {"M09", "A10", "M14", "A15", "M06", "A03", "A05", "M17", "M24", "A01"}


def axes(**states: str) -> list[dict[str, Any]]:
    base = {"MP1": "Hypothesis", "MP2": "Unknown", "MP3": "Concept", "MP4": "Untested", "MP5": "Fragile",
            "MP6": "Assumed", "MP7": "First of its kind"}
    base.update(states)
    return [{"axis": a, "state": s} for a, s in base.items()]


def desk_unit(**packet: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    pk = {"found": 4, "included": 2, "needsVerification": 1, "contradictions": [], **packet}
    path = {"pathId": "p", "assessment": [{"dimensionKey": "value_proposition"}], "researchPacket": pk}
    return path, {"packet": pk, "economics": {"valuePoolUsdLow": 2e6, "valuePoolUsdHigh": 6e6}}


class TestPlaybookCaseC1:
    """The playbook's own worked case C1 (vertical B2B SaaS, AR04 + AR10)."""

    def test_stance_strategy_play_and_line(self) -> None:
        c1 = axes(MP2="Reachable", MP6="Not modeled")
        binding = rv.binding_constraint(PB, c1)
        stance = rv.choose_stance(PB, c1, binding)
        assert binding == "MP1" and stance["stance"] == "Probe"
        assert {r["stance"] for r in stance["ruledOut"]} == {"Activate", "Expand"}
        pick = rv.choose_strategy_and_play(PB, ("MP1", "Hypothesis"), "Probe", ["AR04", "AR10"])
        assert (pick["strategy"], pick["play"]) == ("S03", "P04")
        assert rv.plan_line(PB, "P04", "Probe", set())["sequence"] == ["L03", "L05"]

    def test_the_design_partner_gambit_needs_co_create(self) -> None:
        g02 = next(g for g in rv.gambit_options(PB, "P04", "Probe") if g["id"] == "G02")
        assert not g02["fitsStance"] and g02["needsStance"] == "Co-create" and g02["authorized"] is False
        assert next(g for g in rv.gambit_options(PB, "P04", "Co-create") if g["id"] == "G02")["fitsStance"]


class TestDeskResearchReview:
    def test_full_chain(self) -> None:
        path, case = desk_unit()
        c = rv.run_review(PB, path, case, buyer_roles=3, market_types=["AR04", "AR10", "AR03"],
                          performed=DESK_PERFORMED)
        assert [a["state"] for a in c["axes"]] == ["Hypothesis", "Unknown", "Concept", "Untested", "Fragile",
                                                   "Assumed", "First of its kind"]
        assert (c["disposition"], c["attention"]) == ("TEST", "Watch")
        assert [s["status"] for s in c["line"]["steps"]] == ["done", "done", "done", "done", "to do"]
        assert c["nextStep"]["id"] == "A16" and c["nextStep"]["allowedInMode"] is True
        assert c["line"]["then"] == "L05"
        assert all(a["allowedInMode"] == (a["tier"] <= 2) for a in c["actions"])

    def test_contradictions_reframe(self) -> None:
        path, case = desk_unit(contradictions=["Acme"])
        c = rv.run_review(PB, path, case, buyer_roles=0, market_types=["AR04"], performed=set())
        assert c["axes"][0]["state"] == "Contested" and c["disposition"] == "REFRAME"

    def test_all_companies_excluded_parks(self) -> None:
        path, case = desk_unit(included=0, needsVerification=0)
        c = rv.run_review(PB, path, case, buyer_roles=0, market_types=["AR04"], performed=set())
        assert c["disposition"] == "PARK"

    def test_without_market_types_the_first_fitting_strategy_and_play_are_used(self) -> None:
        path, case = desk_unit()
        c = rv.run_review(PB, path, case, buyer_roles=0, market_types=[], performed=set())
        assert (c["strategy"], c["play"], c["line"]["current"]) == ("S02", "P02", "L02")
        assert c["nextStep"]["id"] == "A05"


class TestRules:
    def test_a_broken_axis_binds_before_the_need(self) -> None:
        assert rv.binding_constraint(PB, axes(MP5="Broken")) == "MP5"

    def test_rejected_need_stops(self) -> None:
        d = rv.disposition(PB, axes(MP1="Rejected"), "Protect", {"found": 2, "included": 1})
        assert d == {"disposition": "STOP", "attention": "Request", "reason": "MP1 is Rejected"}

    def test_performed_steps_count_only_operations_that_ran(self) -> None:
        registry = {"agents": [{"innateCapabilities": [], "skills": [
            {"operations": ["build_level"], "playbook": ["M09 Archetype Segmentation"]},
            {"operations": ["screen_economics"], "playbook": ["A10 Create comparable territory economics"]},
            {"operations": [], "playbook": ["M06 Audience Source Mapping", "Hard rule 01 A market hypothesis"]},
        ]}]}
        assert rv.performed_steps(registry, {"build_level"}) == {"M09", "M06"}
