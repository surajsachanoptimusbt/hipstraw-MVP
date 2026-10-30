"""T018: the shipped first-release repertoire (HA section 5) loads as versioned config."""

from __future__ import annotations

from pathlib import Path

from hipstraw_mm.campaign.repertoire import load_repertoire

REP = load_repertoire(Path("config"))


def test_thirteen_moves_and_five_lines() -> None:
    assert REP.version == "campaign-repertoire.v0.2"
    assert sorted(REP.moves) == [f"M{n:02d}" for n in range(1, 14)]  # HA's twelve plus M13 channel standards
    assert sorted(REP.lines) == ["L01", "L02", "L03", "L04", "L05"]


def test_line_stages_follow_ha_section_5() -> None:
    stages = {line_id: line.stages for line_id, line in REP.lines.items()}
    assert stages == {
        "L01": [["M01"], ["M04", "M05", "M13"], ["M12"]],
        "L02": [["M02"], ["M06"], ["M07"], ["M09"]],
        "L03": [["M07"], ["M09"], ["M10"], ["M11"]],
        "L04": [["M03"], ["M11"], ["M06"]],
        "L05": [["M08"], ["M02"], ["M12"]],
    }


def test_m10_is_the_only_external_effect_and_needs_an_approved_test_plan() -> None:
    e3 = [m.id for m in REP.moves.values() if "E3" in m.effectClasses]
    assert e3 == ["M10"]
    assert REP.moves["M10"].requiresApproval == "test_plan"
    assert REP.moves["M09"].producesTestPlan is True


def test_inference_moves_are_declared_with_prompts() -> None:
    assert REP.moves["M02"].effectClasses == ["E1", "E2"]
    e2 = {m.id: m.promptVersion for m in REP.moves.values() if "E2" in m.effectClasses}
    assert e2 == {
        "M02": "campaign_source_summary.v1", "M06": "campaign_synthesis.v2", "M07": "campaign_variants.v1",
    }


def test_every_move_and_line_has_a_version_and_every_line_a_review_question() -> None:
    assert all(m.version for m in REP.moves.values())
    assert all(line.version and line.reviewQuestion for line in REP.lines.values())
