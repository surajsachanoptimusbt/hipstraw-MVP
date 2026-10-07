"""Size signals and the parent company against the configured thresholds (research R6).

- Thresholds come from the run's constraints and are strict "less than".
- A range uses its upper bound for the "under" test and its lower bound for the "over" test.
- over: some passing signal's lower bound reaches its threshold; under: some upper bound is below it;
  both: conflict (the values are kept as separate signals, FR-010); neither: unknown.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from hipstraw_mm.evidence.excerpt_check import normalize
from hipstraw_mm.models import normalize_company_name

SizeKind = Literal["employees", "revenue"]
SizeStatus = Literal["under", "over", "conflict", "unknown"]

_NUMBER = r"(\d[\d,]*(?:\.\d+)?)"
_SCALE = r"\s*(k|thousand|m|mm|million|bn|b|billion)?\b"
_SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "bn": 1e9, "b": 1e9, "billion": 1e9}
_RANGE = re.compile(_NUMBER + _SCALE + r"\s*(?:-|to)\s*\$?" + _NUMBER + _SCALE)
_AT_LEAST = re.compile(
    r"(?:over|more than|at least|above)\s+\$?" + _NUMBER + _SCALE + r"|" + _NUMBER + _SCALE + r"\s*\+"
)
_BELOW = re.compile(r"(?:under|less than|fewer than|below|up to)\s+\$?" + _NUMBER + _SCALE)
_SINGLE = re.compile(_NUMBER + _SCALE)


def _amount(number: str, scale: str | None) -> float:
    return float(number.replace(",", "")) * _SCALES.get(scale or "", 1.0)


def parse_size(value: str) -> tuple[float | None, float | None] | None:
    """`"51-200"` -> (51, 200); `"5,000+"` -> (5000, None); `"$20 million"` -> (2e7, 2e7); else None."""
    text = normalize(value)
    if m := _RANGE.search(text):
        low_scale = m.group(2) or m.group(4)  # "$10-20 million": the scale applies to both ends
        return _amount(m.group(1), low_scale), _amount(m.group(3), m.group(4))
    if m := _AT_LEAST.search(text):
        number, scale = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        return _amount(number, scale), None
    if m := _BELOW.search(text):
        return None, _amount(m.group(1), m.group(2))
    if m := _SINGLE.search(text):
        amount = _amount(m.group(1), m.group(2))
        return amount, amount
    return None


def evaluate_size(claims: list[tuple[str, str, str]], max_employees: int, max_revenue_usd: int) -> dict[str, Any]:
    """`claims` are passing size citations as (kind, claimValue, evidenceId); kind is employees or revenue."""
    thresholds = {"employees": max_employees, "revenue": max_revenue_usd}
    signals = []
    over = under = False
    for kind, value, evidence_id in claims:
        parsed = parse_size(value)
        if parsed is None:
            continue
        low, high = parsed
        signals.append({"kind": kind, "low": low, "high": high, "evidenceId": evidence_id})
        over = over or (low is not None and low >= thresholds[kind])
        under = under or (high is not None and high < thresholds[kind])
    status: SizeStatus = "conflict" if over and under else "over" if over else "under" if under else "unknown"
    return {"signals": signals, "status": status}


def evaluate_parent(
    parents: list[tuple[str, str]],
    parent_sizes: list[tuple[str, str, str]],
    large_parents: list[str],
    max_employees: int,
    max_revenue_usd: int,
) -> dict[str, Any] | None:
    """`parents` are passing parent claims as (name, evidenceId); `parent_sizes` passing claims about
    the parent's size as (employees | revenue, value, evidenceId). None when there is no parent.

    large: the parent is on `largeEnterpriseParents` (normalized name), or some size figure reaches a
    threshold; small: its figures are all under both; unknown_size: no figure.
    """
    if not parents:
        return None
    listed = {normalize_company_name(name) for name in large_parents}
    size = evaluate_size(parent_sizes, max_employees, max_revenue_usd)
    if any(normalize_company_name(name) in listed for name, _ in parents) or size["status"] in ("over", "conflict"):
        status = "large"
    elif size["status"] == "under":
        status = "small"
    else:
        status = "unknown_size"
    evidence_ids = list(dict.fromkeys([e for _, e in parents] + [e for _, _, e in parent_sizes]))
    return {"name": parents[0][0], "evidenceIds": evidence_ids, "status": status}
