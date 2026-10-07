"""Discovery targeting (FR-022, research R19): which queries and pages come first, and which
candidates are kept when there are more than the cap.

Added after the first live run (`run_20261007T140925`), which kept the first 10 entries of an
alphabetical directory in page order. Nothing here decides a disposition.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Literal

from hipstraw_mm.config import Metro
from hipstraw_mm.evidence.excerpt_check import normalize
from hipstraw_mm.evidence.location import location_status, parse_city_state
from hipstraw_mm.models import domain_key

MetroMatch = Literal["in", "out", "unknown"]
PositionMatch = Literal["strong", "partial", "weak"]

_METRO_ORDER = {"in": 0, "unknown": 1, "out": 2}
_POSITION_ORDER = {"strong": 0, "partial": 1, "weak": 2}


# -- queries ---------------------------------------------------------------------


def _mentions(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE) is not None


def query_metro(query: str, metros: list[Metro]) -> int | None:
    """The index of the first metro whose name or a listed place appears in the query as whole words."""
    for index, metro in enumerate(metros):
        names = [metro.name, *(place for places in metro.places.values() for place in places)]
        if any(_mentions(query, name) for name in names):
            return index
    return None


def order_queries(queries: list[str], metros: list[Metro]) -> list[str]:
    """Round-robin by metro in the configured order; queries that name no metro come last."""
    by_metro: dict[int, list[str]] = defaultdict(list)
    generic: list[str] = []
    for query in queries:
        index = query_metro(query, metros)
        (generic if index is None else by_metro[index]).append(query)
    ordered: list[str] = []
    for round_ in range(max((len(v) for v in by_metro.values()), default=0)):
        for index in sorted(by_metro):
            if round_ < len(by_metro[index]):
                ordered.append(by_metro[index][round_])
    return ordered + generic


# -- pages -----------------------------------------------------------------------


def _interleave(results_per_query: list[list[str]]) -> list[tuple[int, str]]:
    """(query index, URL) taking the first result of every query, then the second, and so on.
    A URL is kept only where it first comes up."""
    seen: set[str] = set()
    out: list[tuple[int, str]] = []
    for round_ in range(max((len(r) for r in results_per_query), default=0)):
        for query_index, results in enumerate(results_per_query):
            if round_ < len(results) and results[round_] not in seen:
                seen.add(results[round_])
                out.append((query_index, results[round_]))
    return out


def reading_order(results_per_query: list[list[str]]) -> list[str]:
    return [url for _, url in _interleave(results_per_query)]


@dataclass
class PageSelection:
    pages: list[tuple[int, str]] = field(default_factory=list)  # (query index, URL), in reading order
    over_total: int = 0
    over_site: int = 0
    over_query: int = 0


def select_pages(results_per_query: list[list[str]], *, total: int, per_query: int, per_site: int) -> PageSelection:
    """The pages to read, round-robin, within the run total and the per-site and per-query caps.

    A skipped result does not stop reading; later results of other sites and queries are still read.
    """
    selection = PageSelection()
    by_site: Counter[str] = Counter()
    by_query: Counter[int] = Counter()
    for query_index, url in _interleave(results_per_query):
        site = domain_key(url)
        if len(selection.pages) >= total:
            selection.over_total += 1
        elif by_site[site] >= per_site:
            selection.over_site += 1
        elif by_query[query_index] >= per_query:
            selection.over_query += 1
        else:
            selection.pages.append((query_index, url))
            by_site[site] += 1
            by_query[query_index] += 1
    return selection


# -- candidates ------------------------------------------------------------------


def location_on_page(location: str | None, text: str) -> bool:
    return bool(location and location.strip()) and normalize(location or "") in normalize(text)


def classify_metro(location: str | None, text: str, model_value: str, metros: list[Metro]) -> MetroMatch:
    """`text` is the entry's excerpt (listing) or the page text (homepage). A location that is not in
    it is ignored; one that reads as a place is classified by the headquarters rules (research R5)."""
    if not location_on_page(location, text):
        return "unknown"
    city, state = parse_city_state(location or "")
    if state is not None:
        status = location_status(city, state, metros)
        if status != "unknown":
            return "in" if status == "met" else "out"
    return model_value if model_value in _METRO_ORDER else "unknown"  # type: ignore[return-value]


@dataclass(frozen=True)
class CandidateMatch:
    key: str  # company key
    page_index: int  # position of its source page in reading order
    has_website: bool
    metroMatch: MetroMatch
    positionMatch: PositionMatch

    def tier(self) -> tuple[int, int, int]:
        return (_METRO_ORDER[self.metroMatch], _POSITION_ORDER[self.positionMatch], 0 if self.has_website else 1)


def _key_hash(candidate: CandidateMatch) -> str:
    return hashlib.sha256(candidate.key.encode("utf-8")).hexdigest()


def rank_candidates(candidates: list[CandidateMatch]) -> list[CandidateMatch]:
    """Best match first. Ties alternate between source pages in reading order, and within a page
    follow the SHA-256 of the company key, so neither page order nor the alphabet decides."""
    by_tier: dict[tuple[int, int, int], dict[int, list[CandidateMatch]]] = defaultdict(lambda: defaultdict(list))
    for candidate in candidates:
        by_tier[candidate.tier()][candidate.page_index].append(candidate)
    ranked: list[CandidateMatch] = []
    for tier in sorted(by_tier):
        pages = [sorted(group, key=_key_hash) for _, group in sorted(by_tier[tier].items())]
        for round_ in range(max(len(group) for group in pages)):
            ranked.extend(group[round_] for group in pages if round_ < len(group))
    return ranked
