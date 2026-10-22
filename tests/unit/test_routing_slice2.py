"""Slice 2 of the task router: the rules route, links and buyer roles on open-weight first with their
validators, and every other main-run model task through the router on the frontier route."""

from __future__ import annotations

from typing import Any

import pytest

from hipstraw_mm import prompts
from hipstraw_mm.market.buyers import buyer_role_checks, no_passing_evidence_rule
from hipstraw_mm.market.links import link_checks
from hipstraw_mm.market.router import (
    RoutingConfig,
    Rule,
    TaskRouter,
    decide_route,
    load_routing,
    routing_override,
)
from hipstraw_mm.market.schemas import BuyerRole, BuyerRoles, LinkEntry, LinkVerification
from hipstraw_mm.market.validation_rubric import load_validation_rubric
from tests.unit.test_task_router import Ctx, FakeTier, _config, tracer_store  # noqa: F401

CHUNK = [
    {"fromNodeId": "n1", "toNodeId": "n2", "fromLabel": "Mid-market SaaS", "toLabel": "Finance team"},
    {"fromNodeId": "n1", "toNodeId": "n3", "fromLabel": "Mid-market SaaS", "toLabel": "Procurement"},
]


def _links(*pairs: tuple[str, str], rationale: str = "the segment has this team") -> LinkVerification:
    return LinkVerification(links=[LinkEntry(fromNodeId=a, toNodeId=b, rationale=rationale, linkConfidence=0.8)
                                   for a, b in pairs])


def _ids(checks: list[Any], failed_only: bool = False) -> set[str]:
    return {c.name for c in checks if not failed_only or not c.passed}


# --------------------------------------------------------------------------------------------------
# configuration and rubric
# --------------------------------------------------------------------------------------------------


def test_every_main_run_model_task_is_wired() -> None:
    cfg = load_routing()
    wired = {k for k, t in cfg.tasks.items() if t.wired}
    assert wired >= {
        prompts.VICHARA, prompts.VICHARA_COVERAGE, prompts.VICHARA_PROPOSE, prompts.GRAPH_LEVEL,
        prompts.LINK_VERIFICATION, prompts.BEAM_SCORING, prompts.PATH_ASSESSMENT, prompts.BUYER_ROLES,
        prompts.ECONOMIC_ASSESSMENT,
    }
    assert cfg.tasks[prompts.LINK_VERIFICATION].class_ == "simple"
    assert cfg.tasks[prompts.BUYER_ROLES].rules == ["no_passing_evidence"]
    assert cfg.openWeight.enabled is False


def test_rubric_covers_every_open_weight_task_and_rule() -> None:
    rubric = load_validation_rubric()
    cfg = load_routing()
    simple = {k for k, t in cfg.tasks.items() if t.wired and t.class_ == "simple"}
    assert set(rubric.tasks) == simple
    defined = {c.id for c in rubric.checks}
    for task in rubric.tasks.values():
        assert set(task.checks) <= defined
    assert {r.id for r in rubric.rules} == {r for t in cfg.tasks.values() for r in t.rules}


def test_link_checks_match_the_rubric() -> None:
    rubric = load_validation_rubric()
    for tier in ("open_weight", "frontier"):
        emitted = _ids(link_checks(_links(("n1", "n2"), ("n1", "n3")), tier, chunk=CHUNK))
        assert emitted == {c for c in rubric.task_checks(prompts.LINK_VERIFICATION, tier) if c != "schema"}


def test_buyer_checks_match_the_rubric() -> None:
    rubric = load_validation_rubric()
    roles = BuyerRoles(roles=[BuyerRole(pathId="p1", role="CFO", authority="approves", evidenceIds=["e1"],
                                        rationale="r")])
    for tier in ("open_weight", "frontier"):
        emitted = _ids(buyer_role_checks(roles, tier, path_id="p1", sent={"e1": "c1"}))
        assert emitted == {c for c in rubric.task_checks(prompts.BUYER_ROLES, tier) if c != "schema"}


# --------------------------------------------------------------------------------------------------
# decide_route: the rules route
# --------------------------------------------------------------------------------------------------


def test_a_matching_rule_routes_to_rules_even_with_open_weight_off() -> None:
    d = decide_route(_config(enabled=False), prompts.BUYER_ROLES, open_weight_available=False,
                     input_chars=10, consecutive_failures=0, rule_hit="no_passing_evidence")
    assert (d.route, d.ruleId) == ("rules", "R2")
    assert "no_passing_evidence" in d.why


def test_without_a_rule_hit_buyers_follow_the_simple_route() -> None:
    d = decide_route(_config(), prompts.BUYER_ROLES, open_weight_available=True,
                     input_chars=10, consecutive_failures=0)
    assert (d.route, d.ruleId) == ("open_weight", "R8")


def test_routing_override_applies_only_inside_the_block() -> None:
    on = _config(enabled=True)
    with routing_override(on):
        assert load_routing().openWeight.enabled is True
    assert load_routing().openWeight.enabled is False


# --------------------------------------------------------------------------------------------------
# link validators
# --------------------------------------------------------------------------------------------------


def test_links_pass_when_every_link_has_one_reasoned_verdict() -> None:
    assert all(c.passed for c in link_checks(_links(("n1", "n2"), ("n1", "n3")), "open_weight", chunk=CHUNK))


def test_coverage_names_missing_extra_and_repeated_links() -> None:
    checks = {c.name: c for c in link_checks(_links(("n1", "n2"), ("n1", "n2"), ("n9", "n2")), "open_weight",
                                             chunk=CHUNK)}
    cov = checks["coverage"]
    assert not cov.passed and cov.blocking
    assert cov.details["expected"] == 2 and cov.details["returned"] == 3
    assert cov.details["missing"] == ["Mid-market SaaS → Procurement"]
    assert cov.details["repeated"] == ["Mid-market SaaS → Finance team"]
    assert cov.details["unknown"] == ["n9 → n2"]


def test_a_verdict_without_a_reason_fails() -> None:
    checks = {c.name: c for c in link_checks(_links(("n1", "n2"), ("n1", "n3"), rationale="ok"), "open_weight",
                                             chunk=CHUNK)}
    assert not checks["rationale"].passed and checks["rationale"].details["short"] == 2


# --------------------------------------------------------------------------------------------------
# buyer role validators and rule
# --------------------------------------------------------------------------------------------------


def _roles(*roles: tuple[str, list[str]]) -> BuyerRoles:
    return BuyerRoles(roles=[BuyerRole(pathId=p, role="Head of AP", authority="owns_budget", evidenceIds=ids,
                                       rationale="named in the careers page") for p, ids in roles])


def test_buyer_roles_pass_when_evidence_was_sent_and_belongs_to_one_company() -> None:
    sent = {"e1": "c1", "e2": "c1", "e3": "c2"}
    assert all(c.passed for c in buyer_role_checks(_roles(("p1", ["e1", "e2"])), "open_weight",
                                                   path_id="p1", sent=sent))


def test_buyer_checks_catch_invented_evidence_mixed_companies_and_wrong_unit() -> None:
    sent = {"e1": "c1", "e3": "c2"}
    checks = {c.name: c for c in buyer_role_checks(_roles(("p1", ["e1", "e9"]), ("p1", ["e1", "e3"]),
                                                          ("p2", ["e1"])), "open_weight", path_id="p1", sent=sent)}
    assert checks["evidence_ids"].details["unknown"] == ["e9"]
    assert checks["one_company"].details["mixed"] == [2]
    assert checks["path_echo"].details == {"asked": "p1", "other": ["p2"]}
    assert all(not c.passed and c.blocking for c in checks.values())


def test_rule_answers_only_when_no_company_has_passing_evidence() -> None:
    empty = [{"companyRecordId": "c1", "evidence": []}, {"companyRecordId": "c2", "evidence": []}]
    rule = no_passing_evidence_rule(empty)
    assert rule.id == "no_passing_evidence" and rule.answer() == BuyerRoles(roles=[])
    some = [{"companyRecordId": "c1", "evidence": [{"evidenceId": "e1"}]}]
    assert no_passing_evidence_rule(some).answer() is None


# --------------------------------------------------------------------------------------------------
# the router runs the rule before any model
# --------------------------------------------------------------------------------------------------


def test_rules_route_answers_without_a_model_call(tracer_store: Any) -> None:  # noqa: F811
    tracer, store = tracer_store
    frontier, ow = FakeTier("gpt-4o"), FakeTier("qwen-test")
    router = TaskRouter(Ctx(frontier, ow), tracer, _config(enabled=False), run_id="mrun_t")
    with tracer.step("position_evaluation", "buyer_role_finder", "identify_buyer_roles",
                     right="identify_buyer_roles") as step:
        result, routing = router.call(step, BuyerRoles, [{"role": "user", "content": "{}"}],
                                      task=prompts.BUYER_ROLES, match_key="buyers:p1",
                                      rule=Rule("no_passing_evidence", lambda: BuyerRoles(roles=[])))
    assert result == BuyerRoles(roles=[])
    assert frontier.calls == 0 and ow.calls == 0
    assert (routing["route"], routing["ruleId"], routing["servedBy"]) == ("rules", "R2", "rules")
    assert routing["attempts"] == [{"route": "rules", "model": None, "outcome": "kept", "rule": "no_passing_evidence"}]
    assert not [s for s in store.list_trace_steps_after("mrun_t", 0) if s["operation"] == "call_model"]


def test_a_rule_not_listed_for_the_task_is_ignored(tracer_store: Any) -> None:  # noqa: F811
    tracer, _ = tracer_store
    frontier = FakeTier("gpt-4o")
    router = TaskRouter(Ctx(frontier, None), tracer, _config(enabled=False), run_id="mrun_t")
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": '{"dimensionKey": "x"}'}]
    with tracer.step("search_research", "link_verifier", "verify_links", right="verify_link") as step:
        _, routing = router.call(step, LinkVerification, messages, task=prompts.LINK_VERIFICATION,
                                 match_key="links:0:1",
                                 rule=Rule("no_passing_evidence", lambda: LinkVerification(links=[])))
    assert frontier.calls == 1 and routing["ruleId"] == "R4"


def test_routing_config_rejects_unknown_fields() -> None:
    raw = load_routing().model_dump(by_alias=True)
    raw["tasks"][prompts.BUYER_ROLES]["rulez"] = []
    with pytest.raises(ValueError):
        RoutingConfig.model_validate(raw)
