"""CLI contract tests for `hipstraw-mm campaign` (contracts/cli.md). One section per unit."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from hipstraw_mm import cli


def run(*argv: str) -> tuple[int, dict[str, Any], str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err)
    body = json.loads(out.getvalue()) if out.getvalue().strip() else {}
    return code, body, err.getvalue()


# -- Unit 1: lint (T020) -------------------------------------------------------------------------------


def test_lint_json() -> None:
    code, body, _ = run("campaign", "--db", ":memory:", "lint", "--json")
    assert code == 0
    assert body["repertoireVersion"] == "campaign-repertoire.v0.2"
    assert body["counts"] == {"moves": 13, "lines": 5}
    assert body["errors"] == []


def test_lint_fails_on_a_broken_copy(tmp_path: Path) -> None:
    shutil.copytree(Path("config") / "campaign", tmp_path / "campaign")
    lines_path = tmp_path / "campaign" / "lines.yaml"
    lines = yaml.safe_load(lines_path.read_text(encoding="utf-8"))
    lines["lines"][0]["stages"][0].append("M99")
    lines_path.write_text(yaml.safe_dump(lines, sort_keys=False), encoding="utf-8")
    code, body, err = run("campaign", "--db", ":memory:", "lint", "--json", "--config-dir", str(tmp_path))
    assert code == 1
    assert "L01" in err and "M99" in err
    assert body["error"]["code"] == 1


# -- Unit 2: submit, amend, show (T028) ----------------------------------------------------------------

LAUNCH_FILE = "tests/fixtures/campaign/launch_complete.yaml"


def test_submit_then_show(tmp_path: Path) -> None:
    db = str(tmp_path / "c.db")
    code, body, _ = run("campaign", "--db", db, "submit", "--file", LAUNCH_FILE,
                        "--by", "Demo Sponsor", "--as", "sponsor", "--json")
    assert code == 0
    launch_id = body["launchId"]
    assert body["mandateVersion"] == 1 and body["positionVersion"] == 1 and body["evidence"] == 4
    assert body["items"]["assumption"] == 4

    code, shown, _ = run("campaign", "--db", db, "show", "--launch", launch_id, "--json")
    assert code == 0
    assert shown["launchId"] == launch_id and shown["mandateVersion"] == 1
    assert shown["position"]["version"] == 1 and shown["position"]["state"] == "proposed"


def test_submit_as_reviewer_is_refused(tmp_path: Path) -> None:
    code, body, err = run("campaign", "--db", str(tmp_path / "c.db"), "submit", "--file", LAUNCH_FILE,
                          "--by", "Demo Reviewer", "--as", "reviewer", "--json")
    assert code == 2 and "reviewer" in err
    assert body["error"]["code"] == 2


def test_show_unknown_launch(tmp_path: Path) -> None:
    code, _, err = run("campaign", "--db", str(tmp_path / "c.db"), "show", "--launch", "lch_nope", "--json")
    assert code == 2 and "lch_nope" in err


def test_amend(tmp_path: Path) -> None:
    db = str(tmp_path / "c.db")
    _, body, _ = run("campaign", "--db", db, "submit", "--file", LAUNCH_FILE,
                     "--by", "Demo Sponsor", "--as", "sponsor", "--json")
    code, amended, _ = run("campaign", "--db", db, "amend", "--launch", body["launchId"], "--file", LAUNCH_FILE,
                           "--by", "Demo Sponsor", "--as", "sponsor", "--json")
    assert code == 0 and amended["mandateVersion"] == 2 and amended["evidence"] == 0


# -- Unit 3: lines, choose (T037) ----------------------------------------------------------------------


def _submitted(tmp_path: Path) -> tuple[str, str]:
    db = str(tmp_path / "c.db")
    _, body, _ = run("campaign", "--db", db, "submit", "--file", LAUNCH_FILE,
                     "--by", "Demo Sponsor", "--as", "sponsor", "--json")
    return db, body["launchId"]


def test_lines_and_choose(tmp_path: Path) -> None:
    db, launch_id = _submitted(tmp_path)
    code, body, _ = run("campaign", "--db", db, "lines", "--launch", launch_id, "--json")
    assert code == 0
    assert "daysToDayZero" in body["facts"]
    assert {c["lineId"] for c in body["eligible"]} | {c["lineId"] for c in body["excluded"]} == {
        "L01", "L02", "L03", "L04", "L05"}

    eligible = body["eligible"][0]["lineId"]
    code, chosen, _ = run("campaign", "--db", db, "choose", "--launch", launch_id, "--line", eligible,
                          "--reason", "first test", "--by", "Demo CM", "--as", "campaign_manager", "--json")
    assert code == 0 and chosen["lineRunId"] == f"lrun_{launch_id}_1" and chosen["lineId"] == eligible


def test_choose_an_excluded_line_exits_2(tmp_path: Path) -> None:
    db, launch_id = _submitted(tmp_path)
    code, _, err = run("campaign", "--db", db, "choose", "--launch", launch_id, "--line", "L04",
                       "--reason", "x", "--by", "Demo CM", "--as", "campaign_manager", "--json")
    assert code == 2 and "excluded" in err


# -- Unit 4: step, deviate, run, stop (T049) -----------------------------------------------------------


def _chosen(tmp_path: Path) -> tuple[str, str]:
    db, launch_id = _submitted(tmp_path)
    _, chosen, _ = run("campaign", "--db", db, "choose", "--launch", launch_id, "--line", "L01", "--reason", "near",
                       "--by", "Demo CM", "--as", "campaign_manager", "--json")
    return db, chosen["lineRunId"]


def test_step_deviate_run(tmp_path: Path) -> None:
    db, run_id = _chosen(tmp_path)
    cm = ("--by", "Demo CM", "--as", "campaign_manager", "--json")
    code, body, _ = run("campaign", "--db", db, "step", "--line-run", run_id, *cm)
    assert code == 0 and body["stage"] == 1 and [e["moveId"] for e in body["executions"]] == ["M01"]
    code, body, _ = run("campaign", "--db", db, "deviate", "--line-run", run_id, "--skip", "M05",
                        "--reason", "dates confirmed", *cm)
    assert code == 0 and body["type"] == "skipped" and body["plannedStages"][1] == ["M04", "M13"]
    code, body, _ = run("campaign", "--db", db, "run", "--line-run", run_id, *cm)
    assert code == 0 and [e["moveId"] for e in body["executions"]] == ["M04", "M13", "M12"] and body["reviewId"]


def test_stop(tmp_path: Path) -> None:
    db, run_id = _chosen(tmp_path)
    code, body, _ = run("campaign", "--db", db, "stop", "--line-run", run_id, "--reason", "paused",
                        "--by", "Demo CM", "--as", "campaign_manager", "--json")
    assert code == 0 and body["state"] == "abandoned" and body["reviewId"]
    code, _, err = run("campaign", "--db", db, "step", "--line-run", run_id,
                       "--by", "Demo CM", "--as", "campaign_manager", "--json")
    assert code == 2 and "abandoned" in err


# -- Unit 6: review queue (T061) -----------------------------------------------------------------------


def test_review_queue_to_accepted_position(tmp_path: Path) -> None:
    db, run_id = _chosen(tmp_path)
    cm = ("--by", "Demo CM", "--as", "campaign_manager", "--json")
    _, ran, _ = run("campaign", "--db", db, "run", "--line-run", run_id, *cm)
    review_id = ran["reviewId"]
    code, shown, _ = run("campaign", "--db", db, "review", "show", "--review", review_id, "--json")
    assert code == 0 and shown["state"] == "drafted"
    reviewer = ("--by", "Demo Reviewer", "--as", "reviewer", "--json")
    for f in shown["findings"]:
        code, _, _ = run("campaign", "--db", db, "review", "finding", "--review", review_id,
                         "--finding", f["findingId"], "--accept", "--reason", "checked", *reviewer)
        assert code == 0
    code, body, _ = run("campaign", "--db", db, "review", "validate", "--review", review_id, *reviewer)
    assert code == 0 and body["state"] == "validated"
    code, body, _ = run("campaign", "--db", db, "review", "accept", "--review", review_id,
                        "--by", "Demo Sponsor", "--as", "sponsor", "--json")
    assert code == 0 and body["state"] == "accepted" and body["positionVersion"] == 2


# -- Unit 7: report (T066) -----------------------------------------------------------------------------


def test_report_command(tmp_path: Path) -> None:
    db, run_id = _chosen(tmp_path)
    cm = ("--by", "Demo CM", "--as", "campaign_manager", "--json")
    _, ran, _ = run("campaign", "--db", db, "run", "--line-run", run_id, *cm)
    review_id = ran["reviewId"]
    _, shown, _ = run("campaign", "--db", db, "review", "show", "--review", review_id, "--json")
    reviewer = ("--by", "Demo Reviewer", "--as", "reviewer", "--json")
    for f in shown["findings"]:
        run("campaign", "--db", db, "review", "finding", "--review", review_id, "--finding", f["findingId"],
            "--accept", "--reason", "ok", *reviewer)
    run("campaign", "--db", db, "review", "validate", "--review", review_id, *reviewer)
    run("campaign", "--db", db, "review", "accept", "--review", review_id, "--by", "Demo Sponsor", "--as", "sponsor",
        "--json")
    out = tmp_path / "report.md"
    code, body, _ = run("campaign", "--db", db, "report", "--launch", shown["launchId"], "--out", str(out), "--json")
    assert code == 0 and body["path"] == str(out) and len(body["sha256"]) == 64 and out.exists()
