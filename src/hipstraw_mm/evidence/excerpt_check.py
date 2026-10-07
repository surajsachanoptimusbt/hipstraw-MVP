"""Citation check: exact excerpt match after typographic normalization (research R4, FR-007, FR-018)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hipstraw_mm.evidence.states import STATE_NAMES, state_code

MAX_EXCERPT_CHARS = 300
WITHHELD_EXCERPT = "[withheld: contact data]"

_TYPOGRAPHY = str.maketrans(
    {
        "‘": "'",  # left single quote
        "’": "'",  # right single quote / apostrophe
        "‚": "'",  # single low-9 quote
        "‛": "'",  # single high-reversed-9 quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "„": '"',  # double low-9 quote
        "‟": '"',  # double high-reversed-9 quote
        "–": "-",  # en dash
        "—": "-",  # em dash
        " ": " ",  # no-break space
        " ": " ",  # narrow no-break space
        " ": " ",  # figure space (non-breaking)
    }
)
_WHITESPACE = re.compile(r"\s+")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# North American numbers need separators between groups, so counts like "1000000000" never match.
_PHONE = re.compile(
    r"(?<![\d.])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\d)"
    r"|\+\d{1,3}(?:[\s.-]\d{2,4}){2,4}(?!\d)"
)


@dataclass(frozen=True)
class CheckResult:
    status: str  # "pass" or "fail"
    reason: str | None  # None on pass

    def to_dict(self) -> dict[str, str | None]:
        return {"status": self.status, "reason": self.reason}


def normalize(text: str) -> str:
    """Quotes, dashes and non-breaking spaces unified, then casefold and collapsed whitespace."""
    return _WHITESPACE.sub(" ", text.translate(_TYPOGRAPHY).casefold()).strip()


def contains_contact_data(text: str) -> bool:
    return bool(_EMAIL.search(text) or _PHONE.search(text.translate(_TYPOGRAPHY)))


def value_variants(claim_value: str, claim_field: str | None) -> list[str]:
    """The ways a claimed value may be written. For a headquarters claim, a state's code and its full
    name are equal ("Addison, TX" = "Addison, Texas", FR-007, 2026-10-07); nothing else is relaxed."""
    if claim_field != "hq" or "," not in claim_value:
        return [claim_value]
    city, _, state_text = claim_value.rpartition(",")
    code = state_code(state_text)
    if code is None or not city.strip():
        return [claim_value]
    return [claim_value, f"{city.strip()}, {code}", f"{city.strip()}, {STATE_NAMES[code]}"]


def check_excerpt(
    excerpt: str, page_text: str, claim_value: str | None = None, *, claim_field: str | None = None
) -> CheckResult:
    """Pass only if the excerpt appears in the page text and, for structured claims, holds the value."""
    if not excerpt or not excerpt.strip():
        return CheckResult("fail", "excerpt_not_found")
    if len(excerpt) > MAX_EXCERPT_CHARS:
        return CheckResult("fail", "excerpt_too_long")
    if contains_contact_data(excerpt):
        return CheckResult("fail", "contains_contact_data")
    normalized_excerpt = normalize(excerpt)
    if normalized_excerpt not in normalize(page_text):
        return CheckResult("fail", "excerpt_not_found")
    if claim_value is not None:
        variants = [normalize(v) for v in value_variants(claim_value, claim_field)]
        if not variants[0] or not any(v in normalized_excerpt for v in variants):
            return CheckResult("fail", "value_not_in_excerpt")
    return CheckResult("pass", None)
