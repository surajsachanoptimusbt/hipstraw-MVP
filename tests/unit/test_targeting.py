"""T077: discovery targeting (FR-022, research R19, added after the first live run on 2026-10-07).

In `run_20261007T140925` all 10 kept companies came from one alphabetical directory page, in page
order. These tests pin the three fixes: metro-ordered queries, round-robin result reading, and
ranking by match to the first position before the cap.
"""

from __future__ import annotations

import hashlib
import random

from hipstraw_mm.steps.targeting import (
    CandidateMatch,
    classify_metro,
    order_queries,
    rank_candidates,
    reading_order,
    select_pages,
)


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _c(key: str, metro: str = "in", position: str = "strong", *, page: int = 0, website: bool = True) -> CandidateMatch:
    return CandidateMatch(key=key, page_index=page, has_website=website, metroMatch=metro, positionMatch=position)


class TestOrderQueries:
    def test_round_robin_by_metro_in_configured_order_with_metro_less_queries_last(self, metros):
        planned = [
            "software companies A to Z",
            "Atlanta B2B SaaS startups",
            "Marietta fintech companies",
            "San Francisco SaaS startups",
            "Jersey City software firms",
            "best SaaS tools 2026",
        ]
        assert order_queries(planned, metros) == [
            "Atlanta B2B SaaS startups",
            "San Francisco SaaS startups",
            "Jersey City software firms",
            "Marietta fintech companies",
            "software companies A to Z",
            "best SaaS tools 2026",
        ]

    def test_places_match_as_whole_words_ignoring_case(self, metros):
        # "Atlantic" is not "Atlanta"; "brooklyn" is Brooklyn.
        assert order_queries(["Atlantic coast SaaS", "brooklyn startups"], metros) == [
            "brooklyn startups",
            "Atlantic coast SaaS",
        ]

    def test_nothing_is_dropped(self, metros):
        planned = ["generic one", "generic two"]
        assert order_queries(planned, metros) == planned


class TestReadingOrder:
    def test_results_are_read_round_robin_across_queries(self):
        per_query = [["a1", "a2", "a3"], ["b1"], ["c1", "c2"]]
        assert reading_order(per_query) == ["a1", "b1", "c1", "a2", "c2", "a3"]

    def test_a_repeated_url_is_read_once_where_it_first_comes_up(self):
        per_query = [["a1", "a2"], ["a1", "b2"]]
        assert reading_order(per_query) == ["a1", "a2", "b2"]

    def test_no_results(self):
        assert reading_order([[], []]) == []


class TestSelectPages:
    """Added at the T051 review: listing pages are capped per site and per query, so one directory
    cannot use up the page budget and leave other queries' results unread."""

    PER_QUERY = [
        [f"https://dir.test/a-z?page={n}" for n in (1, 2, 3, 4)],
        ["https://atl.test/list", "https://atl2.test/list", "https://atl3.test/list", "https://atl4.test/list"],
        ["https://dir.test/sf"],
    ]

    def test_a_site_or_query_at_its_cap_is_skipped_and_reading_continues(self):
        selection = select_pages(self.PER_QUERY, total=12, per_query=3, per_site=2)
        assert selection.pages == [
            (0, "https://dir.test/a-z?page=1"),
            (1, "https://atl.test/list"),
            (2, "https://dir.test/sf"),
            (1, "https://atl2.test/list"),
            (1, "https://atl3.test/list"),
        ]
        assert (selection.over_site, selection.over_query, selection.over_total) == (3, 1, 0)

    def test_the_run_total_still_applies(self):
        selection = select_pages(self.PER_QUERY, total=2, per_query=3, per_site=2)
        assert selection.pages == [(0, "https://dir.test/a-z?page=1"), (1, "https://atl.test/list")]
        assert selection.over_total == 7

    def test_a_url_found_by_two_queries_is_read_once_for_the_first(self):
        selection = select_pages(
            [["https://a.test/x"], ["https://a.test/x", "https://b.test/y"]], total=12, per_query=3, per_site=3
        )
        assert selection.pages == [(0, "https://a.test/x"), (1, "https://b.test/y")]


class TestClassifyMetro:
    EXCERPT_ATLANTA = "Agate Billing: subscription billing SaaS for B2B companies. HQ Atlanta, GA."

    def test_location_not_in_the_text_is_unknown_whatever_the_model_says(self, metros):
        excerpt = "Nimbus Ledger: AP automation SaaS for mid-sized companies."
        assert classify_metro("Atlanta, GA", excerpt, "in", metros) == "unknown"

    def test_no_location_is_unknown(self, metros):
        assert classify_metro(None, self.EXCERPT_ATLANTA, "in", metros) == "unknown"

    def test_a_listed_city_is_in_even_if_the_model_says_otherwise(self, metros):
        assert classify_metro("Atlanta, GA", self.EXCERPT_ATLANTA, "out", metros) == "in"

    def test_a_cited_place_outside_the_metros_is_out_overriding_the_model(self, metros):
        excerpt = "Acorn Freight: trucking marketplace for shippers. HQ Buffalo, NY."
        assert classify_metro("Buffalo, NY", excerpt, "in", metros) == "out"
        assert classify_metro("Dallas, TX", "Aardvark Rides. HQ Dallas, TX.", "in", metros) == "out"

    def test_a_full_state_name_is_read(self, metros):
        assert classify_metro("Austin, Texas", "Abacus Arcade. HQ Austin, Texas.", "unknown", metros) == "out"

    def test_an_unparseable_location_keeps_the_model_value(self, metros):
        excerpt = "Pier Labs: billing tools, based in the Bay Area."
        assert classify_metro("Bay Area", excerpt, "in", metros) == "in"
        assert classify_metro("Bay Area", excerpt, "unknown", metros) == "unknown"

    def test_the_location_check_ignores_case_and_spacing(self, metros):
        assert classify_metro("atlanta,  ga", self.EXCERPT_ATLANTA, "unknown", metros) == "in"


class TestRankCandidates:
    def test_metro_then_position_then_website(self):
        page = [
            _c("aardvark", "out", "weak"),
            _c("abacus", "out", "partial"),
            _c("adder", "unknown", "strong"),
            _c("agate", "in", "strong"),
            _c("albatross", "unknown", "weak"),
            _c("birch", "in", "partial"),
            _c("cobalt", "in", "weak"),
            _c("zeta-registry", "in", "strong", website=False),
        ]
        ranked = [c.key for c in rank_candidates(page)]
        assert ranked == ["agate", "zeta-registry", "birch", "cobalt", "adder", "albatross", "abacus", "aardvark"]

    def test_an_alphabetical_page_is_not_kept_in_page_order(self):
        keys = ["alder-ap", "aspen-bill", "beech-ledger", "cedar-spend", "elm-invoice", "fir-procure"]
        ranked = [c.key for c in rank_candidates([_c(k) for k in keys])]
        assert ranked == sorted(keys, key=_sha)  # ties on one page follow the SHA-256 of the key
        assert ranked != keys

    def test_ties_alternate_between_source_pages_in_reading_order(self):
        first = sorted(["p1-a", "p1-b", "p1-c"], key=_sha)
        second = sorted(["p2-a", "p2-b"], key=_sha)
        candidates = [_c(k, page=0) for k in first] + [_c(k, page=1) for k in second]
        ranked = [c.key for c in rank_candidates(candidates)]
        assert ranked == [first[0], second[0], first[1], second[1], first[2]]

    def test_the_result_does_not_depend_on_input_order(self):
        candidates = [
            _c("k1", "in", "strong", page=0),
            _c("k2", "in", "strong", page=1),
            _c("k3", "unknown", "strong", page=0),
            _c("k4", "in", "partial", page=2),
            _c("k5", "out", "strong", page=1),
            _c("k6", "in", "strong", page=0),
        ]
        expected = rank_candidates(candidates)
        shuffled = candidates[:]
        random.Random(7).shuffle(shuffled)
        assert rank_candidates(shuffled) == expected
