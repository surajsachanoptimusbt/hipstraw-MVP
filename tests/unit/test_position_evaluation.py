"""Position & Evaluation rules: confidence, transition rubric, research requirements, comparison, matching."""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market import evaluation as ev
from hipstraw_mm.market.agents import load_agent_registry
from hipstraw_mm.market.position import commit_record, trajectory
from hipstraw_mm.store.memory import MemoryStore
from hipstraw_mm.viewer import api

GOOD_EVIDENCE = {"sufficiency": "sufficient", "quality": "strong", "criticalUnknowns": "resolved"}
ESTIMATE = {"valuePoolUsdLow": 1e6, "valuePoolUsdHigh": 3e6, "sensitivities": [{"factor": "x", "impact": "low"}]}


def packet(**kw: Any) -> dict[str, Any]:
    return {"found": 3, "included": 2, "needsVerification": 1, "excluded": 0, "contradictions": [], "gaps": [],
            "error": None, **kw}


class TestConfidence:
    def test_strong_evidence_with_verified_companies_is_high(self) -> None:
        assert ev.assess_confidence(GOOD_EVIDENCE, packet(), ESTIMATE)["band"] == "High"

    def test_no_verified_company_caps_low(self) -> None:
        c = ev.assess_confidence(GOOD_EVIDENCE, packet(included=0), ESTIMATE)
        assert c["band"] == "Low" and "no verified (included) company yet" in c["limitingFactors"]

    def test_open_unknowns_and_fragile_economics_cap_medium(self) -> None:
        fragile = {**ESTIMATE, "valuePoolUsdHigh": 9e6}
        open_unknowns = {**GOOD_EVIDENCE, "criticalUnknowns": "open"}
        assert ev.assess_confidence(open_unknowns, packet(), ESTIMATE)["band"] == "Medium"
        assert ev.assess_confidence(GOOD_EVIDENCE, packet(), fragile)["band"] == "Medium"

    def test_contradictions_cap_low(self) -> None:
        assert ev.assess_confidence(GOOD_EVIDENCE, packet(contradictions=["Acme"]), ESTIMATE)["band"] == "Low"


class TestTransitionRubric:
    def rec(self, pk: dict[str, Any], evidence: dict[str, Any] = GOOD_EVIDENCE, prior: Any = None) -> str:
        conf = ev.assess_confidence(evidence, pk, ESTIMATE)
        return str(ev.recommend({"pathId": "p", "nodeLabels": ["a"]}, pk, evidence, conf, prior)["recommendation"])

    def test_new_supported_candidate_recommends_transition(self) -> None:
        assert self.rec(packet()) == "Recommend Transition"

    def test_prior_pursue_still_supported_is_maintain(self) -> None:
        assert self.rec(packet(), prior={"status": "Pursue", "confidence": "High"}) == "Maintain"
        assert self.rec(packet(), prior={"status": "Pursue", "confidence": "Low"}) == "Strengthen"

    def test_failed_or_empty_research_is_investigate_never_retire(self) -> None:
        assert self.rec(packet(error="discover: boom")) == "Investigate Further"
        assert self.rec(packet(found=0, included=0, needsVerification=0)) == "Investigate Further"

    def test_all_excluded_retires_and_weakens_an_old_pursue(self) -> None:
        excluded = packet(included=0, needsVerification=0, excluded=3)
        assert self.rec(excluded) == "Recommend Retirement"
        assert self.rec(excluded, prior={"status": "Pursue", "confidence": "High"}) == "Weaken"

    def test_contradiction_or_thin_evidence_validates(self) -> None:
        assert self.rec(packet(contradictions=["Acme"])) == "Validate"
        assert self.rec(packet(), evidence={**GOOD_EVIDENCE, "sufficiency": "partial"}) == "Validate"

    def test_every_recommendation_maps_to_a_manager_decision(self) -> None:
        assert set(ev.RECOMMENDATION_SUPPORTS.values()) == {"pursue", "needs more evidence", "drop"}


class TestResearchRequirements:
    def test_gaps_and_empty_paths_issue_requirements(self) -> None:
        path = {"pathId": "p", "nodeLabels": ["seg", "arch"]}
        conf = {"band": "Low", "limitingFactors": []}
        empty = ev.research_requirements(path, packet(found=0, included=0), conf, None)
        assert empty[0]["priority"] == "High" and "constraint" in empty[0]["whyMaterial"]
        gaps = ev.research_requirements(path, packet(gaps=[{"field": "hq", "companies": 2}]), conf, None)
        assert any(r["evidenceGap"] == "hq unknown for 2 companies" for r in gaps)
        assert all({"decisionBlocked", "requiredEvidence", "stopCondition", "returnFormat"} <= set(r) for r in gaps)


class TestComparison:
    def case(self, pid: str, mid: float, sufficiency: str, band: str) -> dict[str, Any]:
        return {"pathId": pid, "labels": [pid], "searchScore": 0.8,
                "economics": {"valuePoolUsdLow": mid, "valuePoolUsdHigh": mid},
                "evidence": {"sufficiency": sufficiency}, "confidence": {"band": band},
                "packet": {"included": 1, "gaps": []}, "recommendation": {"recommendation": "Validate"}}

    def test_trade_off_is_kept_without_a_forced_winner(self) -> None:
        cmp_ = ev.compare_candidates([self.case("rich", 9e6, "partial", "Low"),
                                      self.case("solid", 2e6, "sufficient", "Medium")])
        assert cmp_["leaders"]["economics"] == "rich" and cmp_["leaders"]["evidence"] == "solid"
        assert cmp_["tradeOffs"] and cmp_["dominant"] is None

    def test_near_tie_is_flagged(self) -> None:
        cmp_ = ev.compare_candidates([self.case("a", 5.0e6, "partial", "Medium"),
                                      self.case("b", 4.6e6, "partial", "Medium")])
        assert cmp_["nearTies"] and cmp_["dominant"] is None


class TestCanonicalPosition:
    def test_match_prior_and_versioning(self) -> None:
        prior = {"positionKey": "prog__mm_x", "version": 1, "labels": ["Atlanta SaaS", "Mid-market"],
                 "status": "Needs more evidence", "confidence": "Low"}
        assert ev.match_prior(["Atlanta SaaS", "mid market"], [prior]) is not None
        assert ev.match_prior(["Denver mining"], [prior]) is None
        run = {"programId": "prog", "marketRunId": "mrun_2"}
        path = {"pathId": "p", "nodeLabels": ["Atlanta SaaS", "Mid-market"], "researchPacket": {}}
        case = {"caseId": "c", "confidence": {"band": "Medium", "limitingFactors": []},
                "recommendation": {"recommendation": "Validate", "supportsDecision": "needs more evidence",
                                   "rationale": "r"}}
        rec = commit_record(run, path, case, {"decision": "pursue", "reason": "r", "ruleFired": "x"}, prior, "now")
        assert rec["positionKey"] == "prog__mm_x" and rec["version"] == 2
        assert rec["trajectory"] == "up"
        assert rec["recommendationAccepted"] is False and "not accepted" in rec["reviewNote"]
        assert rec["evidenceLineage"]["priorVersion"] == "prog__mm_x__v1"

    def test_trajectory(self) -> None:
        assert trajectory(None, "Pursue", "High") == "new"
        assert trajectory({"status": "Pursue", "confidence": "High"}, "Drop", "Low") == "down"


class TestAgentRegistry:
    def test_registry_loads_and_every_layer_has_an_agent(self) -> None:
        reg = load_agent_registry()
        assert {a.layer for a in reg.agents} == {
            "market_manager", "market_development_controller", "search_research", "position_evaluation", "workers"}
        assert reg.operation_owner("evaluate_candidate") == ("position_evaluation", "evaluation_process")
        assert reg.operation_owner("commit_position") == ("market_manager", "market_review")

    def test_a_skill_with_prompts_is_never_labelled_a_rule(self) -> None:
        for agent in load_agent_registry().agents:
            for sk in agent.skills:
                assert not (sk.promptVersions and sk.kind == "rule"), f"{agent.id}.{sk.id} calls the model"


class TestPlainView:
    def test_titled_agents_are_shown_in_plain_language(self) -> None:
        view = api.plain_view(load_agent_registry().model_dump())
        ids = [a["id"] for a in view["agents"]]
        assert "workers" not in ids and "market_manager" in ids
        assert all(a["role"] and a["does"] for a in view["agents"])
        assert sum(view["counts"].values()) == sum(len(a["does"]) for a in view["agents"])
        mm = next(a for a in view["agents"] if a["id"] == "market_manager")
        assert {d["how"] for d in mm["does"]} == {"built_in", "rule", "mixed"}
        research = next(a for a in view["agents"] if a["id"] == "search_research")
        assert "AI model" in research["uses"] and "Web search" in research["uses"]
        assert view["glossary"] and all(g["proposed"] for g in view["glossary"])

    def test_runs_without_plain_fields_borrow_the_current_wording(self) -> None:
        old = load_agent_registry().model_dump()
        for a in old["agents"]:
            a.pop("title")
        store = MemoryStore()
        store.upsert_market_run({"marketRunId": "mrun_old", "programId": "p", "status": "reported",
                                 "agentRegistry": old})
        shaped = api.shape_agents(store, "mrun_old")
        assert shaped is not None and shaped["simple"]["agents"]
