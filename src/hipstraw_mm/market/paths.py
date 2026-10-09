"""Pure path helpers: path IDs, path counting by dynamic programming, constraints, status rules."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

Doc = dict[str, Any]

STATUSES = ("kept", "pruned", "deferred", "final", "has_evidence", "no_evidence_found")


def path_id(node_ids: list[str]) -> str:
    """Deterministic ID: node IDs joined with '>' hashed to 8 hex characters."""
    return hashlib.sha256(">".join(node_ids).encode("utf-8")).hexdigest()[:8]


def paths_below(
    edges: list[Doc],
    level_order: list[str],
    node_levels: dict[str, str],
    target_nodes: set[str],
) -> int:
    """Count complete paths (down to the last level) that start at any node in `target_nodes`.

    Dynamic programming over edges, one level at a time from the bottom; never lists the paths.
    """
    if not level_order:
        return 0
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e["fromNodeId"]].append(e["toNodeId"])
    counts: dict[str, int] = {}
    by_level: dict[str, list[str]] = defaultdict(list)
    for node, lvl in node_levels.items():
        by_level[lvl].append(node)
    for node in by_level[level_order[-1]]:
        counts[node] = 1
    for lvl in reversed(level_order[:-1]):
        for node in by_level[lvl]:
            counts[node] = sum(counts.get(c, 0) for c in children.get(node, []))
    return sum(counts.get(n, 0) for n in target_nodes)


def check_path_constraints(path_nodes: list[Doc], constraints: Doc) -> Doc | None:
    """Return {"constraint", "nodeId"} for the first broken constraint, or None.

    Constraints: `excludedArchetypes` (labels), `allowedMetroIds`, `allowedSizeBands`.
    """
    for node in path_nodes:
        level = node.get("level")
        if level == "archetype":
            excluded = {str(x).lower() for x in constraints.get("excludedArchetypes", [])}
            if str(node.get("label", "")).lower() in excluded:
                return {"constraint": "excludedArchetypes", "nodeId": node["nodeId"]}
            allowed_sizes = constraints.get("allowedSizeBands")
            if allowed_sizes is not None and node.get("sizeBand") not in allowed_sizes:
                return {"constraint": "allowedSizeBands", "nodeId": node["nodeId"]}
        if level == "segment":
            allowed_metros = constraints.get("allowedMetroIds")
            if allowed_metros is not None and not set(node.get("metroIds", [])) & set(allowed_metros):
                return {"constraint": "allowedMetroIds", "nodeId": node["nodeId"]}
    return None


def evidence_status(is_final: bool, included_companies: int) -> str | None:
    """`has_evidence` with at least one included company; `no_evidence_found` only for a final path with none."""
    if included_companies > 0:
        return "has_evidence"
    return "no_evidence_found" if is_final else None


def transition_path(
    path: Doc, status: str, reason: str, level: str | None, at: str, step_id: str | None
) -> Doc:
    """Return a copy of `path` with the new status and an appended statusHistory entry."""
    if status not in STATUSES:
        raise ValueError(f"unknown path status {status!r}")
    current = path.get("status")
    if current == "final" and status == "kept":
        raise ValueError("a final path never goes back to kept")
    if status == "no_evidence_found" and current not in ("final", "no_evidence_found"):
        raise ValueError("no_evidence_found applies only to a final path")
    updated = dict(path)
    updated["status"] = status
    updated["statusHistory"] = [
        *path.get("statusHistory", []),
        {"status": status, "reason": reason, "level": level, "at": at, "stepId": step_id},
    ]
    return updated
