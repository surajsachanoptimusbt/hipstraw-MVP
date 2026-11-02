"""M14 Review live performance (Nov 2 meeting: review running campaigns daily and give them direction).

Each live channel's measures over the last days, against the benchmarks and rules in
config/campaign/performance.yaml. A rule that holds becomes a direction: a `proposed` hypothesis with the
change to make, and a Direction record with the measure that should move, for M11 to check once the Sponsor
has applied it. A `must` rule (a delivery defect) also opens a blocker, cleared when the measure recovers. A
measure far from its benchmark that no rule explains is a repertoire gap, raised once for the domain owner: a
candidate for a new rule or Move. Rules, not a model (E0); a measure with too little data waits.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from hipstraw_mm.campaign.channels import channel_plans, load_channel_standards
from hipstraw_mm.campaign.models import Direction, MoveExecution, PositionItem, Transition
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome
from hipstraw_mm.campaign.performance import (
    ChannelState,
    PerformanceRules,
    Rule,
    channel_state,
    daily_metrics,
    fmt,
    holds,
    load_performance_rules,
    measure_between,
    metric_evidence_ids,
    status,
)

OPEN_DIRECTION = ("proposed", "planned", "running")


def _open_direction(items: list[PositionItem], key: str) -> bool:
    return any(i.kind == "hypothesis" and i.key == key and i.state in OPEN_DIRECTION for i in items)


def _gaps_raised(ctx: MoveContext) -> set[str]:
    return {p["key"] for e in ctx.store.list_for_launch(MoveExecution, ctx.launch_id) if e.moveId == ctx.move.id
            for p in e.proposals if p.get("type") == "gap" and p.get("key")}


def _fires(rule: Rule, state: ChannelState, rules: PerformanceRules, setup: dict[str, Any]) -> bool:
    return all(holds(c, state, rules, setup) for c in rule.when)


@register("performance.review")
def review_performance(ctx: MoveContext) -> MoveOutcome:
    rules = load_performance_rules(ctx.config_dir)
    standards = load_channel_standards(ctx.config_dir)
    series = daily_metrics(ctx.evidence)
    today = ctx.now.date()
    setups = {p.channel: p.setup for p in channel_plans(ctx.mandate)}
    out = MoveOutcome()
    states: dict[str, ChannelState] = {}
    notes: list[str] = []

    for channel in ctx.mandate.strategy.channels:
        name = standards.name(channel)
        if channel not in rules.measures or channel not in series:
            continue
        state = channel_state(rules, channel, series[channel], today)
        if not state.window:
            notes.append(f"{name}: no data in the last {rules.window} days")
            continue
        states[channel] = state
        measures = {}
        for m, md in rules.measures[channel].items():
            mv = state.values[m]
            measures[m] = {"label": md.label, "value": mv.value, "display": fmt(md, mv.value), "unit": md.unit,
                           "benchmark": md.benchmark, "benchmarkDisplay": fmt(md, md.benchmark),
                           "status": status(md, mv.value), "waiting": mv.waiting, "better": md.better}
        out.proposals.append({"type": "performance", "channel": channel, "channelName": name,
                              "day": today.isoformat(), "window": [state.window[0].isoformat(),
                                                                   state.window[-1].isoformat()],
                              "measures": measures})

    paid = [c for c, s in states.items() if (s.values.get("daily_spend") and s.values["daily_spend"].value or 0) > 0]
    shares = {c: states[c].values["qualified_share"].value for c in paid if "qualified_share" in states[c].values}
    fired: dict[str, set[str]] = defaultdict(set)
    raised: list[str] = []
    for rule in rules.rules:
        for channel, state in states.items():
            if channel not in rule.channels or rule.measure in fired[channel]:
                continue
            if not _fires(rule, state, rules, setups.get(channel, {})):
                continue
            first = rule.when[0]
            d = rules.measure(channel, first.measure)
            best = max((c for c in shares if c != channel and shares[c] is not None),
                       key=lambda c: shares[c] or 0.0, default=None)
            if best is None:  # no other channel has enough applications yet: the one whose reach names the role
                best = next((c for c in paid if c != channel and c in standards.channels
                             and "company size" in standards.channels[c].reach.how), None)
            fired[channel] |= {rule.measure, *(c.measure for c in rule.when)}
            words = {"name": standards.name(channel), "value": fmt(d, state.values[first.measure].value),
                     "benchmark": fmt(d, d.benchmark if d else None), "window": rules.window,
                     "best": standards.name(best) if best else "a channel that targets by role and company size"}
            finding, change = rule.finding.format(**words), rule.change.format(**words)
            key = f"{rule.id}:{channel}"
            refs = metric_evidence_ids(ctx.evidence, channel, state.window[0], state.window[-1])
            if rule.level == "must" and ctx.open_item("blocker", key) is None:
                out.newItems.append(ctx.new_item("blocker", "readiness", finding, "open", refs, key=key,
                                                 channel=channel))
            if _open_direction(ctx.items, key):
                continue
            target_channel = channel if rule.scope == "channel" else None
            baseline = measure_between(rules, target_channel, rule.measure, series, state.window[0], state.window[-1])
            target = rules.measure(target_channel, rule.measure)
            hypothesis = ctx.new_item("hypothesis", "strategy", f"{words['name']}: {change}", "proposed", refs,
                                      key=key, channel=channel, note=finding)
            out.newItems.append(hypothesis)
            direction = Direction(
                directionId=ctx.record_id("dir"), launchId=ctx.launch_id, lineRunId=ctx.line_run_id,
                hypothesisItemId=hypothesis.itemId, ruleId=rule.id, channel=target_channel, cause=rule.cause,
                finding=finding, change=change, measure=rule.measure, expected=rule.expected,
                baseline=baseline if baseline is not None else 0.0,
                benchmark=target.benchmark if target else None, windowStart=state.window[0].isoformat(),
                windowEnd=state.window[-1].isoformat(), source=rule.source, createdAt=ctx.now.isoformat(),
            )
            ctx.store.insert(direction)
            out.produced.append(direction.directionId)
            raised.append(f"{rule.id} {words['name']}")

    # A delivery blocker clears once its rule no longer holds on fresh data.
    by_id = {r.id: r for r in rules.rules}
    for item in ctx.items:
        if item.kind != "blocker" or item.state != "open" or not item.key or ":" not in item.key:
            continue
        rule_id, channel = item.key.split(":", 1)
        held, now_state = by_id.get(rule_id), states.get(channel)
        if held and now_state and not _fires(held, now_state, rules, setups.get(channel, {})):
            out.transitions.append(Transition(itemId=item.itemId, fromState="open", toState="cleared",
                                              evidenceRefs=metric_evidence_ids(ctx.evidence, channel,
                                                                               now_state.window[0],
                                                                               now_state.window[-1])))

    # A measure far from its benchmark that no rule reads on this channel is a repertoire gap, raised once.
    already = _gaps_raised(ctx)
    for channel, gap_state in states.items():
        read = {x for r in rules.rules if channel in r.channels
                for x in [*(c.measure for c in r.when), *([r.measure] if r.scope == "channel" else [])]}
        for m, gd in rules.measures[channel].items():
            gv = gap_state.values[m].value
            if gv is None or gd.benchmark is None or m in read:
                continue
            far = gv < gd.benchmark / rules.gapFactor if gd.better == "higher" else gv > gd.benchmark * rules.gapFactor
            key = f"GAP:{channel}:{m}"
            if far and key not in already:
                out.proposals.append({
                    "type": "gap", "area": "strategy", "key": key, "itemRefs": [], "day": today.isoformat(),
                    "channel": channel,
                    "evidenceRefs": metric_evidence_ids(ctx.evidence, channel, gap_state.window[0],
                                                        gap_state.window[-1]),
                    "text": f"Repertoire gap: {standards.name(channel)} {gd.label.lower()} {fmt(gd, gv)} against a "
                            f"{fmt(gd, gd.benchmark)} benchmark, and no diagnosis rule reads this measure. A candidate "
                            "for a new rule or Move, for the domain owner",
                })
                raised.append(f"gap {standards.name(channel)} {gd.label.lower()}")

    waiting = [f"{standards.name(c)}: {n} measures waiting for data" for c, s in states.items()
               if (n := sum(1 for v in s.values.values() if v.waiting))]
    out.note = "; ".join([*(f"new: {r}" for r in raised), *notes, *waiting]) or \
        f"{len(states)} channels reviewed; nothing new"
    return out
