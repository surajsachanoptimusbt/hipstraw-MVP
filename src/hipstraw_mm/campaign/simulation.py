"""The live campaign simulation (Nov 2 meeting: take a campaign that is not running well and walk through how
Hipstraw reviews it every day, gives it direction, and shows what the change did).

A scenario (input/campaign/simulations/*.yaml) holds a launch file, a response model per channel (daily
volumes and rates, the issues holding a channel back, and what fixing each one does) and who decides. The
simulator makes only the numbers: each simulated day it writes that day's metrics export. Everything else is
Hipstraw's governed operations at the simulated date, exactly as from the CLI: ingest_metrics, choose and run
the daily Line, the reviewer's and the Sponsor's decisions, and record_change when the Sponsor applies an
accepted direction. Hipstraw never sees the response model; it diagnoses from the exported numbers alone, and
a change helps only if it addresses an issue the model holds. Every metric is labelled simulated
(constitution IX). The reviewer and the Sponsor accept everything here; in use, people decide.
"""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from hipstraw_mm.campaign.channels import load_channel_standards
from hipstraw_mm.campaign.intake import METRIC_COLUMNS, ingest_metrics, read_launch_file, submit_launch
from hipstraw_mm.campaign.live import record_change
from hipstraw_mm.campaign.models import Direction, LineRun, MoveExecution, ReviewRun
from hipstraw_mm.campaign.review import accept_review, review_finding, validate_review
from hipstraw_mm.campaign.runner import run_line
from hipstraw_mm.campaign.selection import choose_line
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.errors import UsageError


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fix(_M):
    rates: dict[str, float] = {}
    listSize: int | None = None
    pause: bool = False
    moveBudgetTo: str | None = None
    budgetLift: float = 0.0


class Issue(_M):
    """What holds a channel back from `fromDay` until a change addressing its cause is applied."""

    cause: str
    fromDay: int = 1
    rates: dict[str, float] = {}
    decay: dict[str, float] = {}  # rate -> share lost each day while the issue holds (creative fatigue)
    fix: Fix = Fix()


class ChannelModel(_M):
    kind: Literal["email", "ads"]
    sendDays: list[int] = []
    listSize: int = 0
    impressions: float = 0.0
    frequencyPerDay: float = 0.0
    rates: dict[str, float]
    issues: list[Issue] = []


class Decisions(_M):
    sponsor: str
    reviewer: str
    manager: str
    applyAfterDays: int = 1


class Scenario(_M):
    version: str
    name: str
    note: str
    launch: str
    days: int
    seed: int
    prelaunch: list[str] = []
    dailyLine: str = "L06"
    decisions: Decisions
    channels: dict[str, ChannelModel]


def load_scenario(path: Path) -> Scenario:
    try:
        return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except OSError as exc:
        raise UsageError(f"cannot read simulation scenario {path}: {exc}") from exc


# -- the response model ------------------------------------------------------------------------------------

EMAIL_METRICS = ("sent", "delivered", "clicks", "complaints", "unsubscribes", "applications",
                 "qualified_applications")
AD_METRICS = ("impressions", "clicks", "spend", "applications", "qualified_applications", "frequency")
UNITS = {"spend": "USD", "frequency": "x"}


@dataclass
class _ChannelState:
    list_size: int
    budget: float = 1.0
    paused: bool = False
    frequency: float = 0.0
    fixed: dict[str, int] = field(default_factory=dict)  # cause -> day fixed
    carry: dict[str, float] = field(default_factory=dict)


class Market:
    """The simulated market's response, day by day. Deterministic for a seed."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.rng = random.Random(scenario.seed)
        self.state = {c: _ChannelState(list_size=m.listSize) for c, m in scenario.channels.items()}

    def apply(self, channel: str, cause: str, day: int) -> bool:
        """The Sponsor applied a change for `cause` on `channel`: it helps only if that issue holds there."""
        model, st = self.scenario.channels.get(channel), self.state.get(channel)
        if model is None or st is None:
            return False
        issue = next((i for i in model.issues if i.cause == cause and cause not in st.fixed and i.fromDay <= day),
                     None)
        if issue is None:
            return False
        st.fixed[cause] = day
        if issue.fix.listSize is not None:
            st.list_size = issue.fix.listSize
        if issue.fix.pause:
            st.paused = True
        if issue.fix.moveBudgetTo and issue.fix.moveBudgetTo in self.state:
            self.state[issue.fix.moveBudgetTo].budget *= 1 + issue.fix.budgetLift
        return True

    def _rates(self, channel: str, day: int) -> dict[str, float]:
        model, st = self.scenario.channels[channel], self.state[channel]
        rates = dict(model.rates)
        for issue in model.issues:
            if issue.cause in st.fixed:
                rates.update(issue.fix.rates)
            elif issue.fromDay <= day:
                rates.update(issue.rates)
                for rate, per_day in issue.decay.items():
                    rates[rate] *= (1 - per_day) ** (day - issue.fromDay)
        return rates

    def _count(self, st: _ChannelState, key: str, expected: float) -> int:
        """Whole counts that add up to the expectation over the days (a fractional remainder carries)."""
        total = max(expected, 0.0) * self.rng.uniform(0.9, 1.1) + st.carry.get(key, 0.0)
        n = math.floor(total)
        st.carry[key] = total - n
        return n

    def day(self, day: int) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for channel, model in self.scenario.channels.items():
            st = self.state[channel]
            if st.paused:
                continue
            r = self._rates(channel, day)
            if model.kind == "email":
                if day not in model.sendDays:
                    continue
                delivered = self._count(st, "delivered", st.list_size * r["delivered"])
                clicks = self._count(st, "clicks", delivered * r["click"])
                applications = self._count(st, "applications", clicks * r["apply"])
                out[channel] = {
                    "sent": st.list_size, "delivered": delivered, "clicks": clicks,
                    "complaints": self._count(st, "complaints", delivered * r["complaint"]),
                    "unsubscribes": self._count(st, "unsubscribes", delivered * r["unsubscribe"]),
                    "applications": applications,
                    "qualified_applications": self._count(st, "qualified", applications * r["qualified"]),
                }
            else:
                impressions = self._count(st, "impressions", model.impressions * st.budget)
                clicks = self._count(st, "clicks", impressions * r["ctr"])
                applications = self._count(st, "applications", clicks * r["apply"])
                st.frequency += model.frequencyPerDay * st.budget
                out[channel] = {
                    "impressions": impressions, "clicks": clicks,
                    "spend": round(clicks * r["cpc"] * self.rng.uniform(0.95, 1.05), 2),
                    "applications": applications,
                    "qualified_applications": self._count(st, "qualified", applications * r["qualified"]),
                    "frequency": round(st.frequency, 2),
                }
        return out


def write_export(path: Path, on: date, numbers: dict[str, dict[str, float]]) -> None:
    """One day's metrics export, in the launch file's metrics format, every row marked simulated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    captured = datetime.combine(on + timedelta(days=1), time(7), tzinfo=timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(METRIC_COLUMNS)
        for channel, values in numbers.items():
            for name, value in values.items():
                w.writerow([f"{channel}.{name}", f"{value:g}", UNITS.get(name, ""), on.isoformat(), on.isoformat(),
                            "", f"SIMULATED {name.replace('_', ' ')} for {channel}, one day", captured])


# -- the walk-through --------------------------------------------------------------------------------------


@dataclass
class Event:
    day: int
    on: str
    kind: str  # submitted | prelaunch | metrics | review | direction | applied | delta | gap | blocker
    text: str
    channel: str | None = None


@dataclass
class SimulationResult:
    launchId: str
    scenario: str
    events: list[Event]


def _at(day_zero: date, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day_zero + timedelta(days=day - 1), time(hour, minute), tzinfo=timezone.utc)


def _decide(store: CampaignStore, config_dir: Path, review_id: str, d: Decisions, now: datetime) -> ReviewRun:
    review = store.get(ReviewRun, review_id)
    assert review is not None
    for f in review.findings:
        if f.reviewState == "pending":
            review_finding(store, config_dir, review_id, f.findingId, action="accept",
                           reason="checked against the metrics", by=d.reviewer, role="reviewer", now=now)
    validate_review(store, config_dir, review_id, by=d.reviewer, role="reviewer", now=now)
    return accept_review(store, config_dir, review_id, by=d.sponsor, role="sponsor", now=now)


def _run_line(store: CampaignStore, config_dir: Path, launch_id: str, line: str, reason: str, d: Decisions,
              now: datetime) -> tuple[LineRun, ReviewRun]:
    run = choose_line(store, config_dir, launch_id, line, reason=reason, by=d.manager, role="campaign_manager",
                      now=now)
    run_line(store, config_dir, run.lineRunId, by=d.manager, role="campaign_manager", now=now)
    finished = store.get(LineRun, run.lineRunId)
    assert finished is not None and finished.reviewId is not None
    return finished, _decide(store, config_dir, finished.reviewId, d, now + timedelta(minutes=30))


def run_simulation(store: CampaignStore, config_dir: Path, scenario_path: Path, *, exports_dir: Path,
                   on_event: Callable[[Event], Any] = lambda e: None) -> SimulationResult:
    sc = load_scenario(scenario_path)
    d = sc.decisions
    launch_file = Path(sc.launch)
    day_zero = read_launch_file(launch_file).dayZero
    names = load_channel_standards(config_dir)
    events: list[Event] = []

    def emit(day: int, kind: str, text: str, channel: str | None = None) -> None:
        event = Event(day, (day_zero + timedelta(days=day - 1)).isoformat(), kind, text, channel)
        events.append(event)
        on_event(event)

    launch_id = submit_launch(store, config_dir, launch_file, by=d.sponsor, role="sponsor",
                              now=_at(day_zero, -2, 9)).launchId
    emit(-2, "submitted", f"{sc.name}: launch {launch_id} submitted. {sc.note}")
    for line in sc.prelaunch:
        run, review = _run_line(store, config_dir, launch_id, line, "before Day Zero", d, _at(day_zero, -2, 10))
        emit(-2, "prelaunch", f"{line} before Day Zero; {review.reviewId} accepted: Position "
                              f"v{review.committedPositionVersion}")

    market = Market(sc)
    pending: list[tuple[int, str, Direction]] = []  # (day to apply, channel, direction)
    scheduled: set[str] = set()
    for day in range(1, sc.days + 1):
        on = day_zero + timedelta(days=day - 1)
        for due, channel, direction in [p for p in pending if p[0] == day]:
            pending.remove((due, channel, direction))
            helped = market.apply(channel, direction.cause, day)
            record_change(store, config_dir, launch_id, direction.hypothesisItemId, applied_on=on,
                          what=direction.change, by=d.sponsor, role="sponsor", now=_at(day_zero, day, 8))
            emit(day, "applied", f"The Sponsor applied: {direction.change}", channel)
            if not helped:
                emit(day, "applied", "(simulation note: this change does not address anything holding this channel "
                                     "back in the scenario; watch the Delta)", channel)

        numbers = market.day(day)
        export = exports_dir / f"{launch_id}_day{day:02d}.csv"
        write_export(export, on, numbers)
        ingest_metrics(store, config_dir, launch_id, export, by=d.manager, role="campaign_manager",
                       now=_at(day_zero, day, 21), simulated=True)
        shown = "; ".join(f"{names.name(c)} " + ", ".join(f"{k} {v:g}" for k, v in vals.items()
                                                           if k in ("delivered", "impressions", "clicks",
                                                                    "applications", "qualified_applications"))
                          for c, vals in numbers.items())
        emit(day, "metrics", f"Day {day} export: {shown or 'nothing sent or shown'}")

        run, review = _run_line(store, config_dir, launch_id, sc.dailyLine, f"daily review, day {day}", d,
                                _at(day_zero, day, 21, 30))
        executions = [e for e in store.list_for_launch(MoveExecution, launch_id) if e.lineRunId == run.lineRunId]
        notes = "; ".join(f"{e.moveId} {e.note}" for e in executions if e.note)
        emit(day, "review", f"{sc.dailyLine} {run.lineRunId}: {notes}. {review.reviewId} accepted: Position "
                            f"v{review.committedPositionVersion}")
        for f in review.findings:
            if f.kind == "gap" and f.text.startswith("Repertoire gap"):
                emit(day, "gap", f.text, f.channel)
            elif f.kind == "blocker" and f.sourceMove is not None:  # new or cleared today, not still open
                emit(day, "blocker", f.text, f.channel)
            elif f.kind == "delta" and f.text.startswith("Delta"):
                emit(day, "delta", f.text, f.channel)

        head = store.head_position(launch_id)
        directions = {x.hypothesisItemId: x for x in store.list_for_launch(Direction, launch_id)}
        for item in head.items if head else []:
            found = directions.get(item.itemId)
            if found is None or item.itemId in scheduled or item.state not in ("proposed", "planned"):
                continue
            scheduled.add(item.itemId)
            pending.append((day + d.applyAfterDays, item.channel or "", found))
            emit(day, "direction", f"{found.finding}. Direction: {found.change} (accepted; the Sponsor applies it on "
                                   f"day {day + d.applyAfterDays})", item.channel)
    return SimulationResult(launchId=launch_id, scenario=sc.name, events=events)
