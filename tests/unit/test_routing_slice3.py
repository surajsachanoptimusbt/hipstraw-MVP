"""Slice 3 of the task router: the company-research child runs. Query planning, listing extraction and
homepage identity go open-weight first with their checks; company evidence and review judgement go to
frontier through the router. Every child model call becomes a traced step."""

from __future__ import annotations

from typing import Any

from hipstraw_mm import prompts
from hipstraw_mm.llm_schemas import HomepageIdentity, ListedCompany, ListingExtraction, PlannedQuery, QueryPlan
from hipstraw_mm.market.child_routing import (
    CHILD_OPERATIONS,
    homepage_checks,
    listing_checks,
    query_plan_checks,
    routed_parse,
)
from hipstraw_mm.market.router import TaskRouter, load_routing
from hipstraw_mm.market.validation_rubric import load_validation_rubric
from tests.unit.test_task_router import Ctx, FakeTier, _config, tracer_store  # noqa: F401

METROS = ["Atlanta--Athens-Clarke County--Sandy Springs, GA-AL CSA", "New York--Newark, NY-NJ-CT-PA CSA"]
PAGE = "Top AP software startups in Atlanta: Acme Ledger builds invoice tools. Brightbooks automates payables."
LINKS = {"L1", "L2"}


def _plan(*queries: str) -> QueryPlan:
    return QueryPlan(queries=[PlannedQuery(query=q, purpose="p") for q in queries])


def _listing(*entries: tuple[str, str | None, str]) -> ListingExtraction:
    return ListingExtraction(companies=[
        ListedCompany(name=n, linkId=lid, excerpt=ex, location=None, metroMatch="unknown", positionMatch="partial")
        for n, lid, ex in entries
    ])


def _by_name(checks: list[Any]) -> dict[str, Any]:
    return {c.name: c for c in checks}


# --------------------------------------------------------------------------------------------------
# configuration and rubric
# --------------------------------------------------------------------------------------------------


def test_every_model_task_except_vichara_repair_is_wired() -> None:
    cfg = load_routing()
    assert {k for k, t in cfg.tasks.items() if not t.wired} == {prompts.VICHARA_REPAIR}
    for task in (prompts.QUERY_PLAN, prompts.LISTING_EXTRACTION, prompts.HOMEPAGE_IDENTITY):
        assert cfg.tasks[task].class_ == "simple"
    for task in (prompts.COMPANY_EVIDENCE, prompts.REVIEW_JUDGEMENT):
        assert cfg.tasks[task].class_ == "complex"


def test_rubric_matches_the_child_checks_including_their_blocking_flags() -> None:
    rubric = load_validation_rubric()
    by_id = {c.id: c for c in rubric.checks}
    samples = {
        prompts.QUERY_PLAN: query_plan_checks(_plan("AP software Atlanta"), "open_weight", max_queries=6,
                                              metros=METROS),
        prompts.LISTING_EXTRACTION: listing_checks(_listing(), "open_weight", page_text=PAGE, link_ids=LINKS),
        prompts.HOMEPAGE_IDENTITY: homepage_checks(
            HomepageIdentity(isCompanyHomepage=False, name=None, excerpt=None, location=None, metroMatch="unknown",
                             positionMatch="weak"), "open_weight", page_text=PAGE),
    }
    for task, checks in samples.items():
        assert {c.name for c in checks} == {c for c in rubric.task_checks(task, "open_weight") if c != "schema"}, task
        for c in checks:
            assert c.blocking == by_id[c.name].blocking, c.name
    assert by_id["metros"].blocking is False


def test_every_child_operation_is_claimed_by_a_skill() -> None:
    from hipstraw_mm.market.agents import load_agent_registry

    claimed = {op for a in load_agent_registry().agents for s in a.skills for op in (s.operations or [])}
    assert set(CHILD_OPERATIONS) <= claimed


# --------------------------------------------------------------------------------------------------
# validators
# --------------------------------------------------------------------------------------------------


def test_query_plan_blocks_on_empty_duplicate_or_too_many_queries() -> None:
    ok = _by_name(query_plan_checks(_plan("AP tools Atlanta", "AP tools New York"), "open_weight",
                                    max_queries=6, metros=METROS))
    assert ok["queries"].passed and ok["metros"].passed
    bad = _by_name(query_plan_checks(_plan("AP tools Atlanta", "ap tools  atlanta", " "), "open_weight",
                                     max_queries=2, metros=METROS))
    q = bad["queries"]
    assert not q.passed and q.blocking
    assert q.details == {"returned": 3, "max": 2, "empty": 1, "duplicates": ["ap tools atlanta"]}


def test_a_missing_metro_is_a_warning_not_a_rejection() -> None:
    checks = _by_name(query_plan_checks(_plan("AP tools Atlanta"), "open_weight", max_queries=6, metros=METROS))
    m = checks["metros"]
    assert not m.passed and not m.blocking
    assert m.details["missing"] == [METROS[1]]


def test_listing_link_ids_must_be_on_the_page() -> None:
    checks = _by_name(listing_checks(_listing(("Acme Ledger", "L9", "Acme Ledger builds invoice tools")),
                                     "open_weight", page_text=PAGE, link_ids=LINKS))
    assert not checks["link_ids"].passed and checks["link_ids"].details["unknown"] == ["L9"]


def test_listing_excerpts_must_mostly_be_on_the_page() -> None:
    good = ("Acme Ledger", "L1", "Acme Ledger builds invoice tools")
    bad = ("Clearpay", "L2", "Clearpay is a payments leader")
    half = _by_name(listing_checks(_listing(good, bad), "open_weight", page_text=PAGE, link_ids=LINKS))
    assert half["excerpts"].passed and half["excerpts"].details["notFound"] == ["Clearpay"]
    most = _by_name(listing_checks(_listing(good, bad, ("Zed", None, "Zed rules")), "open_weight",
                                   page_text=PAGE, link_ids=LINKS))
    assert not most["excerpts"].passed
    empty = _by_name(listing_checks(_listing(), "open_weight", page_text=PAGE, link_ids=LINKS))
    assert empty["excerpts"].passed and empty["link_ids"].passed


def test_homepage_answer_must_be_consistent_and_quoted() -> None:
    def ident(is_home: bool, name: str | None, excerpt: str | None) -> HomepageIdentity:
        return HomepageIdentity(isCompanyHomepage=is_home, name=name, excerpt=excerpt, location=None,
                                metroMatch="unknown", positionMatch="weak")

    ok = _by_name(homepage_checks(ident(True, "Acme Ledger", "Acme Ledger builds invoice tools"), "open_weight",
                                  page_text=PAGE))
    assert ok["consistency"].passed and ok["homepage_excerpt"].passed
    unquoted = _by_name(homepage_checks(ident(True, "Acme Ledger", "Acme is great"), "open_weight", page_text=PAGE))
    assert not unquoted["homepage_excerpt"].passed
    mixed = _by_name(homepage_checks(ident(False, "Acme Ledger", None), "open_weight", page_text=PAGE))
    assert not mixed["consistency"].passed and mixed["homepage_excerpt"].passed
    missing = _by_name(homepage_checks(ident(True, None, None), "open_weight", page_text=PAGE))
    assert not missing["consistency"].passed


# --------------------------------------------------------------------------------------------------
# routed_parse: a traced, routed step inside a market run; a plain call outside one
# --------------------------------------------------------------------------------------------------


class PlanTier(FakeTier):
    def parse(self, schema: Any, messages: list[dict[str, str]], match_key: str, prompt_version: str,
              **_: Any) -> Any:
        self.calls += 1
        self.keys.append(match_key)
        self.last_raw = {"model": self.model}
        return _plan("AP tools Atlanta")


class _Ctx(Ctx):
    def __init__(self, frontier: Any, open_llm: Any, router: Any = None) -> None:
        super().__init__(frontier, open_llm)
        self.router = router


def test_without_a_router_the_call_is_the_plain_one() -> None:
    frontier = PlanTier("gpt-4o")
    ctx = _Ctx(frontier, None)
    result = routed_parse(ctx, QueryPlan, prompts.QUERY_PLAN, {"x": 1}, match_key="cand_1",
                          operation="plan_queries", run_id="run_1", step_label="discover", inputs={})
    assert result == _plan("AP tools Atlanta") and frontier.keys == ["cand_1"]


def test_with_a_router_the_call_is_a_routed_traced_step(tracer_store: Any) -> None:  # noqa: F811
    tracer, store = tracer_store
    frontier, ow = PlanTier("gpt-4o"), PlanTier("qwen-test")
    ctx = _Ctx(frontier, ow)
    ctx.router = TaskRouter(ctx, tracer, _config(), run_id="mrun_t")  # type: ignore[arg-type]
    result = routed_parse(
        ctx, QueryPlan, prompts.QUERY_PLAN, {"x": 1}, match_key="cand_1", operation="plan_queries",
        run_id="run_1", step_label="discover", inputs={"metros": 2},
        validate=lambda r, tier: query_plan_checks(r, tier, max_queries=6, metros=METROS),
        outputs=lambda r: {"queries": len(r.queries)},
    )
    assert result.queries[0].query == "AP tools Atlanta"
    assert ow.keys == ["ow:qwen-test:cand_1"] and frontier.calls == 0  # the metro warning does not escalate
    steps = store.list_trace_steps_after("mrun_t", 0)
    business = [s for s in steps if s["operation"] == "plan_queries"][0]
    assert business["inputs"] == {"metros": 2, "childRunId": "run_1"}
    assert business["outputs"]["queries"] == 1
    routing = business["outputs"]["routing"]
    assert (routing["ruleId"], routing["servedBy"]) == ("R8", "open_weight")
    metros = next(c for c in routing["validation"]["open_weight"] if c["id"] == "metros")
    assert metros["passed"] is False and metros["blocking"] is False
    assert any(c["name"] == "open_weight.metros" and "warning" in c["reason"] for c in business["checks"])
    workers = [s for s in steps if s["operation"] == "call_model"]
    assert len(workers) == 1 and workers[0]["parentStepId"] == business["stepId"]


def test_context_counts_calls_on_both_tiers() -> None:
    from hipstraw_mm.context import Context

    assert Context.model_calls(_Ctx(PlanTier("a"), None)) == 0  # type: ignore[arg-type]
    frontier, ow = PlanTier("a"), PlanTier("b")
    frontier.calls, ow.calls = 3, 4
    assert Context.model_calls(_Ctx(frontier, ow)) == 7  # type: ignore[arg-type]
