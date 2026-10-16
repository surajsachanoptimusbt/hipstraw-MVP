"""Dimension deliberation (vichara) with basis grounding checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hipstraw_mm.evidence.excerpt_check import normalize
from hipstraw_mm.market.router import Check


@dataclass(frozen=True)
class GroundingResult:
    status: str
    reason: str | None = None


def check_basis_grounding(basis_text: str, objective_text: str) -> GroundingResult:
    if not basis_text or not basis_text.strip():
        return GroundingResult(status="fail", reason="empty_basis")
    normalized_basis = normalize(basis_text)
    normalized_objective = normalize(objective_text)
    if normalized_basis in normalized_objective:
        return GroundingResult(status="pass")
    return GroundingResult(status="fail", reason="basis_not_in_objective")


def check_item_grounding(item: dict[str, Any], objective_text: str) -> list[dict[str, Any]]:
    if item.get("status") != "answered":
        return []
    results = []
    for basis_text in item.get("basis", []):
        gr = check_basis_grounding(basis_text, objective_text)
        results.append({"basis": basis_text, "status": gr.status, "reason": gr.reason})
    return [r for r in results if r["status"] == "fail"]


def vichara_checks(
    result: Any,
    tier: str,
    *,
    dimension_key: str,
    objective_text: str,
    max_items: int,
    has_documents: bool,
) -> list[Check]:
    """Validators for one vichara.v1 answer. Blocking failures send an open-weight answer to frontier."""
    kept = [item.model_dump() for item in result.items][:max_items]
    checks = [
        Check("echo_key", result.dimensionKey == dimension_key, True,
              f"answered {result.dimensionKey!r}, asked {dimension_key!r}"
              if result.dimensionKey != dimension_key else "answers the dimension asked"),
    ]
    bad = [f for item in kept for f in check_item_grounding(item, objective_text)]
    checks.append(Check("grounding", not bad, True,
                        f"{len(bad)} basis excerpt(s) are not word for word in the objective text"
                        if bad else "every basis is word for word in the objective text"))
    if tier == "open_weight":
        abstained = has_documents and all(item.get("status") == "unresolved" for item in kept)
        checks.append(Check("abstention", not abstained, True,
                            "no answer although objective documents are attached; frontier double-checks"
                            if abstained else "answered, or no documents to answer from"))
    return checks
