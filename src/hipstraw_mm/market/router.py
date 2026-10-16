"""Task router (router.v1): picks rules, open-weight or frontier for each model task.

The choice is never a model call. `decide_route` is an ordered rule list over the task's class in
config/routing.yaml and a few facts about the call. `TaskRouter` carries the choice out inside the
caller's business step: an open-weight answer is kept only when every blocking validator passes;
otherwise the same messages go once to frontier under today's match key. Frontier is the last tier,
so its validator results are recorded and never reject. Every model attempt stays a `call_model`
worker step; the route and escalation go into the business step's checks and `outputs.routing`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field

from hipstraw_mm.adapters.llm import LLMSchemaError
from hipstraw_mm.adapters.replay import ReplayMissingError
from hipstraw_mm.errors import ExternalServiceError

if TYPE_CHECKING:
    from hipstraw_mm.context import Context
    from hipstraw_mm.market.trace import Tracer, TraceStepContext

T = TypeVar("T", bound=BaseModel)
Route = Literal["rules", "open_weight", "frontier"]
Doc = dict[str, Any]


class TaskRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    class_: Literal["rules", "simple", "complex"] = Field(alias="class")
    wired: bool


class OpenWeightPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    maxInputChars: int = Field(gt=0)
    maxConsecutiveFailures: int = Field(gt=0)
    timeoutSeconds: float = Field(gt=0)


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    source: str
    openWeight: OpenWeightPolicy
    tasks: dict[str, TaskRoute]
    unused: list[str] = Field(default_factory=list)


@cache
def _load(path: Path) -> RoutingConfig:
    with open(path, encoding="utf-8") as f:
        return RoutingConfig.model_validate(yaml.safe_load(f))


def load_routing(config_dir: Path = Path("config")) -> RoutingConfig:
    return _load(Path(config_dir) / "routing.yaml")


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    ruleId: str
    why: str


def decide_route(
    config: RoutingConfig,
    task: str,
    *,
    open_weight_available: bool,
    input_chars: int,
    consecutive_failures: int,
) -> RouteDecision:
    """The first rule that applies wins."""
    entry = config.tasks.get(task)
    policy = config.openWeight
    if entry is None:
        return RouteDecision("frontier", "R1", "task is not in the routing table")
    if entry.class_ == "rules":
        return RouteDecision("rules", "R2", "rules are sufficient for this task")
    if entry.class_ == "complex":
        return RouteDecision("frontier", "R3", "complex reasoning task")
    if not policy.enabled:
        return RouteDecision("frontier", "R4", "open-weight route is off in routing.yaml")
    if not open_weight_available:
        return RouteDecision("frontier", "R5", "no open-weight endpoint is configured")
    if input_chars > policy.maxInputChars:
        return RouteDecision("frontier", "R6", f"input is {input_chars} chars, over {policy.maxInputChars}")
    if consecutive_failures >= policy.maxConsecutiveFailures:
        return RouteDecision(
            "frontier", "R7", f"{consecutive_failures} open-weight call failures in a row in this stage"
        )
    return RouteDecision("open_weight", "R8", "simple model task")


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    blocking: bool
    reason: str
    details: dict[str, Any] | None = None

    def log(self) -> Doc:
        return {"id": self.name, "passed": self.passed, "blocking": self.blocking, "reason": self.reason,
                "details": self.details}


Validator = Callable[[Any, Route], list[Check]]


class TaskRouter:
    """One per stage, so the count of open-weight call failures in a row covers the stage's calls."""

    def __init__(self, ctx: Context, tracer: Tracer, config: RoutingConfig, *, run_id: str) -> None:
        self.ctx = ctx
        self.tracer = tracer
        self.config = config
        self.run_id = run_id
        self.consecutive_failures = 0

    def call(
        self,
        step: TraceStepContext,
        schema: type[T],
        messages: list[dict[str, str]],
        *,
        task: str,
        match_key: str,
        validate: Validator | None = None,
    ) -> tuple[T, Doc]:
        from hipstraw_mm.market.stages import model_call

        open_llm = getattr(self.ctx, "open_llm", None)
        decision = decide_route(
            self.config, task,
            open_weight_available=open_llm is not None,
            input_chars=sum(len(m.get("content", "")) for m in messages),
            consecutive_failures=self.consecutive_failures,
        )
        if decision.route == "rules":
            raise ValueError(f"{task} is a rules task; its rule handler answers it, not the router")
        entry = self.config.tasks.get(task)
        routing: Doc = {
            "routerVersion": self.config.version, "task": task,
            "class": entry.class_ if entry else None,
            "ruleId": decision.ruleId, "why": decision.why, "route": decision.route,
            "servedBy": None, "escalated": False, "escalationReason": None, "attempts": [],
            "validation": {},
        }
        form_ok = Check("schema", True, True, f"parsed into {schema.__name__}")

        if decision.route == "open_weight":
            assert open_llm is not None
            reason: str | None = None
            try:
                result = model_call(
                    self.ctx, self.tracer, schema, messages,
                    match_key=f"ow:{open_llm.model}:{match_key}", prompt_version=task, run_id=self.run_id,
                    client=open_llm, route="open_weight", max_attempts=1,
                )
            except LLMSchemaError as exc:
                # Only call failures count toward R7: a failing endpoint, not a weak answer.
                self.consecutive_failures += 1
                reason = f"{type(exc).__name__}: {exc}"
                if validate:
                    form = Check("schema", False, True, str(exc))
                    self._record(step, [form], "open_weight")
                    routing["validation"]["open_weight"] = [form.log()]
            except (ExternalServiceError, ReplayMissingError) as exc:
                self.consecutive_failures += 1
                reason = f"{type(exc).__name__}: {exc}"
            else:
                self.consecutive_failures = 0
                checks = [form_ok, *validate(result, "open_weight")] if validate else []
                failed = self._record(step, checks, "open_weight")
                if validate:
                    routing["validation"]["open_weight"] = [c.log() for c in checks]
                if not failed:
                    routing["servedBy"] = "open_weight"
                    routing["attempts"].append({"route": "open_weight", "model": open_llm.model, "outcome": "kept"})
                    return result, routing
                reason = "; ".join(f"{c.name}: {c.reason}" for c in failed)
            routing["attempts"].append({"route": "open_weight", "model": open_llm.model, "outcome": reason})
            routing.update(escalated=True, escalationReason=reason)

        result = model_call(
            self.ctx, self.tracer, schema, messages,
            match_key=match_key, prompt_version=task, run_id=self.run_id,
        )
        checks = [form_ok, *validate(result, "frontier")] if validate else []
        self._record(step, checks, "frontier")
        if validate:
            routing["validation"]["frontier"] = [c.log() for c in checks]
        routing["servedBy"] = "frontier"
        routing["attempts"].append({"route": "frontier", "model": self.ctx.llm.model, "outcome": "kept"})
        return result, routing

    @staticmethod
    def _record(step: TraceStepContext, checks: list[Check], tier: Route) -> list[Check]:
        """Write each check on the business step; return the ones that reject an open-weight answer."""
        for c in checks:
            if c.passed:
                note = c.reason
            elif tier == "frontier":
                note = f"{c.reason} (recorded only: frontier is the last tier)"
            else:
                note = f"{c.reason} ({'escalates to frontier' if c.blocking else 'warning'})"
            step.add_check(f"{tier}.{c.name}", "pass" if c.passed else "fail", note)
        return [c for c in checks if not c.passed and c.blocking] if tier == "open_weight" else []
