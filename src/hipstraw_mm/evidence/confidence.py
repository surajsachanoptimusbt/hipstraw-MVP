"""Confidence (research R8): computed from evidence only; the model produces no numbers.

The mean, over the four minimum-proof items (existence, location, size, interest signal), of the
reliability weight of the best passing citation for that item; an item without one counts 0.
Bands follow feature 001: High >= 0.8, Medium 0.5-0.79, Low < 0.5.
"""

from __future__ import annotations

from typing import Any, Literal

Band = Literal["High", "Medium", "Low"]


def confidence_band(value: float) -> Band:
    if value >= 0.8:
        return "High"
    if value >= 0.5:
        return "Medium"
    return "Low"


def _item_evidence(record: dict[str, Any]) -> list[list[str]]:
    existence = [record["existenceEvidenceId"]] if record.get("existenceEvidenceId") else []
    location = list((record.get("hq") or {}).get("evidenceIds", []))
    size = [s["evidenceId"] for s in (record.get("size") or {}).get("signals", [])]
    signals = [i for s in record.get("interestSignals") or [] for i in s["evidenceIds"]]
    return [existence, location, size, signals]


def compute_confidence(
    record: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]], weights: dict[str, float]
) -> dict[str, Any]:
    """`{"value": 0-1 rounded to 2 places, "band": ...}` for one company record."""
    best = []
    for evidence_ids in _item_evidence(record):
        passing = [
            weights[evidence_by_id[i]["reliability"]]
            for i in evidence_ids
            if i in evidence_by_id and evidence_by_id[i].get("check", {}).get("status") == "pass"
        ]
        best.append(max(passing, default=0.0))
    value = round(sum(best) / len(best), 2)
    return {"value": value, "band": confidence_band(value)}
