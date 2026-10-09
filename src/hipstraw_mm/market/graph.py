"""Graph generation helpers: filters, caps, parent validation, node ID assignment."""

from __future__ import annotations

from typing import Any


def apply_filters(
    nodes: list[dict[str, Any]],
    level: str,
    run_metros: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    metro_set = set(run_metros)

    for node in nodes:
        if level == "segment":
            node_metros = node.get("metroIds", [])
            if not node_metros or not any(m in metro_set for m in node_metros):
                excluded.append({
                    "label": node["label"],
                    "filterId": "metro_in_force",
                    "reason": "no metro in force",
                })
                continue

        if level == "archetype" and node.get("sizeBand") == "enterprise":
                excluded.append({
                    "label": node["label"],
                    "filterId": "no_enterprise",
                    "reason": "enterprise excluded",
                })
                continue

        kept.append(node)

    return kept, excluded


def apply_caps(
    nodes: list[dict[str, Any]],
    max_nodes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(nodes) <= max_nodes:
        return nodes, []
    return nodes[:max_nodes], nodes[max_nodes:]


def apply_parent_cap(
    node: dict[str, Any],
    max_parents: int,
) -> dict[str, Any]:
    parents = node.get("parentLabels", [])
    if len(parents) > max_parents:
        node = {**node, "parentLabels": parents[:max_parents]}
    return node


def validate_parents(
    nodes: list[dict[str, Any]],
    prev_labels: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for node in nodes:
        parents = node.get("parentLabels", [])
        if parents and not all(p in prev_labels for p in parents):
            invalid.append(node)
        else:
            valid.append(node)
    return valid, invalid


def assign_node_ids(
    nodes: list[dict[str, Any]],
    level: str,
    start: int,
) -> list[dict[str, Any]]:
    result = []
    for i, node in enumerate(nodes):
        node_copy = {**node, "nodeId": f"{level}_{start + i:04d}"}
        result.append(node_copy)
    return result
