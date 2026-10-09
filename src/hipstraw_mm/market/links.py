"""Link verification helpers (Search & Research, right `verify_link`)."""

from __future__ import annotations

from typing import Any

Doc = dict[str, Any]


def chunk_links(links: list[Doc], chunk_size: int) -> list[list[Doc]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    return [links[i : i + chunk_size] for i in range(0, len(links), chunk_size)]


def flag_link(link: Doc, threshold: float) -> Doc:
    """Return a copy with `flagged` (True strictly below the threshold) and `threshold` recorded."""
    out = dict(link)
    out["flagged"] = float(link["linkConfidence"]) < threshold
    out["threshold"] = threshold
    return out


def link_record(link: Doc, threshold: float, step_id: str) -> Doc:
    """The stored record: rationale, linkConfidence, flagged, threshold, stepId."""
    flagged = flag_link(link, threshold)
    return {
        "fromNodeId": link["fromNodeId"],
        "toNodeId": link["toNodeId"],
        "rationale": link["rationale"],
        "linkConfidence": link["linkConfidence"],
        "flagged": flagged["flagged"],
        "threshold": threshold,
        "stepId": step_id,
    }


def check_link_coverage(input_links: list[Doc], returned: list[Doc]) -> None:
    """Every input link must appear exactly once in the response."""
    expected = {(link["fromNodeId"], link["toNodeId"]) for link in input_links}
    seen: set[tuple[str, str]] = set()
    for link in returned:
        key = (link["fromNodeId"], link["toNodeId"])
        if key in seen:
            raise ValueError(f"response repeats link {key[0]} -> {key[1]}")
        seen.add(key)
    missing = expected - seen
    if missing:
        raise ValueError(f"response is missing {len(missing)} link(s): {sorted(missing)}")
    extra = seen - expected
    if extra:
        raise ValueError(f"response contains unknown link(s): {sorted(extra)}")
