"""Buyer roles: functions with authority and cited evidence, never a person (FR-021, FR-030)."""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market.router import Check, Rule
from hipstraw_mm.market.schemas import BuyerRoles

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


def buyer_role_checks(result: Any, tier: str, *, path_id: str, sent: dict[str, str]) -> list[Check]:
    """Validators for one buyer_roles.v2 answer (rubric: config/validation.yaml).

    `sent` maps each passing evidenceId in the prompt to the company record it belongs to.
    """
    other = sorted({r.pathId for r in result.roles if r.pathId != path_id})
    unknown = sorted({e for r in result.roles for e in r.evidenceIds if e not in sent})
    mixed = [n for n, r in enumerate(result.roles, start=1)
             if len({sent[e] for e in r.evidenceIds if e in sent}) > 1]
    roles = len(result.roles)
    return [
        Check("path_echo", not other, True,
              "every role is for the market unit asked" if not other else f"roles for other units: {other}",
              {"asked": path_id, "other": other}),
        Check("evidence_ids", not unknown, True,
              "every cited evidenceId was sent" if not unknown
              else f"{len(unknown)} cited evidenceId(s) were not sent",
              {"roles": roles, "unknown": unknown, "sent": len(sent)}),
        Check("one_company", not mixed, True,
              "each role's evidence comes from one company" if not mixed
              else f"{len(mixed)} role(s) cite evidence from more than one company",
              {"roles": roles, "mixed": mixed}),
    ]


def no_passing_evidence_rule(payload_companies: list[dict[str, Any]]) -> Rule:
    """With no passing evidence on the market unit, no role can be kept: answer with no roles."""
    empty = all(not c.get("evidence") for c in payload_companies)
    return Rule("no_passing_evidence", lambda: BuyerRoles(roles=[]) if empty else None)
