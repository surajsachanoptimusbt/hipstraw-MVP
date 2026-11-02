"""Live performance (Nov 2 meeting: review running campaigns daily, find what is not working, and give it
direction). Daily metric exports become channel measures (rates computed from counts, never taken from a
platform's own summary), compared with published benchmarks, and diagnosis rules turn a gap into a direction
with the change to make and the measure that should move. Thresholds, benchmarks and rules live in
config/campaign/performance.yaml, each with its source; the functions here only compute. Nothing calls a
model (E0).

A measure with too little data is `waiting`, never judged: a rate on a handful of clicks says nothing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from hipstraw_mm.campaign.models import EvidenceRecord
from hipstraw_mm.errors import ConfigError

Status = Literal["ok", "worse", "better", "waiting"]


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeasureDef(_Config):
    label: str
    num: str | None = None  # a ratio of two summed counts...
    den: str | None = None
    latest: str | None = None  # ...or the latest value of one metric (frequency)
    perDay: str | None = None  # ...or a daily average (spend per day)
    unit: Literal["%", "USD", "x"]
    better: Literal["higher", "lower"]
    benchmark: float | None = None
    benchmarkSource: str | None = None
    minimum: dict[str, float] = {}


class Condition(_Config):
    measure: str
    op: Literal["above", "below", "belowBenchmark", "aboveBenchmark", "atLeastBenchmark", "dropFromBest",
                "belowSetup"]
    value: float
    setup: str | None = None  # belowSetup: the channel plan's setup field, e.g. dailyBudget


class Rule(_Config):
    id: str
    cause: str
    channels: list[str]
    level: Literal["must", "should"]
    when: list[Condition]
    finding: str
    change: str
    measure: str
    scope: Literal["channel", "campaign"] = "channel"
    expected: Literal["increase", "decrease"]
    source: str


class PerformanceRules(_Config):
    version: str
    status: str | None = None
    window: int
    deltaMinDays: int
    supportedChange: float
    gapFactor: float
    measures: dict[str, dict[str, MeasureDef]]
    campaign: dict[str, MeasureDef]
    rules: list[Rule]

    def measure(self, channel: str | None, name: str) -> MeasureDef | None:
        return self.campaign.get(name) if channel is None else self.measures.get(channel, {}).get(name)


def load_performance_rules(config_dir: Path = Path("config")) -> PerformanceRules:
    path = config_dir / "campaign" / "performance.yaml"
    with open(path, encoding="utf-8") as f:
        rules = PerformanceRules.model_validate(yaml.safe_load(f))
    for r in rules.rules:
        for c in r.channels:
            names = [r.measure if r.scope == "channel" else None, *(w.measure for w in r.when)]
            missing = [n for n in names if n and n not in rules.measures.get(c, {})]
            if missing:
                raise ConfigError(f"{path}: rule {r.id} uses {', '.join(missing)}, not a {c} measure")
        if r.scope == "campaign" and r.measure not in rules.campaign:
            raise ConfigError(f"{path}: rule {r.id} uses campaign measure {r.measure}, not defined")
    return rules


# -- the daily series --------------------------------------------------------------------------------------

Daily = dict[date, dict[str, float]]


def daily_metrics(evidence: list[EvidenceRecord]) -> dict[str, Daily]:
    """Metric evidence named `<channel>.<metric>` with a one-day window, by channel and day. A later export of
    the same day and metric replaces an earlier one (a corrected export)."""
    out: dict[str, Daily] = defaultdict(lambda: defaultdict(dict))
    for e in sorted((e for e in evidence if e.kind == "metric" and e.metric), key=lambda e: e.capturedAt):
        m = e.metric
        assert m is not None
        if "." not in m.metric or not m.windowEnd:
            continue
        channel, name = m.metric.split(".", 1)
        out[channel][date.fromisoformat(m.windowEnd[:10])][name] = m.value
    return {c: dict(d) for c, d in out.items()}


def metric_evidence_ids(evidence: list[EvidenceRecord], channel: str | None, start: date, end: date) -> list[str]:
    ids = []
    for e in evidence:
        if e.kind != "metric" or not e.metric or not e.metric.windowEnd:
            continue
        day = date.fromisoformat(e.metric.windowEnd[:10])
        if start <= day <= end and (channel is None or e.metric.metric.startswith(f"{channel}.")):
            ids.append(e.evidenceId)
    return ids


@dataclass
class Value:
    value: float | None
    totals: dict[str, float] = field(default_factory=dict)
    waiting: str | None = None  # why there is too little data


def compute(definition: MeasureDef, days: list[dict[str, float]]) -> Value:
    if not days:
        return Value(None, waiting="no data in the window")
    totals: dict[str, float] = defaultdict(float)
    for d in days:
        for k, v in d.items():
            totals[k] += v
    short = [f"{k} {totals.get(k, 0):g} of {n:g}" for k, n in definition.minimum.items() if totals.get(k, 0) < n]
    if short:
        return Value(None, dict(totals), waiting="not enough data yet: " + ", ".join(short))
    if definition.latest:
        latest = next((d[definition.latest] for d in reversed(days) if definition.latest in d), None)
        return Value(latest, dict(totals))
    if definition.perDay:
        return Value(totals.get(definition.perDay, 0.0) / len(days), dict(totals))
    assert definition.num and definition.den
    den = totals.get(definition.den, 0.0)
    if den <= 0:
        return Value(None, dict(totals), waiting=f"no {definition.den} yet")
    return Value(totals.get(definition.num, 0.0) / den, dict(totals))


def status(definition: MeasureDef, value: float | None) -> Status:
    if value is None:
        return "waiting"
    if definition.benchmark is None:
        return "ok"
    worse = value < definition.benchmark if definition.better == "higher" else value > definition.benchmark
    return "worse" if worse else "ok"


def fmt(definition: MeasureDef | None, value: float | None) -> str:
    if value is None or definition is None:
        return "n/a"
    if definition.unit == "%":
        return f"{value * 100:.2f}%"
    if definition.unit == "USD":
        return f"${value:,.2f}"
    return f"{value:.1f}"


# -- evaluating a channel on a day -------------------------------------------------------------------------


@dataclass
class ChannelState:
    channel: str
    today: date
    window: list[date]
    values: dict[str, Value]
    best: dict[str, float]  # each measure's best earlier window value, for `dropFromBest`


def _window_days(series: Daily, end: date, length: int) -> list[date]:
    return [d for d in sorted(series) if end - timedelta(days=length - 1) <= d <= end]


def channel_state(rules: PerformanceRules, channel: str, series: Daily, today: date,
                  setup: dict[str, Any] | None = None) -> ChannelState:
    defs = rules.measures.get(channel, {})
    window = _window_days(series, today, rules.window)
    values = {name: compute(d, [series[x] for x in window]) for name, d in defs.items()}
    best: dict[str, float] = {}
    earlier = [d for d in sorted(series) if d < (window[0] if window else today)]
    for name, d in defs.items():
        seen = [compute(d, [series[x] for x in _window_days(series, end, rules.window)]).value for end in earlier]
        found = [v for v in seen if v is not None]
        if found:
            best[name] = max(found) if d.better == "higher" else min(found)
    return ChannelState(channel, today, window, values, best)


def holds(c: Condition, state: ChannelState, rules: PerformanceRules, setup: dict[str, Any]) -> bool:
    d = rules.measure(state.channel, c.measure)
    v = state.values.get(c.measure)
    if d is None or v is None or v.value is None:
        return False
    x = v.value
    if c.op == "above":
        return x > c.value
    if c.op == "below":
        return x < c.value
    if c.op in ("belowBenchmark", "aboveBenchmark", "atLeastBenchmark"):
        if d.benchmark is None:
            return False
        bound = d.benchmark * c.value
        return {"belowBenchmark": x < bound, "aboveBenchmark": x > bound, "atLeastBenchmark": x >= bound}[c.op]
    if c.op == "dropFromBest":
        best = state.best.get(c.measure)
        if best is None:
            return False
        return x <= best * (1 - c.value) if d.better == "higher" else x >= best * (1 + c.value)
    if c.op == "belowSetup":
        planned = setup.get(c.setup or "")
        try:
            return planned is not None and x < float(str(planned)) * c.value
        except ValueError:
            return False
    return False


def campaign_value(rules: PerformanceRules, name: str, all_series: dict[str, Daily], start: date,
                   end: date) -> float | None:
    """A campaign-wide measure over [start, end], summing every channel's counts."""
    d = rules.campaign[name]
    days = [values for series in all_series.values() for day, values in series.items() if start <= day <= end]
    return compute(d, days).value


def measure_between(rules: PerformanceRules, channel: str | None, name: str, all_series: dict[str, Daily],
                    start: date, end: date) -> float | None:
    return value_between(rules, channel, name, all_series, start, end).value


def value_between(rules: PerformanceRules, channel: str | None, name: str, all_series: dict[str, Daily],
                  start: date, end: date) -> Value:
    d = rules.measure(channel, name)
    if d is None:
        return Value(None, waiting=f"unknown measure {name}")
    if channel is None:
        days = [v for series in all_series.values() for day, v in series.items() if start <= day <= end]
    else:
        days = [v for day, v in all_series.get(channel, {}).items() if start <= day <= end]
    return compute(d, days)


def cost_floor(definition: MeasureDef | None, value: Value) -> float | None:
    """A cost per result with money spent and no result yet: at least the money spent (a lower bound)."""
    if definition is None or definition.unit != "USD" or not definition.num or not definition.den:
        return None
    spent, results = value.totals.get(definition.num, 0.0), value.totals.get(definition.den, 0.0)
    return spent if spent > 0 and results == 0 else None
