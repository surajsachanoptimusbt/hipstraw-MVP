"""Buyer roles: functions with authority and cited evidence, never a person (FR-021, FR-030)."""

from __future__ import annotations

from typing import Any

PERSON_FIELDS = ("name", "email", "phone", "person", "personName", "contact")


def _passing(doc: dict[str, Any] | None) -> bool:
    return doc is not None and doc.get("check", {}).get("status") == "pass"


def validate_buyer_role(role: dict[str, Any], evidence_docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Keep a role only if every cited evidenceId is a passing evidence document of the company.

    Returns {"kept": True, "role": {...}} or {"kept": False, "unknown": {"reason": ...}}.
    `evidence_docs` maps evidenceId to the company's evidence documents.
    """
    cited = role.get("evidenceIds", [])
    if not cited:
        return {"kept": False, "unknown": {"reason": "role cites no evidence"}}
    bad = [e for e in cited if not _passing(evidence_docs.get(e))]
    if bad:
        return {"kept": False, "unknown": {"reason": f"cited evidence is not passing: {', '.join(bad)}"}}
    clean = {k: v for k, v in role.items() if k not in PERSON_FIELDS}
    return {"kept": True, "role": clean}


def batch_by_path(final_paths: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """One batch (one model call) per final path that has companies, in path order."""
    return [(str(p["pathId"]), list(p["companies"])) for p in final_paths if p.get("companies")]
