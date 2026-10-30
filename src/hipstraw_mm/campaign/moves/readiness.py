"""M04 completeness check and M05 Day Zero dependency check: deterministic, from config/campaign/criteria.yaml.
M13 checks each channel against its platform rules and practice, from config/campaign/channels.yaml.

Each failed criterion opens one blocker keyed by the criterion ID, and the blocker clears when a later run
finds the criterion met. Nothing here calls a model (E0).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from hipstraw_mm.campaign.channels import channel_plans, check_channel, load_channel_standards
from hipstraw_mm.campaign.intake import ASSET_LABEL
from hipstraw_mm.campaign.models import Mandate, Transition
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome
from hipstraw_mm.errors import ConfigError


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    check: str
    args: dict[str, Any] = {}


class CriteriaSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    status: str | None = None
    leadDays: int
    criteria: list[Criterion]
    dependencyRules: list[Criterion]


# -- M04 criterion checks: (mandate, args) -> (met, what is missing) --------------------------------------


def _asset_present(m: Mandate, args: dict[str, Any]) -> tuple[bool, str]:
    kind = args["kind"]
    return any(a.kind == kind for a in m.assets), f"no {kind.replace('_', ' ')} in the submission"


def _field_present(m: Mandate, args: dict[str, Any]) -> tuple[bool, str]:
    value: Any = m
    for part in args["field"].split("."):
        value = getattr(value, part, None)
    return bool(value), f"{args['field']} is missing"


def _channel_assets(m: Mandate, args: dict[str, Any]) -> tuple[bool, str]:
    missing = []
    for channel in m.strategy.channels:
        needed = args.get(channel)
        if needed and not any(a.kind == needed and a.channel in (channel, None) for a in m.assets):
            missing.append(f"{channel} needs {needed.replace('_', ' ')}")
    return not missing, "; ".join(missing)


CRITERION_CHECKS: dict[str, Callable[[Mandate, dict[str, Any]], tuple[bool, str]]] = {
    "asset_present": _asset_present,
    "field_present": _field_present,
    "channel_assets": _channel_assets,
}


# -- M05 dependency rules: (mandate, today, leadDays, channel names) -> [(key, met, detail, channel)] -------

Rule = list[tuple[str, bool, str, str | None]]


def _day_zero_valid(m: Mandate, today: date, lead_days: int, names: dict[str, str]) -> Rule:
    # Day Zero is required by the launch file, and a past Day Zero means the campaign is live.
    return [("DZ01", True, "", None)]


def _assets_ready_before(m: Mandate, today: date, lead_days: int, names: dict[str, str]) -> Rule:
    deadline = m.dayZero - timedelta(days=lead_days)
    out: Rule = []
    for a in m.assets:
        if a.kind == "landing_page" or a.readyDate is None:
            continue
        label = ASSET_LABEL[a.kind] + (f" for {names.get(a.channel, a.channel)}" if a.channel else "")
        out.append((
            f"DZ02:{a.assetId}", a.readyDate <= deadline,
            f"{label} ready {a.readyDate.isoformat()}, after {deadline.isoformat()} "
            f"({lead_days} days before Day Zero {m.dayZero.isoformat()})", a.channel,
        ))
    return out


RULE_CHECKS: dict[str, Callable[[Mandate, date, int, dict[str, str]], Rule]] = {
    "day_zero_valid": _day_zero_valid,
    "assets_ready_before": _assets_ready_before,
}


def load_criteria(config_dir: Path = Path("config")) -> CriteriaSet:
    path = config_dir / "campaign" / "criteria.yaml"
    with open(path, encoding="utf-8") as f:
        criteria = CriteriaSet.model_validate(yaml.safe_load(f))
    unknown = [c.check for c in criteria.criteria if c.check not in CRITERION_CHECKS]
    unknown += [r.check for r in criteria.dependencyRules if r.check not in RULE_CHECKS]
    if unknown:
        raise ConfigError(f"{path}: unknown checks {', '.join(unknown)}")
    return criteria


def _apply(ctx: MoveContext, results: list[tuple[str, str, bool, str, str | None]]) -> MoveOutcome:
    """Open a blocker per unmet key (once) and clear an open one whose key is now met."""
    out = MoveOutcome()
    refs = ctx.brief_ref()
    for key, text, met, detail, channel in results:
        existing = ctx.open_item("blocker", key)
        if not met and existing is None:
            out.newItems.append(ctx.new_item("blocker", "readiness", f"{text}: not met ({detail})", "open", refs,
                                             key=key, channel=channel))
        elif met and existing is not None:
            out.transitions.append(Transition(itemId=existing.itemId, fromState="open", toState="cleared",
                                              evidenceRefs=refs))
    out.note = f"{sum(1 for r in results if not r[2])} of {len(results)} checks not met"
    return out


@register("readiness.completeness")
def completeness(ctx: MoveContext) -> MoveOutcome:
    criteria = load_criteria(ctx.config_dir)
    results: list[tuple[str, str, bool, str, str | None]] = []
    for c in criteria.criteria:
        met, detail = CRITERION_CHECKS[c.check](ctx.mandate, c.args)
        results.append((c.id, c.text, met, detail, None))
    return _apply(ctx, results)


@register("readiness.day_zero_dependencies")
def day_zero_dependencies(ctx: MoveContext) -> MoveOutcome:
    criteria = load_criteria(ctx.config_dir)
    standards = load_channel_standards(ctx.config_dir)
    names = {c: standards.name(c) for c in ctx.mandate.strategy.channels}
    results = []
    for rule in criteria.dependencyRules:
        for key, met, detail, channel in RULE_CHECKS[rule.check](ctx.mandate, ctx.now.date(), criteria.leadDays,
                                                                 names):
            results.append((key, rule.text, met, detail, channel))
    return _apply(ctx, results)


def _open_or_clear(ctx: MoveContext, out: MoveOutcome, kind: str, key: str, *, met: bool, text: str,
                   channel: str, refs: list[str]) -> None:
    existing = ctx.open_item(kind, key)
    if not met and existing is None:
        out.newItems.append(ctx.new_item(kind, "readiness", text, "open", refs, key=key, channel=channel))
    elif met and existing is not None:
        out.transitions.append(Transition(itemId=existing.itemId, fromState="open",
                                          toState="cleared" if kind == "blocker" else "resolved", evidenceRefs=refs))


@register("readiness.channel_standards")
def channel_standards(ctx: MoveContext) -> MoveOutcome:
    """M13: each channel against its rules. A `must` not met opens a blocker and a `must` the Sponsor has not
    stated opens an unknown, both cleared by a later run that finds them met; a `should` not met becomes a fix
    for the Review. Every result is kept as a proposal, so the report can show the whole checklist."""
    standards = load_channel_standards(ctx.config_dir)
    out = MoveOutcome()
    refs = ctx.brief_ref()
    counts: Counter[str] = Counter()
    checked = []
    for plan in channel_plans(ctx.mandate):
        standard = standards.channels.get(plan.channel)
        if standard is None:
            continue  # intake holds it as an unknown: name the platform first
        checked.append(standard.name)
        for r in check_channel(ctx.mandate, plan, standard):
            counts[r.status] += 1
            head = f"{standard.name}: {r.text}"
            if r.level == "must":
                _open_or_clear(ctx, out, "blocker", r.key, met=r.status != "not_met",
                               text=f"{head}: not met ({r.detail})", channel=plan.channel, refs=refs)
                _open_or_clear(ctx, out, "unknown", r.key, met=r.status != "not_stated",
                               text=f"{head}: not stated ({r.detail})", channel=plan.channel, refs=refs)
            out.proposals.append({
                "type": "standard", "channel": plan.channel, "channelName": standard.name, "checkId": r.checkId,
                "text": r.text, "level": r.level, "status": r.status, "detail": r.detail, "source": r.source,
                "standardsVersion": standards.version,
            })
    out.note = (f"{counts['met']} met, {counts['not_met']} not met, {counts['not_stated']} not stated"
                f" ({', '.join(checked) or 'no channel with standards on file'})")
    return out
