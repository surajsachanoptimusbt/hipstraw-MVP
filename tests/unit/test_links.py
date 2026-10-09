"""T067: Unit tests for src/hipstraw_mm/market/links.py."""

from __future__ import annotations

import pytest


def _l(i: int, conf: float = 0.9) -> dict[str, object]:
    return {"fromNodeId": f"a{i}", "toNodeId": f"b{i}", "rationale": "why", "linkConfidence": conf}


class TestChunking:
    def test_chunks_of_size(self) -> None:
        from hipstraw_mm.market.links import chunk_links

        chunks = chunk_links([_l(i) for i in range(30)], 12)
        assert [len(c) for c in chunks] == [12, 12, 6]

    def test_empty(self) -> None:
        from hipstraw_mm.market.links import chunk_links

        assert chunk_links([], 12) == []

    def test_bad_size(self) -> None:
        from hipstraw_mm.market.links import chunk_links

        with pytest.raises(ValueError):
            chunk_links([_l(1)], 0)


class TestFlag:
    def test_below_threshold_flagged(self) -> None:
        from hipstraw_mm.market.links import flag_link

        assert flag_link(_l(1, 0.49), 0.5)["flagged"] is True

    def test_exactly_threshold_not_flagged(self) -> None:
        from hipstraw_mm.market.links import flag_link

        assert flag_link(_l(1, 0.5), 0.5)["flagged"] is False

    def test_above_not_flagged(self) -> None:
        from hipstraw_mm.market.links import flag_link

        assert flag_link(_l(1, 0.9), 0.5)["flagged"] is False


class TestRecord:
    def test_record_fields(self) -> None:
        from hipstraw_mm.market.links import link_record

        rec = link_record(_l(1, 0.3), 0.5, "step-1")
        assert rec["rationale"] == "why"
        assert rec["linkConfidence"] == 0.3
        assert rec["flagged"] is True
        assert rec["threshold"] == 0.5
        assert rec["stepId"] == "step-1"


class TestCoverage:
    def test_unknown_link_rejected(self) -> None:
        from hipstraw_mm.market.links import check_link_coverage

        with pytest.raises(ValueError, match="unknown"):
            check_link_coverage([{"fromNodeId": "a1", "toNodeId": "b1"}], [_l(1), _l(2)])
