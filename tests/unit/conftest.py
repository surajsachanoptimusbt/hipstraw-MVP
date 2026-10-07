"""Fixtures shared by the unit tests."""

from __future__ import annotations

import pytest

from hipstraw_mm.config import Metro


@pytest.fixture
def metros() -> list[Metro]:
    """Three small metros with state-keyed counties and places (contracts/config.md, 2026-10-07 shape).

    The place lists are short on purpose; the completeness of the real lists is tested separately.
    "Springfield" is listed for NJ only, and "Newark" for both CA and NJ, so tests can show that a
    place is matched within its own state.
    """
    return [
        Metro(
            id="atlanta",
            name="Atlanta--Athens-Clarke County--Sandy Springs, GA-AL CSA",
            csaCode="122",
            states=["GA", "AL"],
            counties={"GA": ["Fulton", "Cobb", "Forsyth"], "AL": ["Chambers"]},
            places={"GA": ["Atlanta", "Marietta", "Alpharetta", "Cumming"], "AL": ["Lanett"]},
        ),
        Metro(
            id="san_francisco",
            name="San Jose--San Francisco--Oakland, CA CSA",
            csaCode="488",
            states=["CA"],
            counties={"CA": ["San Francisco", "Alameda", "Santa Clara"]},
            places={"CA": ["San Francisco", "Oakland", "Palo Alto", "San Jose", "Newark"]},
        ),
        Metro(
            id="new_york",
            name="New York--Newark, NY-NJ-CT-PA CSA",
            csaCode="408",
            states=["NY", "NJ", "CT", "PA"],
            counties={
                "NY": ["New York", "Kings"],
                "NJ": ["Hudson", "Essex", "Union"],
                "CT": ["Fairfield"],
                "PA": ["Pike"],
            },
            places={
                "NY": ["New York", "Brooklyn", "Yonkers"],
                "NJ": ["Jersey City", "Newark", "Hoboken", "Springfield"],
                "CT": ["Stamford", "Greenwich"],
                "PA": ["Milford"],
            },
        ),
    ]
