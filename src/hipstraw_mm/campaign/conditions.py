"""Line and Move conditions: typed checks over Position and mandate facts (research R4).

A condition is `{all: [...]}` or `{any: [...]}` of `{fact, op, value}`. There is no expression language
and nothing is evaluated from config text: facts are computed by code and compared with a fixed set of
operators, and every check yields a plain-language reason.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from hipstraw_mm.campaign.models import Mandate, PositionItem, PositionSnapshot, TestPlan

# Facts a condition may test, and their types (contracts/config.md "Conditions").
FACT_TYPES: dict[str, type] = {
    "daysToDayZero": int,
    "isLive": bool,
    "hasMetrics": bool,
    "openBlockers": int,
    "openReadinessBlockers": int,
    "unverifiedCoreAssumptions": int,
    "contestedClaims": int,
    "unknowns": int,
    "openHypotheses": int,
    "authorizedTestChannel": bool,
    "testPlanBudgetSet": bool,
}
OPERATORS = ("<", "<=", ">", ">=", "==", "!=")
_EQUALITY = ("==", "!=")
_OPS: dict[str, Callable[[int | bool, int | bool], bool]] = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
}
# How each fact reads in a reason, so a Campaign Manager can see why a Line fits or not.
FACT_LABELS: dict[str, str] = {
    "daysToDayZero": "days to Day Zero",
    "isLive": "campaign is live",
    "hasMetrics": "metrics supplied",
    "openBlockers": "open blockers",
    "openReadinessBlockers": "open readiness blockers",
    "unverifiedCoreAssumptions": "unverified core assumptions",
    "contestedClaims": "contested claims",
    "unknowns": "open unknowns",
    "openHypotheses": "open hypotheses",
    "authorizedTestChannel": "authorized test channel",
    "testPlanBudgetSet": "Test Plan budget set",
}
Facts = dict[str, int | bool]


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact: str
    op: str
    value: bool | int


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all: list[Check] | None = None
    any: list[Check] | None = None

    @model_validator(mode="after")
    def _one_combinator(self) -> Condition:
        if (self.all is None) == (self.any is None):
            raise ValueError("a condition needs exactly one of `all` or `any`")
        return self

    @property
    def checks(self) -> list[Check]:
        return list(self.all if self.all is not None else self.any or [])


def condition_errors(condition: Condition | None, owner: str, field: str) -> list[str]:
    """Lint errors for one condition: unknown facts or operators, and values of the wrong type."""
    if condition is None:
        return []
    errors: list[str] = []
    for check in condition.checks:
        where = f"{owner} {field}"
        fact_type = FACT_TYPES.get(check.fact)
        if fact_type is None:
            errors.append(f"{where}: unknown fact {check.fact!r}")
            continue
        if check.op not in OPERATORS:
            errors.append(f"{where}: unknown operator {check.op!r} on {check.fact}")
            continue
        if fact_type is bool:
            if not isinstance(check.value, bool):
                errors.append(f"{where}: {check.fact} is true or false, not {check.value!r}")
            elif check.op not in _EQUALITY:
                errors.append(f"{where}: {check.fact} is true or false; use == or !=, not {check.op}")
        elif isinstance(check.value, bool):
            errors.append(f"{where}: {check.fact} is a number, not {check.value!r}")
    return errors


def compute_facts(mandate: Mandate, position: PositionSnapshot, today: date,
                  test_plans: Sequence[TestPlan] = ()) -> Facts:
    """The facts Line and Move conditions test, from the head Position and the current mandate only."""
    return facts_from_items(mandate, position.items, today, test_plans)


def facts_from_items(mandate: Mandate, items: Sequence[PositionItem], today: date,
                     test_plans: Sequence[TestPlan] = ()) -> Facts:
    """The same facts over any item list, e.g. a Line run's working state at the start of a stage."""

    def count(kind: str, *states: str, area: str | None = None) -> int:
        return sum(1 for i in items if i.kind == kind and i.state in states and (area is None or i.area == area))

    days = (mandate.dayZero - today).days
    return {
        "daysToDayZero": days,
        "isLive": days <= 0,  # Day Zero itself is the first live day (T0)
        "hasMetrics": mandate.metricsFile is not None,
        "openBlockers": count("blocker", "open"),
        "openReadinessBlockers": count("blocker", "open", area="readiness"),
        "unverifiedCoreAssumptions": sum(
            1 for i in items if i.kind == "assumption" and i.core and i.state in ("open", "awaiting_evidence")
        ),
        "contestedClaims": count("claim", "contested"),
        "unknowns": count("unknown", "open"),
        "openHypotheses": count("hypothesis", "proposed", "planned"),
        "authorizedTestChannel": bool(mandate.authorizedChannels),
        "testPlanBudgetSet": any(tp.budget is not None for tp in test_plans if tp.launchId == mandate.launchId),
    }


def _shown(value: int | bool) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def describe(check: Check, facts: Facts) -> tuple[bool, str]:
    """Whether one check holds, and how it reads: `days to Day Zero = 10 (needs <= 14)`."""
    value = facts[check.fact]
    holds = _OPS[check.op](value, check.value)
    label = FACT_LABELS.get(check.fact, check.fact)
    return holds, f"{label} = {_shown(value)} (needs {check.op} {_shown(check.value)})"


def evaluate(condition: Condition, facts: Facts) -> tuple[bool, list[str]]:
    results = [describe(c, facts) for c in condition.checks]
    held = [ok for ok, _ in results]
    holds = all(held) if condition.all is not None else any(held)
    return holds, [f"{text}: {'met' if ok else 'not met'}" for ok, text in results]
