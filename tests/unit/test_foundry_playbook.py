"""The playbook (Nov 6 meeting): predefined Lines and Moves, picked by rules, never by a model. For each task the
Lines available are listed with their conditions checked, the eligible ones ranked in playbook order, and the
first picked."""

from __future__ import annotations

import io
import json
from pathlib import Path

from hipstraw_mm import cli
from hipstraw_mm.foundry.demand import load_demand_rubric
from hipstraw_mm.foundry.playbook import recommend
from hipstraw_mm.foundry.walkthrough import Thesis, load_thesis

RUBRIC = load_demand_rubric(Path("config"))
ZIMPLII = load_thesis(Path("input/demand/theses/zimplii_technical_assurance.yaml"), RUBRIC)


def test_each_task_lists_its_lines_and_picks_the_first_eligible() -> None:
    rec = recommend(ZIMPLII, RUBRIC)
    picks = {h.id: [t.lineId for t in h.tasks] for h in rec.hypotheses}
    assert picks == {"H1": ["LD1", "LD2", "LD4", "LD5"], "H2": ["LD1", "LD3", None, "LD5"],
                     "H3": ["LD1", "LD2", "LD4", "LD5"]}
    t2 = rec.hypotheses[0].tasks[1]
    ld2, ld3 = t2.options
    assert (ld2.lineId, ld2.eligible, ld2.rank, ld2.picked) == ("LD2", True, 1, True)
    assert (ld3.lineId, ld3.eligible, ld3.rank, ld3.picked) == ("LD3", False, None, False)
    assert [(c.text, c.ok) for c in ld3.checks] == [("motion is sales_led, needs self_serve", False)]
    assert t2.reason.startswith("Playbook: LD2 Paid pilot is the first eligible Line")
    assert "Jev" in rec.ranking and "deferred" in rec.ranking
    t3 = rec.hypotheses[1].tasks[2]
    assert t3.lineId is None and t3.moves == [] and "recurring is false, needs true" in t3.reason


def test_moves_carry_their_status_and_the_first_action() -> None:
    h1 = recommend(ZIMPLII, RUBRIC).hypotheses[0]
    first = h1.tasks[0].moves
    assert [(m.id, m.status) for m in first[:3]] == [("DV01", "done"), ("DV09", "next"), ("DV02", "planned")]
    assert first[2].needsCharter and not first[1].needsCharter
    assert h1.firstAction.startswith("DV09 Map reachable buyers")
    assert [m.dimension for m in h1.metrics][0] == "Problem demand"


def test_the_payload_hash_changes_only_when_the_picks_change() -> None:
    a, b = recommend(ZIMPLII, RUBRIC), recommend(ZIMPLII, RUBRIC)
    assert a.payload_hash() == b.payload_hash()
    raw = ZIMPLII.model_dump(mode="json")
    raw["hypotheses"][0]["motion"] = "self_serve"
    changed = recommend(Thesis.model_validate(raw), RUBRIC)
    assert changed.hypotheses[0].tasks[1].lineId == "LD3" and changed.payload_hash() != a.payload_hash()


def test_cli_recommend() -> None:
    out = io.StringIO()
    code = cli.main(["demand", "recommend", "--thesis", "input/demand/theses/zimplii_technical_assurance.yaml",
                     "--json"], stdout=out, stderr=io.StringIO())
    data = json.loads(out.getvalue())
    assert code == 0 and data["command"] == "demand recommend" and len(data["payloadHash"]) == 64
    assert data["hypotheses"][1]["tasks"][1]["lineId"] == "LD3"
