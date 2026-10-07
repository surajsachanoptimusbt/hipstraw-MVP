"""Headquarters matching against the configured CSA metros (research R5, revised 2026-10-07).

Per passing citation:
- met: the city is on a metro's place list for that state;
- not_met: any other city and state (Buffalo, NY), or a state alone that has no part in any metro;
- unknown: no city and no state, or a state alone that has some part in a metro ("New York").

Across citations: met and not_met together are a conflict; otherwise any met is met, any not_met is
not_met, and no passing citation is unknown. Place lists are keyed by state and must be complete,
because an unlisted city is outside the metros.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from hipstraw_mm.config import Metro
from hipstraw_mm.evidence.states import state_code

HqStatus = Literal["met", "not_met", "conflict", "unknown"]

_COUNTRY = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}
_ZIP = re.compile(r"\s+\d{5}(?:-\d{4})?$")


def parse_city_state(value: str) -> tuple[str | None, str | None]:
    """`"Atlanta, GA"` -> `("Atlanta", "GA")`; `"Austin, Texas 78701"` -> `("Austin", "TX")`;
    `"Texas"` -> `(None, "TX")`. A trailing country is ignored. Anything else -> `(None, None)`."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) > 1 and parts[-1].casefold() in _COUNTRY:
        parts = parts[:-1]
    if not parts:
        return None, None
    state = state_code(_ZIP.sub("", parts[-1]))
    if state is None:
        return None, None
    if len(parts) == 1:
        return None, state
    return parts[-2], state


def location_status(city: str | None, state: str | None, metros: list[Metro]) -> Literal["met", "not_met", "unknown"]:
    if not state:
        return "unknown"
    in_state = [m for m in metros if state in m.states]
    if city is None:
        return "unknown" if in_state else "not_met"
    wanted = city.casefold()
    if any(wanted in {p.casefold() for p in m.places.get(state, [])} for m in in_state):
        return "met"
    return "not_met"


def evaluate_hq(claims: list[tuple[str, str]], metros: list[Metro]) -> dict[str, Any]:
    """`claims` are passing hq citations as (claimValue, evidenceId)."""
    if not claims:
        return {"city": None, "state": None, "status": "unknown", "evidenceIds": []}
    parsed = [(*parse_city_state(value), evidence_id) for value, evidence_id in claims]
    statuses = [location_status(city, state, metros) for city, state, _ in parsed]
    placed = [p for p, s in zip(parsed, statuses, strict=True) if s != "unknown"]
    city, state, _ = placed[0] if placed else parsed[0]
    status: HqStatus
    if "met" in statuses and "not_met" in statuses:
        status = "conflict"
    elif "met" in statuses:
        status = "met"
    elif "not_met" in statuses:
        status = "not_met"
    else:
        status = "unknown"
    return {"city": city, "state": state, "status": status, "evidenceIds": [e for _, _, e in parsed]}
