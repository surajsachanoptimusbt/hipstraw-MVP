"""Dimension deliberation (vichara) with basis grounding checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hipstraw_mm.evidence.excerpt_check import normalize


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
