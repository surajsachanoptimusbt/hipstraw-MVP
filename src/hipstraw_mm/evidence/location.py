"""Headquarters matching against the configured CSA metros (research R5).

- met: the city and state are on a configured metro's lists;
- not_met: the state is outside every configured metro's states (definitive);
- unknown: the state matches but the city isn't listed, or there is no usable headquarters claim.

An unlisted city never excludes a company; it only makes the location unknown.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from hipstraw_mm.config import Metro

HqStatus = Literal["met", "not_met", "unknown"]

_STATE = re.compile(r"^[A-Za-z]{2}$")
_COUNTRY = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}


def parse_city_state(value: str) -> tuple[str | None, str | None]:
    """`"Atlanta, GA"` -> `("Atlanta", "GA")`. A trailing country is ignored. Unparseable -> (None, None)."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) > 2 and parts[-1].casefold() in _COUNTRY:
        parts = parts[:-1]
    if len(parts) < 2 or not _STATE.match(parts[-1]):
        return None, None
    return parts[-2], parts[-1].upper()


def location_status(city: str | None, state: str | None, metros: list[Metro]) -> HqStatus:
    if not state:
        return "unknown"
    in_state = [m for m in metros if state in m.states]
    if not in_state:
        return "not_met"
    if city and any(city.casefold() in {p.casefold() for p in m.places} for m in in_state):
        return "met"
    return "unknown"


def evaluate_hq(claims: list[tuple[str, str]], metros: list[Metro]) -> dict[str, Any]:
    """`claims` are passing hq citations as (claimValue, evidenceId). Disagreeing claims give unknown."""
    if not claims:
        return {"city": None, "state": None, "status": "unknown", "evidenceIds": []}
    parsed = [(*parse_city_state(value), evidence_id) for value, evidence_id in claims]
    statuses = {location_status(city, state, metros) for city, state, _ in parsed}
    city, state, _ = parsed[0]
    return {
        "city": city,
        "state": state,
        "status": statuses.pop() if len(statuses) == 1 else "unknown",
        "evidenceIds": [evidence_id for _, _, evidence_id in parsed],
    }
