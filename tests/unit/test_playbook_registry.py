"""The playbook as structured data: counts, references and stance matrices match the playbook."""

from __future__ import annotations

from hipstraw_mm.market.playbook import integrity_problems, load_playbook

# Playbook gap 6 (docs/playbook_gaps.md): these Plays' default stance is not allowed by their own
# primary Strategy. Recorded, not fixed, until the playbook owner decides.
KNOWN_STANCE_MISMATCHES = {"P25", "P26", "P29"}


def test_counts_and_references_match_the_playbook() -> None:
    pb = load_playbook()
    assert (len(pb.strategies), len(pb.plays), len(pb.lines), len(pb.moves), len(pb.gambits), len(pb.actions),
            len(pb.hardRules), len(pb.marketTypes), len(pb.axes)) == (16, 32, 20, 56, 12, 60, 20, 16, 7)
    assert integrity_problems(pb) == []


def test_play_stances_fit_their_strategy_except_the_documented_gaps() -> None:
    pb = load_playbook()
    mismatched = {
        p.id for p in pb.plays
        if p.stance.default and not pb.strategy(p.strategy.primary).stance.permits(p.stance.default)
    }
    assert mismatched == KNOWN_STANCE_MISMATCHES


def test_matrices_read_by_column() -> None:
    pb = load_playbook()
    hypothesis = pb.matrices.positionStance["MP1"]["Hypothesis"]
    assert hypothesis["Probe"] == "default" and hypothesis["Activate"] == hypothesis["Expand"] == "never"
    assert "Build" not in hypothesis  # blank cell: not typical
    assert pb.matrices.gambitStance["G02"] == {"Listen": "never", "Scout": "never", "Co-create": "default",
                                               "Activate": "allowed", "Protect": "never"}


def test_cards_carry_their_line_steps_and_actions_their_tier() -> None:
    pb = load_playbook()
    assert [s.id for s in pb.line("L03").steps] == ["M09", "A10", "M14", "A15", "A16"]
    assert pb.line("L05").branchIds == ["M29", "L02"]
    assert pb.strategy("S02").plays.primary == [] and pb.strategy("S02").plays.also == ["P02", "P03", "P18", "P32"]
    assert (pb.action("A16").tier, pb.action("A40").tier) == (2, 5)
    assert pb.gambit("G02").approver == "Commercial sponsor"
