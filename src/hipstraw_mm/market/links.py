"""Link verification helpers (Search & Research, right `verify_link`)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from hipstraw_mm.market.router import Check

Doc = dict[str, Any]
MIN_RATIONALE_WORDS = 3


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


def link_checks(result: Any, tier: str, *, chunk: list[Doc]) -> list[Check]:
    """Validators for one link_verification.v1 answer (rubric: config/validation.yaml)."""
    labels = {(link["fromNodeId"], link["toNodeId"]): f"{link['fromLabel']} → {link['toLabel']}" for link in chunk}

    def name(pair: tuple[str, str]) -> str:
        return labels.get(pair, f"{pair[0]} → {pair[1]}")

    returned = [(entry.fromNodeId, entry.toNodeId) for entry in result.links]
    counts = Counter(returned)
    missing = [name(p) for p in labels if p not in counts]
    repeated = [name(p) for p, n in counts.items() if n > 1 and p in labels]
    unknown = [name(p) for p in counts if p not in labels]
    covered = not (missing or repeated or unknown)
    problems = [f"{len(missing)} missing" if missing else "", f"{len(repeated)} repeated" if repeated else "",
                f"{len(unknown)} unknown" if unknown else ""]
    short = [name((e.fromNodeId, e.toNodeId)) for e in result.links
             if len(e.rationale.split()) < MIN_RATIONALE_WORDS]
    return [
        Check("coverage", covered, True,
              "every link answered once" if covered else "links " + ", ".join(p for p in problems if p),
              {"expected": len(labels), "returned": len(returned), "missing": missing, "repeated": repeated,
               "unknown": unknown}),
        Check("rationale", not short, True,
              "every verdict has a reason" if not short
              else f"{len(short)} verdict(s) with fewer than {MIN_RATIONALE_WORDS} words of reason",
              {"short": len(short), "links": short[:10], "minWords": MIN_RATIONALE_WORDS}),
    ]
