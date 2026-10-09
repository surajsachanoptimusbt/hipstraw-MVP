"""Pure structural validation of a seed graph (no I/O, no model call).

The graph is a dict with `nodes`, `edges`, and optionally `unresolved` (items with a `level`) and
`metrosInForce`. Each violation is a dict with `nodeId` or `edgeId`, `rule`, and `reason`.
"""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market.meaning import GraphMeaning


def edge_id(edge: dict[str, Any]) -> str:
    return str(edge.get("edgeId") or f"{edge.get('fromNodeId')}->{edge.get('toNodeId')}")


def _node_violation(node_id: Any, rule: str, reason: str) -> dict[str, Any]:
    return {"nodeId": node_id, "rule": rule, "reason": reason}


def _edge_violation(edge: dict[str, Any], rule: str, reason: str) -> dict[str, Any]:
    return {"edgeId": edge_id(edge), "rule": rule, "reason": reason}


def validate_graph_structure(graph: dict[str, Any], meaning: GraphMeaning) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = list(graph.get("nodes", []))
    edges: list[dict[str, Any]] = list(graph.get("edges", []))
    unresolved: list[dict[str, Any]] = list(graph.get("unresolved", []))
    metros = graph.get("metrosInForce")

    order = {lv.level: i for i, lv in enumerate(meaning.levels)}
    violations: list[dict[str, Any]] = []

    # duplicate node IDs
    seen: set[str] = set()
    reported_dups: set[str] = set()
    for n in nodes:
        nid = str(n.get("nodeId"))
        if nid in seen and nid not in reported_dups:
            reported_dups.add(nid)
            violations.append(_node_violation(nid, "duplicate_node_id", f"node ID {nid!r} appears more than once"))
        seen.add(nid)

    by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        by_id.setdefault(str(n.get("nodeId")), n)

    # undefined level
    for nid, n in by_id.items():
        if n.get("level") not in order:
            violations.append(_node_violation(nid, "undefined_level", f"level {n.get('level')!r} is not defined"))

    # edges
    touched: set[str] = set()
    for e in edges:
        src, dst = str(e.get("fromNodeId")), str(e.get("toNodeId"))
        missing = [x for x in (src, dst) if x not in by_id]
        if missing:
            violations.append(
                _edge_violation(e, "dangling_edge", f"endpoint(s) not in graph: {', '.join(missing)}")
            )
            for x in (src, dst):
                touched.add(x)
            continue
        touched.update((src, dst))
        a, b = order.get(str(by_id[src].get("level"))), order.get(str(by_id[dst].get("level")))
        if a is None or b is None:
            continue
        if b <= a:
            violations.append(_edge_violation(e, "reversed_level", "edge does not go to a deeper level"))
        elif b - a > 1:
            violations.append(_edge_violation(e, "skipped_level", f"edge skips {b - a - 1} level(s)"))

    # orphans
    for nid in by_id:
        if nid not in touched:
            violations.append(_node_violation(nid, "orphan_node", "node has no edges"))

    # mandatory filters
    filter_ids = {f.id for f in meaning.mandatoryFilters}
    for nid, n in by_id.items():
        if "metro_in_force" in filter_ids and n.get("level") == "segment":
            node_metros = n.get("metroIds") or []
            ok = bool(node_metros) and (metros is None or any(m in set(metros) for m in node_metros))
            if not ok:
                violations.append(_node_violation(nid, "metro_in_force", "segment has no metro in force"))
        if "no_enterprise" in filter_ids and n.get("level") == "archetype" and n.get("sizeBand") == "enterprise":
            violations.append(_node_violation(nid, "no_enterprise", "enterprise archetype is excluded"))

    # empty levels
    populated = {n.get("level") for n in nodes}
    explained = {u.get("level") for u in unresolved}
    for lv in meaning.levels:
        if lv.level not in populated and lv.level not in explained:
            violations.append(
                _node_violation(None, "empty_level", f"level {lv.level!r} has no nodes and no unresolved item")
                | {"level": lv.level}
            )

    violations.sort(key=lambda v: (str(v.get("nodeId") or ""), str(v.get("edgeId") or ""), v["rule"], v["reason"]))
    return violations
