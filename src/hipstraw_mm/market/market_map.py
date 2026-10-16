"""The market map: every market unit opportunity ranking reached, sized by economics, coloured by Disposition.

A tile is one market unit: a complete path (segment -> use case) scored at the deepest ranking level,
grouped by its segment. Final market units were researched and carry a committed Market Position with
a playbook Disposition; the rest were screened by search score and economics only, which the tile
says. Size is the Position & Evaluation economic estimate (a hypothesis with its assumptions). Change
is computed against the program's previous market map by label similarity.
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
    order: list[str],
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
                "disposition": position["disposition"],
                "attention": position["attention"],
                "confidence": position["confidence"],
                "version": position["version"],
                "trajectory": position["trajectory"],
                "play": position.get("play"),
                "nextStep": (position.get("nextStep") or {}).get("id"),
                "recommendation": (case or {}).get("recommendation", {}).get("recommendation"),
            } if position else None,
            "includedCompanies": ((case or {}).get("packet") or {}).get("included", 0),
            "change": _change(prior, score, position, order),
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
        "colorBasis": "Disposition of the committed Market Position for researched market units; screened otherwise",
        "builtAt": at,
    }


def _change(prior: Doc | None, score: float, position: Doc | None, order: list[str]) -> Doc:
    if prior is None:
        return {"direction": "new", "matchedTileId": None}
    before = float(prior.get("searchScore") or 0.0)
    prior_status = (prior.get("position") or {}).get("disposition")
    status = (position or {}).get("disposition")
    if status in order and prior_status in order and status != prior_status:
        direction = "up" if order.index(status) > order.index(prior_status) else "down"
    else:
        pp = (score - before) * 100
        direction = "up" if pp >= 1 else "down" if pp <= -1 else "flat"
    return {
        "direction": direction,
        "matchedTileId": prior.get("tileId"),
        "similarity": prior.get("similarity"),
        "searchScorePp": round((score - before) * 100, 1),
        "previousDisposition": prior_status,
    }
