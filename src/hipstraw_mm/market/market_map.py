"""The market map: every micro market the beam reached, sized by economics and coloured by position.

A tile is one micro market: a complete path (segment -> use case) scored at the deepest beam level,
grouped by its segment. Final paths were researched and carry a committed Market Position; the rest
were screened by search score and economics only, which the tile says. Size is the Position &
Evaluation economic estimate (a hypothesis with its assumptions). Change is computed against the
program's previous market map by label similarity.
"""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market.evaluation import economic_midpoint, match_prior

Doc = dict[str, Any]


def build_market_map(
    run: Doc,
    deepest_level: Doc | None,
    economics: dict[str, Doc],
    positions_by_path: dict[str, Doc],
    cases_by_path: dict[str, Doc],
    previous_map: Doc | None,
    at: str,
) -> Doc:
    prior_tiles = (previous_map or {}).get("tiles", [])
    tiles: list[Doc] = []
    for cand in (deepest_level or {}).get("scored", []):
        labels = cand.get("nodeLabels") or [p.strip() for p in str(cand.get("label", "")).split(" > ") if p.strip()]
        if not labels:
            continue
        est = economics.get(cand["pathId"])
        position = positions_by_path.get(cand["pathId"])
        case = cases_by_path.get(cand["pathId"])
        prior = match_prior(labels, prior_tiles)
        score = float(cand.get("searchScore") or 0.0)
        tile: Doc = {
            "tileId": cand["pathId"],
            "pathId": cand["pathId"],
            "group": labels[0],
            "labels": labels,
            "title": " · ".join(labels[1:3]) if len(labels) > 1 else labels[0],
            "searchScore": score,
            "outcome": "final" if position else cand.get("outcome", "screened"),
            "researched": position is not None,
            "valuePoolUsdLow": (est or {}).get("valuePoolUsdLow"),
            "valuePoolUsdHigh": (est or {}).get("valuePoolUsdHigh"),
            "valueMid": economic_midpoint(est),
            "economicsBasis": (est or {}).get("unit"),
            "targetCompanyEstimate": (est or {}).get("targetCompanyEstimate"),
            "assumptions": (est or {}).get("assumptions", []),
            "sensitivities": (est or {}).get("sensitivities", []),
            "position": {
                "status": position["status"],
                "confidence": position["confidence"],
                "version": position["version"],
                "trajectory": position["trajectory"],
                "recommendation": (case or {}).get("recommendation", {}).get("recommendation"),
            } if position else None,
            "includedCompanies": ((case or {}).get("packet") or {}).get("included", 0),
            "change": _change(prior, score, position),
        }
        tiles.append(tile)
    groups: dict[str, Doc] = {}
    for t in tiles:
        g = groups.setdefault(t["group"], {"group": t["group"], "tiles": 0, "valueMid": 0.0, "researched": 0})
        g["tiles"] += 1
        g["valueMid"] += t["valueMid"] or 0.0
        g["researched"] += 1 if t["researched"] else 0
    return {
        "marketRunId": run["marketRunId"],
        "programId": run["programId"],
        "level": (deepest_level or {}).get("levelName"),
        "tiles": tiles,
        "groups": sorted(groups.values(), key=lambda g: -g["valueMid"]),
        "previousRunId": (previous_map or {}).get("marketRunId"),
        "sizeBasis": "Position & Evaluation economic estimate (annual value pool, USD midpoint) - a hypothesis",
        "colorBasis": "Market Position status for researched micro markets; screened otherwise",
        "builtAt": at,
    }


def _change(prior: Doc | None, score: float, position: Doc | None) -> Doc:
    if prior is None:
        return {"direction": "new", "matchedTileId": None}
    before = float(prior.get("searchScore") or 0.0)
    prior_status = (prior.get("position") or {}).get("status")
    status = (position or {}).get("status")
    order = {"Drop": 0, "Needs more evidence": 1, "Pursue": 2}
    if status and prior_status and order.get(status, 1) != order.get(prior_status, 1):
        direction = "up" if order.get(status, 1) > order.get(prior_status, 1) else "down"
    else:
        pp = (score - before) * 100
        direction = "up" if pp >= 1 else "down" if pp <= -1 else "flat"
    return {
        "direction": direction,
        "matchedTileId": prior.get("tileId"),
        "similarity": prior.get("similarity"),
        "searchScorePp": round((score - before) * 100, 1),
        "previousStatus": prior_status,
    }
