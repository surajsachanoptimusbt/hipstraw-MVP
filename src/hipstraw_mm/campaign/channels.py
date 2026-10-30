"""Channel standards (config/campaign/channels.yaml): who each channel reaches, and the checks the platforms and
the law set, and practitioners apply, before money is spent on it (Oct 30 meeting: every campaign starts from
its channels, and each channel serves a different audience).

Each check is a named function here; the YAML chooses and parameterizes them, sets the level (`must` for a
platform rule or the law, `should` for established practice) and names the source. A check reads only what the
Sponsor stated, so its result is `met`, `not_met` or `not_stated`, never a guess. Nothing here calls a model (E0).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import yaml
from pydantic import BaseModel, ConfigDict

from hipstraw_mm.campaign.models import Asset, AssetKind, ChannelPlan, Mandate
from hipstraw_mm.errors import ConfigError

Level = Literal["must", "should"]
Status = Literal["met", "not_met", "not_stated"]


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reach(_Config):
    how: str
    fitsWell: str
    fitsPoorly: str


class MustWhen(_Config):
    """A `should` that becomes a `must` past a size, e.g. DMARC for senders of 5,000 or more emails a day."""

    field: str
    atLeast: float


class ChannelCheck(_Config):
    id: str
    text: str
    level: Level
    check: str
    args: dict[str, Any] = {}
    source: str
    markets: list[str] = []  # empty: every market
    mustWhen: MustWhen | None = None


class ChannelStandard(_Config):
    name: str
    assetKind: AssetKind
    reach: Reach
    format: str
    setup: dict[str, str]
    assetFields: dict[str, str]
    checks: list[ChannelCheck]


class ChannelStandards(_Config):
    version: str
    status: str | None = None
    channels: dict[str, ChannelStandard]

    def name(self, channel: str) -> str:
        known = self.channels.get(channel)
        return known.name if known else channel.replace("_", " ")


@dataclass
class CheckResult:
    channel: str
    checkId: str
    text: str
    level: Level
    status: Status
    detail: str
    source: str

    @property
    def key(self) -> str:
        """Stable across runs, so a later run clears the same blocker or unknown."""
        return f"{self.checkId}:{self.channel}"


# -- checks: (plan, the channel's assets, args) -> (status, detail) ---------------------------------------

Result = tuple[Status, str]


def _stated(value: Any) -> bool:
    return value not in (None, "", [], {})


def _as_list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _setup_present(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    missing = [f for f in args["fields"] if not _stated(plan.setup.get(f))]
    return ("not_stated", f"not stated: {', '.join(missing)}") if missing else ("met", "stated")


def _setup_any(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    found = [f for f in args["fields"] if _stated(plan.setup.get(f))]
    return ("met", f"stated: {', '.join(found)}") if found else ("not_stated", f"none of {', '.join(args['fields'])}")


def _setup_includes(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    value = plan.setup.get(args["field"])
    if not _stated(value):
        return "not_stated", f"{args['field']} not stated"
    have = {v.casefold() for v in _as_list(value)}
    missing = [v for v in args["values"] if v.casefold() not in have]
    stated = ", ".join(_as_list(value))
    if args.get("any"):  # one of the values is enough
        return ("not_met", f"none of {', '.join(args['values'])} (stated: {stated})") \
            if len(missing) == len(args["values"]) else ("met", stated)
    return ("not_met", f"missing {', '.join(missing)} (stated: {stated})") if missing else ("met", stated)


def _setup_not_in(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    value = plan.setup.get(args["field"])
    if not _stated(value):
        return "not_stated", f"{args['field']} not stated"
    return ("not_met", f"{args['field']} is {value}") if str(value) in args["values"] else ("met", str(value))


def _setup_equals(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    value = plan.setup.get(args["field"])
    if not _stated(value):
        return "not_stated", f"{args['field']} not stated"
    return ("met", str(value)) if str(value) == str(args["value"]) else ("not_met", f"{args['field']} is {value}")


def _setup_at_least(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    value = plan.setup.get(args["field"])
    if not _stated(value):
        return "not_stated", f"{args['field']} not stated"
    try:
        number = float(str(value))
    except ValueError:
        return "not_met", f"{args['field']} is {value!r}, not a number"
    minimum = args["min"]
    return ("met", f"{number:g}") if number >= minimum else ("not_met", f"{number:g}, below {minimum:g}")


def _field_values(assets: list[Asset], field: str) -> list[tuple[Asset, str | None]]:
    return [(a, a.fields.get(field) or None) for a in assets]


def _asset_field_present(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    if not assets:
        return "not_stated", "no asset for this channel"
    missing = [a.assetId for a, v in _field_values(assets, args["field"]) if not v]
    return ("not_met", f"{args['field']} missing in {', '.join(missing)}") if missing else ("met", "present")


def _asset_field_max(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    values = [(a, v) for a, v in _field_values(assets, args["field"]) if v]
    if not values:
        return "not_stated", f"no {args['field']} on file"
    over = [f"{len(v)} characters in {a.assetId}" for a, v in values if len(v) > args["max"]]
    return ("not_met", f"{'; '.join(over)} (limit {args['max']})") if over \
        else ("met", f"{max(len(v) for _, v in values)} characters")


def _asset_field_contains(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    values = [(a, v) for a, v in _field_values(assets, args["field"]) if v]
    if not values:
        return "not_stated", f"no {args['field']} on file"
    lacking = [a.assetId for a, v in values if not any(t.casefold() in v.casefold() for t in args["any"])]
    return ("not_met", f"no {' / '.join(args['any'])} in the {args['field']} of {', '.join(lacking)}") if lacking \
        else ("met", "present")


def _asset_field_has_setup(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    expected = plan.setup.get(args["setupField"])
    values = [(a, v) for a, v in _field_values(assets, args["field"]) if v]
    if not _stated(expected):
        return "not_stated", f"{args['setupField']} not stated"
    if not values:
        return "not_met", f"no {args['field']} on file"
    want = " ".join(str(expected).split()).casefold()
    lacking = [a.assetId for a, v in values if want not in " ".join(v.split()).casefold()]
    return ("not_met", f"the {args['field']} of {', '.join(lacking)} does not carry it") if lacking \
        else ("met", "present")


def _asset_url_tagged(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    values = [(a, v) for a, v in _field_values(assets, args["field"]) if v]
    if not values:
        return "not_stated", f"no {args['field']} on file"
    untagged = []
    for a, url in values:
        params = parse_qs(urlparse(url).query)
        missing = [p for p in args["params"] if p not in params]
        if missing:
            untagged.append(f"{a.assetId} lacks {', '.join(missing)}")
    return ("not_met", "; ".join(untagged)) if untagged else ("met", "tagged")


def _measure_not(plan: ChannelPlan, assets: list[Asset], args: dict[str, Any]) -> Result:
    measure = plan.successMeasure
    if not measure:
        return "not_stated", "no success measure stated for this channel"
    hits = [t for t in args["terms"] if t.casefold() in measure.casefold()]
    return ("not_met", f"measured by {measure!r}") if hits else ("met", measure)


CHECKS: dict[str, Callable[[ChannelPlan, list[Asset], dict[str, Any]], Result]] = {
    "setup_present": _setup_present,
    "setup_any": _setup_any,
    "setup_includes": _setup_includes,
    "setup_not_in": _setup_not_in,
    "setup_equals": _setup_equals,
    "setup_at_least": _setup_at_least,
    "asset_field_present": _asset_field_present,
    "asset_field_max": _asset_field_max,
    "asset_field_contains": _asset_field_contains,
    "asset_field_has_setup": _asset_field_has_setup,
    "asset_url_tagged": _asset_url_tagged,
    "measure_not": _measure_not,
}


def load_channel_standards(config_dir: Path = Path("config")) -> ChannelStandards:
    path = config_dir / "campaign" / "channels.yaml"
    with open(path, encoding="utf-8") as f:
        standards = ChannelStandards.model_validate(yaml.safe_load(f))
    unknown = sorted({c.check for s in standards.channels.values() for c in s.checks if c.check not in CHECKS})
    if unknown:
        raise ConfigError(f"{path}: unknown checks {', '.join(unknown)}")
    ids = [c.id for s in standards.channels.values() for c in s.checks]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ConfigError(f"{path}: check IDs used twice: {', '.join(repeated)}")
    return standards


def channel_plans(mandate: Mandate) -> list[ChannelPlan]:
    """The mandate's channel plans, in its channel order; a channel named only in the strategy gets an empty plan."""
    plans = {p.channel: p for p in mandate.channelPlans}
    return [plans.get(c) or ChannelPlan(channel=c) for c in mandate.strategy.channels]


def _level(check: ChannelCheck, plan: ChannelPlan) -> Level:
    if check.mustWhen is not None:
        value = plan.setup.get(check.mustWhen.field)
        try:
            if value is not None and float(value) >= check.mustWhen.atLeast:
                return "must"
        except (TypeError, ValueError):
            pass
    return check.level


def check_channel(mandate: Mandate, plan: ChannelPlan, standard: ChannelStandard) -> list[CheckResult]:
    assets = [a for a in mandate.assets if a.channel == plan.channel and a.kind == standard.assetKind]
    out = []
    for check in standard.checks:
        if check.markets and mandate.market not in check.markets:
            continue
        status, detail = CHECKS[check.check](plan, assets, check.args)
        out.append(CheckResult(channel=plan.channel, checkId=check.id, text=check.text, level=_level(check, plan),
                               status=status, detail=detail, source=check.source))
    return out
