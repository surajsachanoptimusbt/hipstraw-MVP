"""Move handlers, looked up by the `handler` name in config/campaign/moves.yaml.

Every first-release handler name is registered up front so the Line lint can check names. A handler
whose unit has not landed raises NotImplementedError; the handler modules imported at the bottom
replace their entries with `@register`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

HANDLER_NAMES = (
    "evidence.capture_assets",         # M01
    "evidence.source_research",        # M02
    "evidence.verify_metrics",         # M03
    "readiness.completeness",          # M04
    "readiness.day_zero_dependencies",  # M05
    "strategy.synthesize",             # M06
    "strategy.propose_variants",       # M07
    "strategy.request_evidence",       # M08
    "testing.draft_test_plan",         # M09
    "testing.dispatch_blocked",        # M10
    "testing.record_delta",            # M11
    "escalation.escalate",             # M12
)


def _not_built(name: str) -> Callable[..., Any]:
    def handler(*_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError(f"Move handler {name} is not built yet")
    return handler


HANDLERS: dict[str, Callable[..., Any]] = {name: _not_built(name) for name in HANDLER_NAMES}


def register(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        HANDLERS[name] = fn
        return fn
    return wrap


from hipstraw_mm.campaign.moves import escalation, evidence, readiness, strategy, testing  # noqa: E402, F401
