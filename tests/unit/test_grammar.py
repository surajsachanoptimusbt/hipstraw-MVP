"""T030: Unit tests for config/grammar.yaml and src/hipstraw_mm/market/grammar.py."""

from __future__ import annotations

EXPECTED_KEYS = [
    "market_scope", "problem", "segment_fit", "buyer", "use_case",
    "value_proposition", "demand_signals", "adoption_readiness", "economics",
    "timing", "alternatives", "risks", "dependencies",
    "evidence_sufficiency", "evidence_quality", "critical_unknowns",
    "trajectory", "transition", "market_status",
]


class TestGrammarYaml:
    def test_exactly_19_unique_keys(self) -> None:
        from hipstraw_mm.market.grammar import load_grammar

        grammar = load_grammar()
        keys = [d.key for d in grammar.dimensions]
        assert len(keys) == 19
        assert len(set(keys)) == 19

    def test_keys_match_expected(self) -> None:
        from hipstraw_mm.market.grammar import load_grammar

        grammar = load_grammar()
        keys = [d.key for d in grammar.dimensions]
        assert set(keys) == set(EXPECTED_KEYS)

    def test_every_rank_key_in_states(self) -> None:
        from hipstraw_mm.market.grammar import load_grammar

        grammar = load_grammar()
        for dim in grammar.dimensions:
            for rank_key in dim.rank:
                assert rank_key in dim.states, (
                    f"dimension {dim.key}: rank key {rank_key!r} not in states {dim.states}"
                )

    def test_decided_by_is_market_manager(self) -> None:
        from hipstraw_mm.market.grammar import load_grammar

        grammar = load_grammar()
        for dim in grammar.dimensions:
            assert dim.decidedBy == "market_manager", (
                f"dimension {dim.key}: decidedBy={dim.decidedBy!r}, expected 'market_manager'"
            )

    def test_no_replacement_character(self) -> None:
        from pathlib import Path

        text = (Path("config") / "grammar.yaml").read_text(encoding="utf-8")
        assert "�" not in text, "U+FFFD replacement character found in grammar.yaml"

    def test_header_records_source_and_replacements(self) -> None:
        from pathlib import Path

        text = (Path("config") / "grammar.yaml").read_text(encoding="utf-8")
        lines = text.split("\n")
        header = "\n".join(lines[:3])
        assert "sha256" in header.lower() or "SHA-256" in header
        assert "hipstraw-faculty" in header or "grammar.json" in header

    def test_lookup_by_key(self) -> None:
        from hipstraw_mm.market.grammar import load_grammar

        grammar = load_grammar()
        dim = grammar.by_key("market_scope")
        assert dim is not None
        assert dim.key == "market_scope"
        assert grammar.by_key("nonexistent") is None
