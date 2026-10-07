"""T046: headquarters matching against the CSA metros (research R5, revised 2026-10-07).

Since the first live run, a cited city that is not on its state's place list is outside the metros
(`not_met`), not `unknown`; unknown is kept for a missing citation or one that names no city inside a
metro's state. The place lists are keyed by state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hipstraw_mm.config import load_metro_config
from hipstraw_mm.evidence.location import evaluate_hq, location_status, parse_city_state

REAL_METROS = Path(__file__).resolve().parents[2] / "config" / "metros.yaml"


class TestParse:
    def test_city_and_state_code(self):
        assert parse_city_state("Atlanta, GA") == ("Atlanta", "GA")

    def test_trailing_country_is_ignored(self):
        assert parse_city_state("Palo Alto, CA, USA") == ("Palo Alto", "CA")

    def test_full_state_name_is_read_as_its_code(self):
        assert parse_city_state("Austin, Texas") == ("Austin", "TX")
        assert parse_city_state("Addison, Texas") == ("Addison", "TX")

    def test_state_alone(self):
        assert parse_city_state("Texas") == (None, "TX")
        assert parse_city_state("California") == (None, "CA")

    def test_no_place_at_all(self):
        assert parse_city_state("Bay Area") == (None, None)


class TestLocationStatus:
    def test_listed_city_with_matching_state_is_met(self, metros):
        assert location_status("Atlanta", "GA", metros) == "met"

    def test_palo_alto_is_met_because_the_csa_is_the_wider_region(self, metros):
        assert location_status("Palo Alto", "CA", metros) == "met"

    def test_state_outside_every_metro_is_not_met(self, metros):
        assert location_status("Dallas", "TX", metros) == "not_met"

    def test_unlisted_city_in_a_metro_state_is_not_met(self, metros):
        # Changed on 2026-10-07: Buffalo is in New York State but outside the New York CSA.
        assert location_status("Buffalo", "NY", metros) == "not_met"

    def test_a_place_is_matched_within_its_own_state(self, metros):
        assert location_status("Springfield", "NJ", metros) == "met"
        assert location_status("Springfield", "PA", metros) == "not_met"
        assert location_status("Newark", "CA", metros) == "met"
        assert location_status("Newark", "NJ", metros) == "met"

    def test_matching_ignores_letter_case(self, metros):
        assert location_status("jersey city", "NJ", metros) == "met"

    def test_state_alone_inside_a_metro_is_unknown(self, metros):
        assert location_status(None, "CA", metros) == "unknown"

    def test_state_alone_outside_every_metro_is_not_met(self, metros):
        assert location_status(None, "TX", metros) == "not_met"

    def test_nothing_is_unknown(self, metros):
        assert location_status(None, None, metros) == "unknown"


class TestEvaluateHq:
    def test_no_citation_is_unknown(self, metros):
        assert evaluate_hq([], metros) == {"city": None, "state": None, "status": "unknown", "evidenceIds": []}

    def test_cited_buffalo_is_not_met(self, metros):
        hq = evaluate_hq([("Buffalo, NY", "ev1")], metros)
        assert hq == {"city": "Buffalo", "state": "NY", "status": "not_met", "evidenceIds": ["ev1"]}

    def test_cited_full_state_name_outside_is_not_met(self, metros):
        assert evaluate_hq([("Austin, Texas", "ev1")], metros)["status"] == "not_met"

    def test_value_naming_no_city_in_a_metro_state_is_unknown(self, metros):
        assert evaluate_hq([("California", "ev1")], metros)["status"] == "unknown"
        assert evaluate_hq([("Bay Area", "ev1")], metros)["status"] == "unknown"

    def test_state_alone_outside_every_metro_is_not_met(self, metros):
        assert evaluate_hq([("Texas", "ev1")], metros)["status"] == "not_met"
        assert evaluate_hq([("Illinois", "ev1")], metros)["status"] == "not_met"

    @pytest.mark.parametrize("value", ["New York", "Georgia", "Alabama", "Pennsylvania", "Connecticut", "NJ"])
    def test_state_alone_with_some_part_in_a_metro_is_unknown(self, metros, value):
        # Approved at the T051 review: "New York" alone stays unknown (city or state, either way).
        assert evaluate_hq([(value, "ev1")], metros)["status"] == "unknown"

    def test_all_citations_inside_is_met(self, metros):
        hq = evaluate_hq([("Atlanta, GA", "ev1"), ("Marietta, GA", "ev2")], metros)
        assert hq["status"] == "met"
        assert hq["evidenceIds"] == ["ev1", "ev2"]

    def test_inside_and_outside_together_is_a_conflict(self, metros):
        hq = evaluate_hq([("Atlanta, GA", "ev1"), ("Austin, TX", "ev2")], metros)
        assert hq["status"] == "conflict"
        assert hq["evidenceIds"] == ["ev1", "ev2"]

    def test_an_unknown_citation_does_not_override_a_placed_one(self, metros):
        assert evaluate_hq([("Atlanta, GA", "ev1"), ("Bay Area", "ev2")], metros)["status"] == "met"
        assert evaluate_hq([("Dallas, TX", "ev1"), ("California", "ev2")], metros)["status"] == "not_met"

    def test_city_and_state_come_from_the_first_placed_citation(self, metros):
        hq = evaluate_hq([("Bay Area", "ev1"), ("Oakland, CA", "ev2")], metros)
        assert (hq["city"], hq["state"]) == ("Oakland", "CA")


@pytest.fixture(scope="module")
def real_metros():
    return load_metro_config(REAL_METROS).metros


class TestRealPlaceLists:
    """The real config/metros.yaml must name every place in each CSA, because an unlisted city now
    excludes a company (T052 generates the lists from the Census files)."""

    @pytest.mark.parametrize(
        ("city", "state"),
        [
            ("Cumming", "GA"),
            ("Buford", "GA"),
            ("Menlo Park", "CA"),
            ("Redwood City", "CA"),
            ("Napa", "CA"),
            ("Morristown", "NJ"),
            ("Montclair", "NJ"),
            ("Greenwich", "CT"),
            ("Brooklyn", "NY"),
        ],
    )
    def test_places_inside_the_csas_are_listed(self, real_metros, city, state):
        assert location_status(city, state, real_metros) == "met"

    @pytest.mark.parametrize(
        ("city", "state"),
        [("Buffalo", "NY"), ("Sacramento", "CA"), ("Savannah", "GA"), ("Philadelphia", "PA"), ("Hartford", "CT")],
    )
    def test_places_outside_the_csas_are_not_listed(self, real_metros, city, state):
        assert location_status(city, state, real_metros) == "not_met"

    def test_every_metro_lists_counties_and_places_for_each_of_its_states(self, real_metros):
        for metro in real_metros:
            assert set(metro.counties) == set(metro.states), metro.id
            assert set(metro.places) == set(metro.states), metro.id
            assert all(metro.places[state] for state in metro.states), metro.id
