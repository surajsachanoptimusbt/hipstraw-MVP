"""Launch intake (US1, FR-005 to FR-014): a launch file becomes a versioned mandate (C1), immutable evidence
records (C2) and a proposed Campaign Position v1 (C3).

Everything the customer tells us is `reported`, never more: intake records what was said and where, and
leaves verification to the Moves. A required input that is missing becomes an explicit unknown, not a
default (constitution VIII).
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError, model_validator

from hipstraw_mm.campaign.audit import record_audit
from hipstraw_mm.campaign.channels import ChannelStandards, channel_plans, load_channel_standards
from hipstraw_mm.campaign.config import CampaignSettings, load_roles, load_settings
from hipstraw_mm.campaign.gate import authorize
from hipstraw_mm.campaign.models import (
    Area,
    Asset,
    AssetKind,
    Audience,
    Budget,
    ChannelPlan,
    EvidenceRecord,
    Launch,
    Mandate,
    MetricFields,
    MetricsFile,
    Objective,
    PositionItem,
    PositionSnapshot,
    Product,
    Provenance,
    Record,
    Strategy,
    content_hash,
)
from hipstraw_mm.campaign.repertoire import load_repertoire
from hipstraw_mm.campaign.stamp import mechanism_stamp
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.errors import PreconditionError, UsageError

ITEM_PREFIX = {"claim": "C", "assumption": "A", "blocker": "B", "unknown": "U", "hypothesis": "H", "observation": "O"}
ASSET_LABEL = {
    "ad_copy": "Ad copy", "email_copy": "Email copy", "creative": "Creative", "brief": "Brief", "other": "Asset",
}
# How a structured asset's parts read as text, so a quote can cite "Subject: ..." word for word.
FIELD_LABEL = {
    "from": "From", "subject": "Subject", "preheader": "Preheader", "body": "Body", "cta": "Call to action",
    "ctaUrl": "Link", "footer": "Footer", "introText": "Intro text", "headline": "Headline", "image": "Image",
    "visual": "Visual", "caption": "Caption", "destination": "Destination",
}
METRIC_COLUMNS = ("metric", "value", "unit", "window_start", "window_end", "denominator", "definition", "captured_at")
# Without these a metric cannot be checked for identity and freshness, so the row stays unverified.
METRIC_REQUIRED = ("definition", "window_start", "window_end", "captured_at")

# Inputs the tests need; when one is missing it becomes an explicit unknown (FR-010).
RequiredCheck = Callable[[Mandate], bool]
REQUIRED_INPUTS: tuple[tuple[str, Area, RequiredCheck], ...] = (
    ("Landing page not provided", "readiness", lambda m: any(a.kind == "landing_page" for a in m.assets)),
    ("Success measure for the objective not stated", "strategy", lambda m: bool(m.objective.successMeasure)),
    ("Approver (Sponsor) not named", "readiness", lambda m: bool(m.approver)),
    ("Tracking plan not stated", "readiness", lambda m: bool(m.trackingPlan)),
    ("Campaign budget not stated", "readiness", lambda m: m.strategy.budget is not None),
)


class AssetIn(Record):
    kind: AssetKind
    channel: str | None = None
    url: str | None = None
    text: str | None = None
    fields: dict[str, str] = {}
    readyDate: date | None = None


class ChannelIn(Record):
    """One channel of the campaign with its own audience, setup and assets (contracts/config.md "Launch file")."""

    channel: str
    audience: str | None = None
    budget: Budget | None = None
    successMeasure: str | None = None
    setup: dict[str, Any] = {}
    assets: list[AssetIn] = []


class LaunchFile(Record):
    """The launch submission (contracts/config.md "Launch file"). Channels are named first (Oct 30 meeting):
    either as `channels`, each with its audience, setup and assets, or as the older `strategy.channels` list."""

    product: Product
    audience: Audience
    market: str
    dayZero: date
    objective: Objective
    strategy: Strategy
    channels: list[ChannelIn] = []
    authorizedChannels: list[str] = []
    approver: str | None = None
    trackingPlan: str | None = None
    assets: list[AssetIn] = []
    metricsFile: str | None = None

    @model_validator(mode="after")
    def _channels_named(self) -> LaunchFile:
        planned = [c.channel for c in self.channels]
        if len(set(planned)) < len(planned):
            raise ValueError("a channel is listed twice under channels")
        if planned and self.strategy.channels and set(planned) != set(self.strategy.channels):
            raise ValueError("strategy.channels and channels name different channels; give the channels once")
        if planned and not self.strategy.channels:
            self.strategy.channels = planned
        if not self.strategy.channels:
            raise ValueError("name at least one channel (channels, or strategy.channels)")
        return self


@dataclass
class MetricRow:
    values: dict[str, str]
    missing: list[str]


@dataclass
class SubmitResult:
    launchId: str
    mandateVersion: int
    evidence: int
    positionVersion: int
    items: dict[str, int]


@dataclass
class AmendResult:
    launchId: str
    mandateVersion: int
    evidence: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_launch_file(path: Path) -> LaunchFile:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return LaunchFile.model_validate(raw)
    except OSError as exc:
        raise UsageError(f"cannot read launch file {path}: {exc}") from exc
    except (yaml.YAMLError, ValidationError) as exc:
        raise UsageError(f"launch file {path} is not valid: {exc}") from exc


def parse_metrics_csv(path: Path) -> list[MetricRow]:
    try:
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing_columns = [c for c in METRIC_COLUMNS if c not in (reader.fieldnames or [])]
            if missing_columns:
                raise UsageError(f"metrics file {path} lacks columns: {', '.join(missing_columns)}")
            rows = [{c: (r.get(c) or "").strip() for c in METRIC_COLUMNS} for r in reader]
    except OSError as exc:
        raise UsageError(f"cannot read metrics file {path}: {exc}") from exc
    out = []
    for n, row in enumerate(rows, start=1):
        try:
            float(row["value"])
        except ValueError as exc:
            raise UsageError(f"metrics file {path} row {n}: value {row['value']!r} is not a number") from exc
        out.append(MetricRow(values=row, missing=[c for c in METRIC_REQUIRED if not row[c]]))
    return out


def _check_market(market: str, settings: CampaignSettings) -> None:
    if market not in settings.launchMarkets:
        raise UsageError(
            f"market {market!r} is not a launch market; allowed: {', '.join(settings.launchMarkets)}"
        )


def _new_launch_id(store: CampaignStore, now: datetime) -> str:
    base = f"lch_{now:%Y%m%dT%H%M%S}"
    candidate, n = base, 1
    while store.get(Launch, candidate) is not None:
        n += 1
        candidate = f"{base}_{n}"
    return candidate


def _build_mandate(lf: LaunchFile, launch_id: str, version: int, by: str, at: str,
                   metrics: MetricsFile | None) -> Mandate:
    assets = list(lf.assets) + [a.model_copy(update={"channel": c.channel}) for c in lf.channels for a in c.assets]
    return Mandate(
        launchId=launch_id, version=version, createdAt=at, createdBy=by, product=lf.product,
        audience=lf.audience, market=lf.market, dayZero=lf.dayZero, objective=lf.objective,
        strategy=lf.strategy, authorizedChannels=lf.authorizedChannels, approver=lf.approver,
        trackingPlan=lf.trackingPlan, metricsFile=metrics,
        assets=[Asset(assetId=f"A{n}", **a.model_dump()) for n, a in enumerate(assets, start=1)],
        channelPlans=[ChannelPlan(**c.model_dump(exclude={"assets"})) for c in lf.channels],
    )


def _brief(mandate: Mandate) -> dict[str, Any]:
    """The submitted strategy as one evidence record, so every claim drawn from it can cite it."""
    brief = mandate.model_dump(
        mode="json",
        include={"product", "audience", "market", "dayZero", "objective", "strategy", "authorizedChannels",
                 "approver", "trackingPlan"},
    )
    if mandate.channelPlans:
        brief["channelPlans"] = [p.model_dump(mode="json", exclude_defaults=True) for p in mandate.channelPlans]
    return brief


def asset_content(asset: Asset) -> str:
    if asset.fields:
        parts = "\n".join(f"{FIELD_LABEL.get(k, k)}: {v}" for k, v in asset.fields.items())
        return f"{parts}\n{asset.text}" if asset.text else parts
    return asset.text or asset.url or ""


def asset_claim_text(asset: Asset) -> str:
    """How an asset reads as a claim in the Position (intake and M01 share it)."""
    if asset.kind == "landing_page":
        return f"Landing page provided: {asset.url or '(no address)'}"
    text = f"{ASSET_LABEL[asset.kind]} provided" + (f" for {asset.channel}" if asset.channel else "")
    return text + (f", ready {asset.readyDate.isoformat()}" if asset.readyDate else "")


def _asset_signature(asset: Asset) -> tuple[Any, ...]:
    return (asset.kind, asset.channel, asset.url, asset.text, tuple(sorted(asset.fields.items())), asset.readyDate)


class _EvidenceWriter:
    def __init__(self, store: CampaignStore, launch_id: str, by: str, at: str) -> None:
        self.store, self.launch_id, self.by, self.at = store, launch_id, by, at
        self.next_n = len(store.list_for_launch(EvidenceRecord, launch_id)) + 1
        self.written: list[EvidenceRecord] = []

    def add(self, **fields: Any) -> EvidenceRecord:
        content = fields["content"]
        record = EvidenceRecord(
            evidenceId=f"ev_{self.launch_id}_{self.next_n}", launchId=self.launch_id, capturedAt=self.at,
            provenance=Provenance(by=self.by, method="launch submission"), contentHash=content_hash(content),
            **fields,
        )
        self.store.insert(record)
        self.next_n += 1
        self.written.append(record)
        return record


def _record_mandate_evidence(
    writer: _EvidenceWriter, mandate: Mandate, previous: Mandate | None, previous_brief_hash: str | None,
    metrics_rows: list[MetricRow] | None,
) -> tuple[EvidenceRecord | None, dict[str, EvidenceRecord]]:
    """Evidence for what is new in this mandate version: the brief, assets and metric rows."""
    v = mandate.version
    brief: EvidenceRecord | None = None
    brief_content = _brief(mandate)
    if content_hash(brief_content) != previous_brief_hash:
        brief = writer.add(kind="asset", source="customer_submission", sourceRef=f"mandate:v{v}#brief",
                           verificationState="reported", uncertainty="customer's own statement",
                           content=brief_content, accessClass="D2")
    known = {_asset_signature(a) for a in previous.assets} if previous else set()
    assets: dict[str, EvidenceRecord] = {}
    for asset in mandate.assets:
        if _asset_signature(asset) in known:
            continue
        assets[asset.assetId] = writer.add(
            kind="asset", source="customer_submission", sourceRef=f"mandate:v{v}#asset:{asset.assetId}",
            verificationState="reported", uncertainty="as supplied; not yet checked against the live channel",
            content=asset_content(asset), accessClass="D2",
        )
    for n, row in enumerate(metrics_rows or [], start=1):
        r = row.values
        assert mandate.metricsFile is not None
        writer.add(
            kind="metric", source="metrics_export", sourceRef=f"metrics:{mandate.metricsFile.sha256[:12]}#row{n}",
            effectiveAt=r["window_end"] or None,
            verificationState="unverified" if row.missing else "reported",
            uncertainty=f"missing: {', '.join(row.missing)}" if row.missing else "customer export; not yet verified",
            content=r, accessClass="D3",
            metric=MetricFields(metric=r["metric"], value=float(r["value"]), unit=r["unit"] or None,
                                windowStart=r["window_start"] or None, windowEnd=r["window_end"] or None,
                                denominator=r["denominator"] or None, definition=r["definition"] or None),
        )
    return brief, assets


def _initial_items(mandate: Mandate, brief: EvidenceRecord, assets: dict[str, EvidenceRecord],
                   settings: CampaignSettings, standards: ChannelStandards) -> list[PositionItem]:
    counters: Counter[str] = Counter()

    def item(kind: str, area: Area, text: str, state: str, refs: list[str], core: bool = False,
             channel: str | None = None, key: str | None = None) -> PositionItem:
        counters[kind] += 1
        return PositionItem(itemId=f"{ITEM_PREFIX[kind]}{counters[kind]:02d}", kind=kind,  # type: ignore[arg-type]
                            area=area, text=text, state=state, core=core, evidenceRefs=refs, setBy="intake",
                            channel=channel, key=key)

    b = [brief.evidenceId]
    s, o = mandate.strategy, mandate.objective
    items = [
        item("claim", "strategy", f"Product: {mandate.product.name}. {mandate.product.description}", "reported", b),
        item("claim", "strategy", f"Audience: {mandate.audience.description}", "reported", b),
        item("claim", "strategy", f"Objective: {o.statement}"
             + (f" (measured by: {o.successMeasure})" if o.successMeasure else ""), "reported", b),
        item("claim", "strategy", f"Message: {s.message}", "reported", b),
    ]
    if s.offer:
        items.append(item("claim", "strategy", f"Offer: {s.offer}", "reported", b))
    items.append(item("claim", "strategy", f"Channels: {', '.join(standards.name(c) for c in s.channels)}",
                      "reported", b))
    for plan in mandate.channelPlans:
        if plan.audience:
            items.append(item("claim", "strategy", f"{standards.name(plan.channel)} reaches: {plan.audience}",
                              "reported", b, channel=plan.channel))
    items.append(item("claim", "readiness", f"Day Zero: {mandate.dayZero.isoformat()}", "reported", b))
    if s.budget:
        items.append(item("claim", "readiness", f"Budget: {s.budget.amount:g} {s.budget.currency}", "reported", b))
    if mandate.approver:
        items.append(item("claim", "readiness", f"Approver: {mandate.approver}", "reported", b))
    if mandate.trackingPlan:
        items.append(item("claim", "readiness", f"Tracking plan: {mandate.trackingPlan}", "reported", b))
    if mandate.authorizedChannels:
        items.append(item("claim", "readiness", f"Authorized test channels: {', '.join(mandate.authorizedChannels)}",
                          "reported", b))
    for asset in mandate.assets:
        ev = assets.get(asset.assetId)
        if ev is not None:
            items.append(item("claim", "readiness", asset_claim_text(asset), "reported", [ev.evidenceId],
                              channel=asset.channel))

    core = settings.coreAssumptions
    for text in core.general:
        items.append(item("assumption", "strategy", text, "open", b, core=True))
    for channel in s.channels:
        items.append(item("assumption", "strategy", core.perChannel.format(channel=standards.name(channel)), "open",
                          b, core=True, channel=channel))

    for text, area, present in REQUIRED_INPUTS:
        if not present(mandate):
            items.append(item("unknown", area, text, "open", b))
    # A campaign starts from its channels (Oct 30 meeting): a channel with no platform rules on file, or with no
    # stated audience, cannot be judged for whom it reaches.
    for plan in channel_plans(mandate):
        if plan.channel not in standards.channels:
            items.append(item("unknown", "strategy", f"Channel {plan.channel!r} is not a specific platform with "
                              f"rules on file; name it ({', '.join(standards.channels)})", "open", b,
                              channel=plan.channel, key=f"CHANNEL:{plan.channel}"))
        elif not plan.audience:
            items.append(item("unknown", "strategy", f"Who the {standards.name(plan.channel)} channel reaches is "
                              "not stated (the list, or the targeting)", "open", b, channel=plan.channel,
                              key=f"AUDIENCE:{plan.channel}"))
    return items


def submit_launch(store: CampaignStore, config_dir: Path, path: Path, *, by: str, role: str,
                  now: datetime) -> SubmitResult:
    at = now.isoformat()
    settings = load_settings(config_dir)
    authorize(store, load_roles(config_dir), launch_id=None, actor=by, role=role, action="submit_launch", at=at)
    lf = read_launch_file(path)
    _check_market(lf.market, settings)
    metrics_path = (path.parent / lf.metricsFile) if lf.metricsFile else None
    metrics_rows = parse_metrics_csv(metrics_path) if metrics_path else None
    repertoire = load_repertoire(config_dir)
    standards = load_channel_standards(config_dir)

    launch_id = _new_launch_id(store, now)
    store.insert(Launch(launchId=launch_id, owner=lf.approver or by, market=lf.market,
                        productName=lf.product.name, createdAt=at))
    tracer = campaign_tracer(store, config_dir, launch_id)
    writer = _EvidenceWriter(store, launch_id, by, at)

    with tracer.step("campaign_manager", "launch_desk", "open_launch", right="open_launch") as step:
        step.set_inputs({"file": str(path), "sha256": _sha256(path), "market": lf.market, "by": by, "role": role})
        metrics = MetricsFile(path=str(metrics_path), sha256=_sha256(metrics_path)) if metrics_path else None
        mandate = _build_mandate(lf, launch_id, 1, by, at, metrics)
        store.insert(mandate)
        brief, assets = _record_mandate_evidence(writer, mandate, None, None, metrics_rows)
        step.set_outputs({"launchId": launch_id, "mandateVersion": 1, "evidence": len(writer.written),
                          "evidenceIds": [e.evidenceId for e in writer.written]})
        step.set_decision("opened", "launch file valid and market allowed")

    assert brief is not None
    with tracer.step("campaign_manager", "launch_desk", "propose_position", right="propose_position") as step:
        step.set_inputs({"mandateVersion": 1, "evidenceIds": [e.evidenceId for e in writer.written]})
        items = _initial_items(mandate, brief, assets, settings, standards)
        position = PositionSnapshot(
            positionId=f"pos_{launch_id}_v1", launchId=launch_id, version=1, state="proposed", evidenceCutoff=at,
            createdAt=at, origin="intake", items=items,
            mechanismStamp=mechanism_stamp(repertoire_version=repertoire.version),
        )
        store.insert(position)
        counts: dict[str, int] = dict(Counter(str(i.kind) for i in items))
        step.set_outputs({"positionVersion": 1, "items": counts})
        step.set_decision("proposed", "the intake proposal becomes accepted only through a Review")

    record_audit(store, launch_id=launch_id, at=at, actor=by, role=role, action="submit_launch",
                 right="submit_launch", before=None, after=position.positionId)
    return SubmitResult(launchId=launch_id, mandateVersion=1, evidence=len(writer.written), positionVersion=1,
                        items=counts)


def amend_mandate(store: CampaignStore, config_dir: Path, launch_id: str, path: Path, *, by: str, role: str,
                  now: datetime) -> AmendResult:
    """A new, complete mandate version. Earlier versions and the Position are unchanged; only new or
    changed inputs become evidence, for the next Line to examine."""
    at = now.isoformat()
    settings = load_settings(config_dir)
    authorize(store, load_roles(config_dir), launch_id=launch_id, actor=by, role=role, action="amend_mandate", at=at)
    launch = store.get(Launch, launch_id)
    previous = store.latest_mandate(launch_id)
    if launch is None or previous is None:
        raise PreconditionError(f"launch {launch_id} not found")
    lf = read_launch_file(path)
    _check_market(lf.market, settings)
    if lf.market != launch.market:
        raise UsageError(f"launch {launch_id} is for market {launch.market}; open a new launch for {lf.market}")
    metrics_path = (path.parent / lf.metricsFile) if lf.metricsFile else None
    metrics = MetricsFile(path=str(metrics_path), sha256=_sha256(metrics_path)) if metrics_path else None
    old_hash = previous.metricsFile.sha256 if previous.metricsFile else None
    new_metrics = metrics is not None and metrics.sha256 != old_hash
    metrics_rows = parse_metrics_csv(metrics_path) if new_metrics and metrics_path else None

    tracer = campaign_tracer(store, config_dir, launch_id)
    writer = _EvidenceWriter(store, launch_id, by, at)
    version = previous.version + 1
    with tracer.step("campaign_manager", "launch_desk", "amend_mandate", right="amend_mandate") as step:
        step.set_inputs({"file": str(path), "sha256": _sha256(path), "previousVersion": previous.version})
        mandate = _build_mandate(lf, launch_id, version, by, at, metrics)
        store.insert(mandate)
        _record_mandate_evidence(writer, mandate, previous, content_hash(_brief(previous)), metrics_rows)
        step.set_outputs({"mandateVersion": version, "evidenceIds": [e.evidenceId for e in writer.written]})
        step.set_decision("amended", "Position unchanged; the next Line reads the new version")
    record_audit(store, launch_id=launch_id, at=at, actor=by, role=role, action="amend_mandate",
                 right="amend_mandate", before=f"mandate:v{previous.version}", after=f"mandate:v{version}")
    return AmendResult(launchId=launch_id, mandateVersion=version, evidence=len(writer.written))
