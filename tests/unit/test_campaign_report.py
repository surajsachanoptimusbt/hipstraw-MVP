"""T065: the campaign readiness report, rendered only from an accepted Position (US5, FR-046, FR-051)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hipstraw_mm.campaign.config import load_settings
from hipstraw_mm.campaign.models import LineRun, ReportRecord, ReviewRun
from hipstraw_mm.campaign.moves.common import PageRead
from hipstraw_mm.campaign.report import render_report
from hipstraw_mm.campaign.review import accept_review, review_finding, validate_review
from hipstraw_mm.campaign.runner import run_line
from hipstraw_mm.campaign.selection import choose_line
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.errors import PreconditionError
from tests.integration.test_campaign_line_run import _synthesis, _variants
from tests.unit.campaign_fake_model import CannedClient, CannedModels
from tests.unit.campaign_moves_support import CONFIG, NOW, launch

CM = {"by": "Demo CM", "role": "campaign_manager", "now": NOW}
SCOPE = load_settings(CONFIG).scopeStatement


def _accepted(line: str, *, reject_first_rubric: bool = False) -> tuple[SqliteCampaignStore, str]:
    store, launch_id = launch()
    run = choose_line(store, CONFIG, launch_id, line, reason="demo", **CM)
    run_line(store, CONFIG, run.lineRunId, fetch=lambda url: PageRead(url=url, ok=True, text="Book a free 90-day "
             "invoice audit. LedgerLoop flags invoice errors before payment."),
             model=CannedModels(llm=CannedClient({"Synthesis": _synthesis, "Variants": _variants})), **CM)
    finished = store.get(LineRun, run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None
    rejected = next((f.findingId for f in review.findings if f.kind == "rubric"), None) if reject_first_rubric else None
    for f in review.findings:
        review_finding(store, CONFIG, review.reviewId, f.findingId, action="reject" if f.findingId == rejected
                       else "accept", reason="checked", by="Demo Reviewer", role="reviewer", now=NOW)
    validate_review(store, CONFIG, review.reviewId, by="Demo Reviewer", role="reviewer", now=NOW)
    accept_review(store, CONFIG, review.reviewId, by="Demo Sponsor", role="sponsor", now=NOW)
    return store, launch_id


def test_no_report_before_a_position_is_accepted(tmp_path: Path) -> None:
    store, launch_id = launch()
    with pytest.raises(PreconditionError, match="accepted"):
        render_report(store, CONFIG, launch_id, NOW, tmp_path / "r.md")


def test_report_sections_and_citations(tmp_path: Path) -> None:
    store, launch_id = _accepted("L02")
    record = render_report(store, CONFIG, launch_id, NOW, tmp_path / "r.md")
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert text.index(SCOPE) < text.index("\n## ")
    headings = re.findall(r"^## (.+)$", text, flags=re.M)
    assert headings == ["Channel by channel: is the message right for the audience it reaches?", "Whole campaign",
                        "Readiness blockers", "Strategy findings", "Open assumptions", "Unknowns", "Lines used",
                        "Evidence"]
    assert re.findall(r"^### (.+)$", text, flags=re.M) == ["Side by side", "Email", "LinkedIn ads"]
    assert "| Question | Email | LinkedIn ads |" in text
    assert "| CR03 Offer and one next step | partly met | partly met |" in text
    assert "| CR03 Offer and one next step | partly met |" in text
    assert "Reaches: 1,800 AP managers and controllers" in text
    assert '"Book a free 90-day invoice audit"' in text
    for row in re.findall(r"^\| CR\d\d .+$", text[text.index("### Email"):], flags=re.M):  # past the side by side
        assert "ev_" in row or "unknown" in row
    stored = store.list_for_launch(ReportRecord, launch_id)
    assert stored == [record] and record.positionVersion == 2 and len(record.sha256) == 64


def test_report_has_no_score_or_forecast(tmp_path: Path) -> None:
    store, launch_id = _accepted("L02")
    render_report(store, CONFIG, launch_id, NOW, tmp_path / "r.md")
    body = (tmp_path / "r.md").read_text(encoding="utf-8").replace(SCOPE, "")
    for word in ("score", "probability", "forecast", "likelihood", "/10"):
        assert word not in body.lower(), word


def test_a_rejected_rubric_finding_is_not_reported(tmp_path: Path) -> None:
    store, launch_id = _accepted("L02", reject_first_rubric=True)
    render_report(store, CONFIG, launch_id, NOW, tmp_path / "r.md")
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "| CR01 Message fits the audience | rejected | unknown (too little evidence) |" in text
    email = text[text.index("### Email"):text.index("### LinkedIn ads")]
    assert "| CR01 " not in email and "| CR02 " in email
    assert "rejected by the reviewer: 1" in text


def test_l01_report_lists_blockers_and_the_line(tmp_path: Path) -> None:
    store, launch_id = _accepted("L01")
    render_report(store, CONFIG, launch_id, NOW, tmp_path / "r.md")
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "L01 Readiness-first" in text and "No rubric judgements yet" in text


def test_the_report_covers_every_accepted_review(tmp_path: Path) -> None:
    store, launch_id = _accepted("L02")
    run = choose_line(store, CONFIG, launch_id, "L01", reason="readiness next", **CM)
    run_line(store, CONFIG, run.lineRunId, **CM)
    finished = store.get(LineRun, run.lineRunId)
    review = store.get(ReviewRun, finished.reviewId if finished else "")
    assert review is not None
    for f in review.findings:
        review_finding(store, CONFIG, review.reviewId, f.findingId, action="accept", reason="ok",
                       by="Demo Reviewer", role="reviewer", now=NOW)
    validate_review(store, CONFIG, review.reviewId, by="Demo Reviewer", role="reviewer", now=NOW)
    accept_review(store, CONFIG, review.reviewId, by="Demo Sponsor", role="sponsor", now=NOW)
    render_report(store, CONFIG, launch_id, NOW, tmp_path / "r.md")
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "Position v3" in text and "| CR03 Offer and one next step | partly met |" in text
    # L01's M13 adds each channel's rules, with their sources, to the channel's section.
    email = text[text.index("### Email"):text.index("### LinkedIn ads")]
    assert "| EM03 Sending domain authenticated (SPF or DKIM) | must | met |" in email
    assert "support.google.com/a/answer/81126" in email
    assert "| Open blockers | 0 | 0 |" in text and "| Practice fixes | 0 | 0 |" in text
    assert "L02 Strategy validation" in text and "L01 Readiness-first" in text
    assert "Proposed variant to test" in text
