"""Beam search helpers: scoring, filtering, diversity, keep-top (Search & Research layer).

A candidate is a dict with at least `pathId`; scored candidates also carry `searchScore`. The search
score is a hypothesis about where to look next. It is never evidence and never called a confidence.
"""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market.schemas import GRAPH_LEVELS

FACTOR_NAMES = ("relevance", "feasibility", "timing", "cost")
_DIVERSITY_FROM = GRAPH_LEVELS.index("problem")


def _factor_value(factor: Any) -> float:
    if isinstance(factor, dict):
        return float(factor["value"])
    return float(factor)


def compute_search_score(factors: dict[str, Any], weights: dict[str, float]) -> float:
    """Weighted mean of the factors; weights are normalized and default to equal."""
    if not factors:
        return 0.0
    raw = {name: float(weights.get(name, 1.0)) for name in factors}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("factor weights must sum to more than zero")
    return sum(_factor_value(f) * raw[name] / total for name, f in factors.items())


def build_scored_record(
    path_id: str,
    factors: dict[str, Any],
    weights: dict[str, float],
    mean_link_confidence: float | None,
) -> dict[str, Any]:
    """The stored score: `searchScore` and per-factor value, rationale, weight. No field is named
    `confidence`; `meanLinkConfidence` sits beside the score and has no effect on it."""
    total = sum(float(weights.get(n, 1.0)) for n in factors) or 1.0
    return {
        "pathId": path_id,
        "searchScore": compute_search_score(factors, weights),
        "factors": {
            n: {
                "value": _factor_value(f),
                "rationale": f.get("rationale", "") if isinstance(f, dict) else "",
                "weight": float(weights.get(n, 1.0)) / total,
            }
            for n, f in factors.items()
        },
        "meanLinkConfidence": mean_link_confidence,
    }


def sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score descending; ties break by pathId so results are reproducible."""
    return sorted(candidates, key=lambda c: (-float(c.get("searchScore", 0.0)), str(c["pathId"])))


def filter_beam(
    candidates: list[dict[str, Any]],
    constraints: dict[str, Any],
    graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop extensions that break a mandatory constraint. Returns (passed, dropped).

    `constraints` may hold `forbiddenSizeBands` and `excludedLabels`; `graph` is
    `{"nodes": {nodeId: {label, sizeBand, ...}}}`.
    """
    nodes = graph.get("nodes", {})
    forbidden_bands = set(constraints.get("forbiddenSizeBands", []))
    excluded_labels = set(constraints.get("excludedLabels", []))
    passed: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for cand in candidates:
        node = nodes.get(cand.get("nodeId"), {})
        reason: str | None = None
        if node.get("sizeBand") in forbidden_bands:
            reason = f"size band {node['sizeBand']!r} breaks a mandatory constraint"
        elif node.get("label") in excluded_labels:
            reason = f"{node['label']!r} is excluded by a mandatory constraint"
        if reason is None:
            passed.append({**cand, "filter": {"status": "passed", "reason": None}})
        else:
            dropped.append({
                **cand,
                "filter": {"status": "dropped", "reason": reason},
                "outcome": "pruned",
                "reason": reason,
                "pathsBelow": cand.get("pathsBelow", 0),
            })
    return passed, dropped


def diversity_filter(
    candidates: list[dict[str, Any]], level: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """From the problem level on, keep at most one path per (segment, problem), best score first."""
    ordered = sort_candidates(candidates)
    if level not in GRAPH_LEVELS or GRAPH_LEVELS.index(level) < _DIVERSITY_FROM:
        return ordered, []
    seen: dict[tuple[Any, Any], str] = {}
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for cand in ordered:
        key = (cand.get("segment"), cand.get("problem"))
        first = seen.get(key)
        if first is None:
            seen[key] = str(cand["pathId"])
            kept.append({**cand, "diversity": {"status": "unique", "duplicateOf": None}})
        else:
            removed.append({
                **cand,
                "diversity": {"status": "duplicate", "duplicateOf": first},
                "outcome": "pruned",
                "reason": f"same segment and problem as {first}",
                "pathsBelow": cand.get("pathsBelow", 0),
            })
    return kept, removed


def keep_top(
    candidates: list[dict[str, Any]], width: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the top `width` by score. Fewer candidates than the width are all kept."""
    ordered = sort_candidates(candidates)
    kept = [
        {**c, "outcome": "kept", "reason": "within beam width", "rank": i + 1,
         "pathsBelow": c.get("pathsBelow", 0)}
        for i, c in enumerate(ordered[:width])
    ]
    pruned = [
        {**c, "outcome": "pruned", "reason": f"below beam width {width}", "rank": width + i + 1,
         "pathsBelow": c.get("pathsBelow", 0)}
        for i, c in enumerate(ordered[width:])
    ]
    return kept, pruned


def select_final(
    kept: list[dict[str, Any]], final_paths: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Top `final_paths` of the last level are final; the rest are deferred.

    Returns (final, deferred, finalPathShortfall or None).
    """
    ordered = sort_candidates(kept)
    final = ordered[:final_paths]
    deferred = [
        {**c, "outcome": "deferred", "reason": "below the final-path limit",
         "pathsBelow": c.get("pathsBelow", 0)}
        for c in ordered[final_paths:]
    ]
    shortfall: dict[str, Any] | None = None
    if len(final) < final_paths:
        reason = (
            "no path survived the beam" if not final
            else f"only {len(final)} path(s) survived the beam"
        )
        shortfall = {"wanted": final_paths, "found": len(final), "reason": reason}
    return final, deferred, shortfall
