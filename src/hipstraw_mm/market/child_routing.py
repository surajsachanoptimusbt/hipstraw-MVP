"""Task routing inside the company-research child runs (feature 002's discover, verify and review).

Inside a market run, each child model call is its own traced business step: the router picks the
tier, the model attempts are worker steps beneath it, and the routing and validation log go into the
step's outputs. Outside a market run (feature 002 on its own) there is no router and the call is the
plain one, as before.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from hipstraw_mm import prompts
from hipstraw_mm.evidence.excerpt_check import check_excerpt
from hipstraw_mm.market.router import Check, Validator

T = TypeVar("T", bound=BaseModel)
Doc = dict[str, Any]

# operation -> (layer, actor, right), matching the child step that makes the call (stages._child_steps)
CHILD_OPERATIONS = {
    "plan_queries": ("search_research", "company_search", "discover_companies"),
    "extract_listing": ("search_research", "company_search", "discover_companies"),
    "read_homepage": ("search_research", "company_search", "discover_companies"),
    "extract_evidence": ("search_research", "company_search", "discover_companies"),
    "judge_company": ("market_manager", "review", "record_disposition"),
}


def routed_parse(
    ctx: Any,
    schema: type[T],
    task: str,
    payload: Doc,
    *,
    match_key: str,
    operation: str,
    run_id: str,
    step_label: str,
    inputs: Doc,
    validate: Validator | None = None,
    outputs: Callable[[T], Doc] | None = None,
) -> T:
    """One child model call: routed and traced inside a market run, the plain call outside one.

    Raises LLMSchemaError like the plain call when no tier returns a usable answer.
    """
    messages = prompts.messages(task, payload)
    router = getattr(ctx, "router", None)
    if router is None:
        result: T = ctx.llm.parse(schema, messages, match_key, task, run_id=run_id, step=step_label)
        return result
    layer, actor, right = CHILD_OPERATIONS[operation]
    with router.tracer.step(layer, actor, operation, right=right) as step:
        step.set_inputs({**inputs, "childRunId": run_id})
        answer, routing = router.call(step, schema, messages, task=task, match_key=match_key,
                                      validate=validate, log_run_id=run_id)
        routed: T = answer
        step.set_outputs({**(outputs(routed) if outputs else {}), "routing": routing})
    return routed


# --------------------------------------------------------------------------------------------------
# validators (rubric: config/validation.yaml)
# --------------------------------------------------------------------------------------------------


def _metro_cities(name: str) -> list[str]:
    """'Atlanta--Athens-Clarke County--Sandy Springs, GA-AL CSA' -> its city names, lower case."""
    return [part.strip().casefold() for part in name.split(",")[0].split("--") if part.strip()]


def query_plan_checks(result: Any, tier: str, *, max_queries: int, metros: list[str]) -> list[Check]:
    queries = [" ".join(q.query.split()) for q in result.queries]
    empty = sum(1 for q in queries if not q)
    seen: set[str] = set()
    duplicates: list[str] = []
    for q in (q.casefold() for q in queries if q):
        if q in seen and q not in duplicates:
            duplicates.append(q)
        seen.add(q)
    ok = 1 <= len(queries) <= max_queries and not empty and not duplicates
    text = " | ".join(queries).casefold()
    missing = [m for m in metros if not any(city in text for city in _metro_cities(m))]
    return [
        Check("queries", ok, True,
              f"{len(queries)} distinct queries within the limit of {max_queries}" if ok
              else f"{len(queries)} queries (limit {max_queries}), {empty} blank, {len(duplicates)} repeated",
              {"returned": len(queries), "max": max_queries, "empty": empty, "duplicates": duplicates}),
        Check("metros", not missing, False,
              "every metro is named by a query" if not missing
              else f"{len(missing)} metro(s) not named by any query",
              {"metros": len(metros), "missing": missing}),
    ]


def listing_checks(result: Any, tier: str, *, page_text: str, link_ids: set[str]) -> list[Check]:
    unknown = sorted({c.linkId for c in result.companies if c.linkId and c.linkId not in link_ids})
    quoted = [c.name for c in result.companies
              if check_excerpt(c.excerpt, page_text, claim_value=c.name).status == "pass"]
    not_found = [c.name for c in result.companies if c.name not in quoted]
    total = len(result.companies)
    enough = total == 0 or len(quoted) * 2 >= total
    return [
        Check("link_ids", not unknown, True,
              "every linkId is a link on the page" if not unknown else f"{len(unknown)} linkId(s) are not on the page",
              {"companies": total, "unknown": unknown}),
        Check("excerpts", enough, True,
              f"{len(quoted)} of {total} companies quoted from the page",
              {"companies": total, "quoted": len(quoted), "notFound": not_found[:10]}),
    ]


def homepage_checks(result: Any, tier: str, *, page_text: str) -> list[Check]:
    filled = bool((result.name or "").strip()) and bool((result.excerpt or "").strip())
    empty = not (result.name or "").strip() and not (result.excerpt or "").strip()
    consistent = filled if result.isCompanyHomepage else empty
    quoted = True
    if result.isCompanyHomepage and filled:
        quoted = check_excerpt(result.excerpt, page_text, claim_value=result.name).status == "pass"
    return [
        Check("consistency", consistent, True,
              "the fields match the verdict" if consistent
              else ("a homepage needs a name and an excerpt" if result.isCompanyHomepage
                    else "'not a homepage' should carry no name or excerpt"),
              {"isCompanyHomepage": result.isCompanyHomepage, "name": result.name, "hasExcerpt": bool(result.excerpt)}),
        Check("homepage_excerpt", quoted, True,
              "not a homepage" if not result.isCompanyHomepage
              else ("the excerpt is on the page and names the company" if quoted
                    else "the excerpt is not on the page or does not name the company"),
              {"excerpt": (result.excerpt or "")[:300] or None, "name": result.name}),
    ]
