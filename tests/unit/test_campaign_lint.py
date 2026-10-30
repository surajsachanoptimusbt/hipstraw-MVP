"""T019: the Line lint (contracts/config.md, FR-018). Each broken copy of the shipped repertoire must be
refused with an error that names the Line or Move at fault."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from hipstraw_mm.campaign.repertoire import load_repertoire
from hipstraw_mm.errors import ConfigError

Doc = dict[str, Any]


def _broken(tmp_path: Path, change: Callable[[Doc, Doc], None]) -> Path:
    """A copy of config/campaign with `change(moves_doc, lines_doc)` applied."""
    shutil.copytree(Path("config") / "campaign", tmp_path / "campaign")
    moves_path, lines_path = tmp_path / "campaign" / "moves.yaml", tmp_path / "campaign" / "lines.yaml"
    moves, lines = (yaml.safe_load(p.read_text(encoding="utf-8")) for p in (moves_path, lines_path))
    change(moves, lines)
    moves_path.write_text(yaml.safe_dump(moves, sort_keys=False), encoding="utf-8")
    lines_path.write_text(yaml.safe_dump(lines, sort_keys=False), encoding="utf-8")
    return tmp_path


def _move(moves: Doc, move_id: str) -> Doc:
    return next(m for m in moves["moves"] if m["id"] == move_id)  # type: ignore[no-any-return]


def _line(lines: Doc, line_id: str) -> Doc:
    return next(x for x in lines["lines"] if x["id"] == line_id)  # type: ignore[no-any-return]


def _errors(tmp_path: Path, change: Callable[[Doc, Doc], None]) -> str:
    with pytest.raises(ConfigError) as exc:
        load_repertoire(_broken(tmp_path, change))
    return str(exc.value)


def test_shipped_repertoire_passes() -> None:
    load_repertoire(Path("config"))


def test_unknown_move_in_a_line(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _line(lines, "L01")["stages"][1].append("M99")
    msg = _errors(tmp_path, change)
    assert "L01" in msg and "M99" in msg


def test_move_without_version(tmp_path: Path) -> None:
    msg = _errors(tmp_path, lambda moves, lines: _move(moves, "M04").pop("version"))
    assert "M04" in msg and "version" in msg


def test_line_without_version(tmp_path: Path) -> None:
    msg = _errors(tmp_path, lambda moves, lines: _line(lines, "L02").pop("version"))
    assert "L02" in msg and "version" in msg


def test_unknown_handler(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _move(moves, "M05")["handler"] = "readiness.no_such_check"
    msg = _errors(tmp_path, change)
    assert "M05" in msg and "readiness.no_such_check" in msg


def test_external_effect_without_an_earlier_test_plan(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _line(lines, "L03")["stages"] = [["M07"], ["M10"], ["M09"], ["M11"]]
    msg = _errors(tmp_path, change)
    assert "L03" in msg and "M10" in msg and "Test Plan" in msg


def test_external_effect_without_required_approval(tmp_path: Path) -> None:
    msg = _errors(tmp_path, lambda moves, lines: _move(moves, "M10").pop("requiresApproval"))
    assert "M10" in msg and "approval" in msg


def test_inference_move_cannot_raise_a_claim_above_reported(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _move(moves, "M06")["transitions"] = [{"kind": "claim", "from": ["reported"], "to": ["observed"]}]
    msg = _errors(tmp_path, change)
    assert "M06" in msg and "observed" in msg


def test_unknown_fact(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _line(lines, "L01")["useWhen"] = {"all": [{"fact": "vibes", "op": ">", "value": 0}]}
    msg = _errors(tmp_path, change)
    assert "L01" in msg and "vibes" in msg


def test_unknown_operator(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _line(lines, "L02")["useWhen"] = {"all": [{"fact": "unknowns", "op": "~=", "value": 0}]}
    msg = _errors(tmp_path, change)
    assert "L02" in msg and "~=" in msg


def test_value_of_the_wrong_type(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _line(lines, "L04")["useWhen"] = {"all": [{"fact": "isLive", "op": "==", "value": 3}]}
    msg = _errors(tmp_path, change)
    assert "L04" in msg and "isLive" in msg


def test_duplicate_ids(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        moves["moves"].append(dict(_move(moves, "M01")))
        lines["lines"].append(dict(_line(lines, "L05")))
    msg = _errors(tmp_path, change)
    assert "M01" in msg and "L05" in msg and "duplicate" in msg


def test_every_error_is_reported_at_once(tmp_path: Path) -> None:
    def change(moves: Doc, lines: Doc) -> None:
        _move(moves, "M05")["handler"] = "x.y"
        _line(lines, "L01")["stages"][0].append("M98")
    msg = _errors(tmp_path, change)
    assert "M05" in msg and "M98" in msg
