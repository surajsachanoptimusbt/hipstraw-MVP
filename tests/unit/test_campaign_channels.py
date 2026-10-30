"""Channel-first campaigns (Oct 30 meeting): each channel with its own audience, setup and assets, checked by M13
against config/campaign/channels.yaml, the platforms' rules, the law and practice, each with its source."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from hipstraw_mm.campaign.channels import ChannelPlan, check_channel, load_channel_standards
from hipstraw_mm.campaign.intake import read_launch_file, submit_launch
from hipstraw_mm.campaign.models import Asset, LineRun, Mandate, ReviewRun
from hipstraw_mm.campaign.runner import run_line
from hipstraw_mm.campaign.selection import choose_line
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import UsageError
from tests.unit.campaign_moves_support import CONFIG, FIX, NOW, context, run

STANDARDS = load_channel_standards(CONFIG)
EMAIL_SCENARIO = Path("input/campaign/kozmo_email_us.yaml")
THREE_CHANNELS = Path("input/campaign/kozmo_three_channels_us.yaml")
CM = {"by": "Demo CM", "role": "campaign_manager", "now": NOW}


def _mandate(path: Path) -> Mandate:
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(store, CONFIG, path, by="Kozmo GTM lead", role="sponsor", now=NOW).launchId
    mandate = store.latest_mandate(launch_id)
    assert mandate is not None
    return mandate


def _results(mandate: Mandate, channel: str) -> dict[str, Any]:
    plan = next(p for p in mandate.channelPlans if p.channel == channel)
    return {r.checkId: r for r in check_channel(mandate, plan, STANDARDS.channels[channel])}


def _check(channel: str, check_id: str, plan: ChannelPlan, assets: list[Asset], market: str = "US") -> Any:
    standard = STANDARDS.channels[channel].model_copy(update={"checks": [
        c for c in STANDARDS.channels[channel].checks if c.id == check_id]})
    mandate = _mandate(FIX / "launch_complete.yaml").model_copy(update={"assets": assets, "market": market})
    found = check_channel(mandate, plan, standard)
    return found[0] if found else None


# -- the standards file ------------------------------------------------------------------------------------


def test_every_platform_names_who_it_reaches_and_every_check_names_its_source() -> None:
    assert set(STANDARDS.channels) == {"email", "linkedin_ads", "instagram_ads", "reddit_ads"}
    for standard in STANDARDS.channels.values():
        assert standard.reach.how and standard.reach.fitsWell and standard.reach.fitsPoorly and standard.format
        for check in standard.checks:
            assert check.source and check.level in ("must", "should"), check.id
    assert "company size" in STANDARDS.channels["instagram_ads"].reach.fitsPoorly
    assert STANDARDS.name("linkedin_ads") == "LinkedIn ads" and STANDARDS.name("paid_social") == "paid social"


def test_email_rules_follow_the_sender_requirements_and_can_spam() -> None:
    email = {c.id: c for c in STANDARDS.channels["email"].checks}
    assert email["EM03"].level == "must" and email["EM03"].args["any"] is True  # SPF or DKIM for every sender
    assert email["EM04"].mustWhen is not None and email["EM04"].mustWhen.atLeast == 5000  # bulk senders
    assert email["EM07"].markets == ["US"] and "CAN-SPAM" in email["EM07"].source
    assert email["EM08"].markets == ["IN"] and "DPDP" in email["EM08"].source


# -- the checks ------------------------------------------------------------------------------------------


def test_a_fact_not_stated_is_not_stated_never_a_guess() -> None:
    result = _check("email", "EM01", ChannelPlan(channel="email", setup={"listSource": "webinar"}), [])
    assert (result.status, result.detail) == ("not_stated", "not stated: consent")


def test_spf_or_dkim_is_enough_for_a_small_sender_but_bulk_senders_need_dmarc_too() -> None:
    small = ChannelPlan(channel="email", setup={"authentication": ["DKIM"], "listSize": 2100})
    assert _check("email", "EM03", small, []).status == "met"
    dmarc = _check("email", "EM04", small, [])
    assert (dmarc.status, dmarc.level) == ("not_met", "should")
    bulk = small.model_copy(update={"setup": {"authentication": ["SPF", "DKIM"], "listSize": 12000}})
    assert _check("email", "EM04", bulk, []).level == "must"


def test_the_postal_address_rule_applies_in_the_us_only() -> None:
    plan = ChannelPlan(channel="email", setup={"postalAddress": "1 Main St, Springfield"})
    footer = Asset(assetId="A2", kind="email_copy", channel="email", fields={"footer": "Unsubscribe."})
    assert _check("email", "EM07", plan, [footer]).status == "not_met"
    assert _check("email", "EM07", plan, [footer], market="IN") is None
    with_address = footer.model_copy(update={"fields": {"footer": "Kozmo, 1 Main  St, Springfield. Unsubscribe."}})
    assert _check("email", "EM07", plan, [with_address]).status == "met"


def test_length_tags_and_success_measure_checks() -> None:
    plan = ChannelPlan(channel="email", successMeasure="Open rate above 40%")
    long_subject = Asset(assetId="A2", kind="email_copy", channel="email", fields={
        "subject": "x" * 61, "ctaUrl": "https://k.ai/p?utm_source=e&utm_medium=email"})
    subject = _check("email", "EM09", plan, [long_subject])
    assert subject.status == "not_met" and "61 characters" in subject.detail
    tags = _check("email", "EM11", plan, [long_subject])
    assert tags.status == "not_met" and "utm_campaign" in tags.detail
    assert _check("email", "EM13", plan, [long_subject]).status == "not_met"  # opens are inflated by Apple MPP


# -- the scenarios -----------------------------------------------------------------------------------------


def test_the_email_scenario_finds_what_a_practitioner_would() -> None:
    results = _results(_mandate(EMAIL_SCENARIO), "email")
    assert all(results[c].status == "met" for c in ("EM01", "EM02", "EM03", "EM05", "EM09", "EM10"))
    assert results["EM07"].status == "not_stated"  # no postal address given: an unknown, not a guess
    assert {c for c, r in results.items() if r.status == "not_met"} == {"EM04", "EM06", "EM11", "EM13"}
    assert "EM08" not in results  # India's consent rule does not apply to a US launch


def test_three_channels_differ_where_their_rules_differ() -> None:
    mandate = _mandate(THREE_CHANNELS)
    linkedin, instagram = _results(mandate, "linkedin_ads"), _results(mandate, "instagram_ads")
    assert linkedin["LI06"].status == "not_met" and "(limit 150)" in linkedin["LI06"].detail
    assert linkedin["LI03"].status == "not_met" and linkedin["LI02"].status == "met"
    assert instagram["IG02"].status == "not_stated" and instagram["IG02"].level == "must"
    assert instagram["IG04"].status == "met"


# -- intake ----------------------------------------------------------------------------------------------


def test_channel_assets_belong_to_their_channel_and_the_brief_carries_each_plan() -> None:
    lf = read_launch_file(THREE_CHANNELS)
    assert lf.strategy.channels == ["email", "linkedin_ads", "instagram_ads"]
    mandate = _mandate(THREE_CHANNELS)
    assert [(a.kind, a.channel) for a in mandate.assets] == [
        ("landing_page", None), ("email_copy", "email"), ("ad_copy", "linkedin_ads"), ("ad_copy", "instagram_ads")]
    assert mandate.channelPlans[1].setup["audienceSize"] == 38000
    assert mandate.assets[1].fields["subject"] == "Are you paying what your contracts say?"


@pytest.mark.parametrize("change, message", [
    (lambda raw: raw["channels"].append(raw["channels"][0]), "listed twice"),
    (lambda raw: raw["strategy"].update(channels=["email", "linkedin_ads"]), "name different channels"),
])
def test_channels_are_named_once(tmp_path: Path, change: Any, message: str) -> None:
    raw = yaml.safe_load(EMAIL_SCENARIO.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "launch.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(UsageError, match=message):
        read_launch_file(path)


def test_a_vague_channel_or_one_with_no_audience_is_an_unknown_from_the_start(tmp_path: Path) -> None:
    complete = submit_launch(SqliteCampaignStore(":memory:"), CONFIG, FIX / "launch_complete.yaml", by="S",
                             role="sponsor", now=NOW)
    assert "unknown" not in complete.items  # every channel named, each with its audience
    raw = yaml.safe_load((FIX / "launch_bad_market.yaml").read_text(encoding="utf-8"))
    raw["market"] = "US"  # the older shape: strategy.channels only, with a vague "paid_social"
    launch_file = tmp_path / "vague_channel.yaml"
    launch_file.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(store, CONFIG, launch_file, by="S", role="sponsor", now=NOW).launchId
    position = store.head_position(launch_id)
    assert position is not None
    unknowns = {i.key: i.text for i in position.items if i.kind == "unknown"}
    assert "not a specific platform" in unknowns["CHANNEL:paid_social"]
    assert "Who the Email channel reaches is not stated" in unknowns["AUDIENCE:email"]


# -- M13 and its Review ------------------------------------------------------------------------------------


def test_m13_opens_unknowns_for_missing_rules_and_keeps_the_checklist() -> None:
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(store, CONFIG, EMAIL_SCENARIO, by="Kozmo GTM lead", role="sponsor", now=NOW).launchId
    out = run(context(store, launch_id, "M13"))
    assert [(i.kind, i.key, i.channel) for i in out.newItems] == [("unknown", "EM07:email", "email")]
    standards = [p for p in out.proposals if p["type"] == "standard"]
    assert len(standards) == len(_results(_mandate(EMAIL_SCENARIO), "email"))
    assert out.note is not None and out.note == "6 met, 4 not met, 2 not stated (Email)"


def test_a_should_miss_reaches_the_review_as_a_fix_with_its_source() -> None:
    store = SqliteCampaignStore(":memory:")
    launch_id = submit_launch(store, CONFIG, EMAIL_SCENARIO, by="Kozmo GTM lead", role="sponsor", now=NOW).launchId
    line_run = choose_line(store, CONFIG, launch_id, "L01", reason="Day Zero close", **CM)
    run_line(store, CONFIG, line_run.lineRunId, **CM)
    finished = store.get(LineRun, line_run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None
    fixes = [f for f in review.findings if f.kind == "standard"]
    assert len(fixes) == 4 and all(f.channel == "email" and "Source:" in f.text for f in fixes)
    assert any("Apple Mail Privacy Protection" in f.text for f in fixes)
    unknown = next(f for f in review.findings if f.kind == "unknown" and f.channel == "email")
    assert "Physical postal address" in unknown.text
    assert date.fromisoformat(review.createdAt[:10]) == NOW.date()
