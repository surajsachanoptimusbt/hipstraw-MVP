"""T025/T026: a launch file becomes a mandate, evidence records and a proposed Position v1 (US1)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from hipstraw_mm.campaign.intake import amend_mandate, submit_launch
from hipstraw_mm.campaign.models import AuditEvent, EvidenceRecord, Mandate
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError, UsageError

FIX = Path("tests/fixtures/campaign")
CONFIG = Path("config")
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> SqliteCampaignStore:
    return SqliteCampaignStore(":memory:")


def _submit(store: SqliteCampaignStore, name: str = "launch_complete.yaml") -> str:
    return submit_launch(store, CONFIG, FIX / name, by="Demo Sponsor", role="sponsor", now=NOW).launchId


def test_complete_launch(store: SqliteCampaignStore) -> None:
    launch_id = _submit(store)
    mandate = store.latest_mandate(launch_id)
    assert mandate is not None and mandate.version == 1
    assert (mandate.market, mandate.dayZero) == ("US", date(2026, 11, 11))
    assert [a.assetId for a in mandate.assets] == ["A1", "A2", "A3"]

    evidence = store.list_for_launch(EvidenceRecord, launch_id)
    assets = [e for e in evidence if e.sourceRef.startswith("mandate:v1#asset:")]
    assert len(assets) == 3
    assert all(e.verificationState == "reported" and len(e.contentHash) == 64 for e in evidence)

    position = store.head_position(launch_id)
    assert position is not None and (position.version, position.state) == (1, "proposed")
    ids = {e.evidenceId for e in evidence}
    claims = [i for i in position.items if i.kind == "claim"]
    assert claims and all(i.state == "reported" and i.evidenceRefs and set(i.evidenceRefs) <= ids for i in claims)
    core = [i for i in position.items if i.kind == "assumption"]
    assert len(core) == 4  # two general + one per channel (email, linkedin_ads)
    assert all(i.core and i.state == "open" for i in core)
    assert any("LinkedIn ads" in i.text and i.channel == "linkedin_ads" for i in core)
    assert [i for i in position.items if i.kind == "unknown"] == []
    assert position.mechanismStamp.repertoireVersion == "campaign-repertoire.v0.2"
    assert position.evidenceCutoff == NOW.isoformat()


def test_missing_landing_page_is_an_unknown_not_a_claim(store: SqliteCampaignStore) -> None:
    position = store.head_position(_submit(store, "launch_missing_landing.yaml"))
    assert position is not None
    unknowns = [i for i in position.items if i.kind == "unknown"]
    assert any("landing page" in i.text.lower() for i in unknowns)
    assert all(i.state == "open" for i in unknowns)
    assert not any("landing page" in i.text.lower() for i in position.items if i.kind == "claim")


def test_market_outside_the_launch_markets_is_rejected(store: SqliteCampaignStore) -> None:
    with pytest.raises(UsageError, match="US, IN"):
        _submit(store, "launch_bad_market.yaml")


def test_metric_rows_keep_their_values_and_flag_missing_definitions(store: SqliteCampaignStore) -> None:
    launch_id = _submit(store, "launch_live.yaml")
    metrics = [e for e in store.list_for_launch(EvidenceRecord, launch_id) if e.kind == "metric"]
    assert {e.metric.metric: e.metric.value for e in metrics if e.metric} == {
        "landing_page_sessions": 1240.0, "demo_bookings": 9.0,
    }
    by_name = {e.metric.metric: e for e in metrics if e.metric}
    assert by_name["landing_page_sessions"].verificationState == "reported"
    bookings = by_name["demo_bookings"]
    assert bookings.verificationState == "unverified" and "definition" in bookings.uncertainty
    mandate = store.latest_mandate(launch_id)
    assert mandate is not None and mandate.metricsFile is not None and len(mandate.metricsFile.sha256) == 64


def test_role_without_the_right_is_refused_and_audited(store: SqliteCampaignStore) -> None:
    with pytest.raises(PreconditionError, match="reviewer"):
        submit_launch(store, CONFIG, FIX / "launch_complete.yaml", by="Demo Reviewer", role="reviewer", now=NOW)
    refused = [e for e in store.list_all(AuditEvent) if e.outcome == "refused"]
    assert [(e.actor, e.action) for e in refused] == [("Demo Reviewer", "submit_launch")]


def test_amend_creates_a_new_version_and_evidence_only_for_changed_assets(
    store: SqliteCampaignStore, tmp_path: Path
) -> None:
    launch_id = _submit(store)
    before = store.head_position(launch_id)
    raw = yaml.safe_load((FIX / "launch_complete.yaml").read_text(encoding="utf-8"))
    email = next(a for c in raw["channels"] for a in c["assets"] if a["kind"] == "email_copy")
    email["text"] = "Subject: a new subject line"
    amended = tmp_path / "amended.yaml"
    amended.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    evidence_before = len(store.list_for_launch(EvidenceRecord, launch_id))

    result = amend_mandate(store, CONFIG, launch_id, amended, by="Demo Sponsor", role="sponsor", now=NOW)

    assert result.mandateVersion == 2
    versions = store.list_for_launch(Mandate, launch_id)
    assert [m.version for m in versions] == [1, 2]
    assert versions[0].assets[1].text != "Subject: a new subject line"  # v1 unchanged
    new = store.list_for_launch(EvidenceRecord, launch_id)[evidence_before:]
    assert len(new) == 1 and str(new[0].content).endswith("Subject: a new subject line")
    assert new[0].sourceRef.startswith("mandate:v2#asset:")
    assert store.head_position(launch_id) == before


def test_amend_by_a_campaign_manager_is_refused(store: SqliteCampaignStore) -> None:
    launch_id = _submit(store)
    with pytest.raises(PreconditionError, match="amend_mandate"):
        amend_mandate(store, CONFIG, launch_id, FIX / "launch_complete.yaml", by="Demo CM",
                      role="campaign_manager", now=NOW)
