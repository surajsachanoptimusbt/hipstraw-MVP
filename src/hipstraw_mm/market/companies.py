"""Real companies per final path: one feature 002 child run per path (research R1, R13, R16).

Each final path becomes a feature 002 position (segment, archetype, buyer role, problem, trigger) on a
child run `<marketRunId>_p<n>` with a synthetic `traced_path` candidate. Feature 002's own discover,
verify, and review run unchanged on it, so every company is found on a retrieved page, checked against
its website, given cited evidence, and reviewed into include / exclude / needs_verification.

The functions here are pure mappings from the child run's stored records; the orchestration lives in
`stages.stage_companies`.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from hipstraw_mm.market.evidence_states import (
    MINIMUM_PROOFS,
    compute_critical_unknowns,
    compute_quality,
    compute_sufficiency,
)
from hipstraw_mm.models import MarketCandidate, Position, domain_key, registry_key

Doc = dict[str, Any]

# feature 002 Review rule -> the minimum proof it establishes (research R16)
RULE_FOR_PROOF = {"existence": "existence", "location": "hq", "size": "size", "interest_signal": "interest_signal"}
EVIDENCE_DIMENSIONS = {
    "sufficiency": "evidence_sufficiency",
    "quality": "evidence_quality",
    "criticalUnknowns": "critical_unknowns",
}


def child_run_id(market_run_id: str, n: int) -> str:
    return f"{market_run_id}_p{n}"


def labels_by_level(path: Doc, graph_nodes: dict[str, Doc]) -> dict[str, str]:
    out: dict[str, str] = {}
    for node_id in path.get("nodeIds", []):
        node = graph_nodes.get(node_id)
        if node:
            out[node["level"]] = node["label"]
    return out


def position_for_path(
    path: Doc, graph_nodes: dict[str, Doc], interest_ids: list[str], metro_names: list[str]
) -> Position:
    labels = labels_by_level(path, graph_nodes)
    missing = [lv for lv in ("segment", "archetype", "problem", "trigger", "buyerRole") if not labels.get(lv)]
    if missing:
        raise ValueError(f"path {path['pathId']} has no node for: {', '.join(missing)}")
    hints = [h for h in (labels.get("useCase"), *metro_names) if h]
    return Position(
        segment=labels["segment"],
        companyArchetype=labels["archetype"],
        buyer=labels["buyerRole"],
        problem=labels["problem"],
        trigger=labels["trigger"],
        primaryInterestIds=interest_ids,
        searchHints=hints,
    )


def interest_ids_for(program: Doc, default_ids: list[str]) -> list[str]:
    known = [i["id"] for i in program.get("primaryInterests", [])]
    chosen = [i for i in default_ids if i in known]
    return chosen or known[:1]


def path_candidate(market_run_id: str, program_id: str, path: Doc) -> Doc:
    label = " > ".join(path.get("nodeLabels", [])) or path["pathId"]
    return MarketCandidate(
        candidateId=f"{market_run_id}__{path['pathId']}",
        programId=program_id,
        experimentContextId=path["pathId"],
        label=label,
        origin="traced_path",
    ).model_dump()


def _proof(outcome: str | None) -> bool | None:
    if outcome == "pass":
        return True
    if outcome == "fail":
        return False
    return None


def companies_from_child_run(store: Any, child_id: str) -> list[Doc]:
    """One entry per company record of the child run, with its Review disposition and proofs."""
    evidence = {e["evidenceId"]: e for e in store.list_evidence(child_id)}
    out: list[Doc] = []
    for rec in store.list_company_records(child_id):
        decision = store.get_review_decision(rec["companyRecordId"]) or {}
        rules = {r["rule"]: r["outcome"] for r in decision.get("ruleResults", [])}
        proofs = {proof: _proof(rules.get(rule)) for proof, rule in RULE_FOR_PROOF.items()}
        if rules.get("large_enterprise") == "fail":
            proofs["size"] = False
        disposition = decision.get("disposition", "needs_verification")
        passing = [
            i for i in decision.get("evidenceIds", [])
            if evidence.get(i, {}).get("check", {}).get("status") == "pass"
        ]
        domain = rec.get("domain")
        hq = rec.get("hq") or {}
        confidence = rec.get("confidence") or {}
        out.append({
            "companyRecordId": rec["companyRecordId"],
            "name": rec["name"],
            "domain": domain,
            "domainKey": domain_key(domain) if domain else registry_key(rec["name"]),
            "url": f"https://{domain}" if domain else (rec.get("origin") or {}).get("resultUrl"),
            "disposition": disposition,
            "reason": decision.get("reason"),
            "hq": {"city": hq.get("city"), "state": hq.get("state"), "status": hq.get("status", "unknown")},
            "sizeStatus": (rec.get("size") or {}).get("status", "unknown"),
            "proofs": proofs,
            "conflict": any(o == "conflict" for o in rules.values()),
            "evidenceConfidence": float(confidence.get("value") or 0.0),
            "confidenceBand": confidence.get("band"),
            "needsVerification": disposition == "needs_verification",
            "unknowns": [u["field"] for u in rec.get("unknowns", [])],
            "evidenceIds": passing,
        })
    return out


def evidence_states(companies: list[Doc], settings: dict[str, Any], assessed_by: dict[str, str]) -> Doc:
    """The three verification results for one path, over companies Review did not exclude."""
    considered = [c for c in companies if c["disposition"] != "exclude"]
    states = {
        "sufficiency": compute_sufficiency(considered, settings),
        "quality": compute_quality(considered, settings),
        "criticalUnknowns": compute_critical_unknowns(considered),
    }
    full = sum(1 for c in considered if all(c["proofs"].get(p) is True for p in MINIMUM_PROOFS))
    reasons = {
        "sufficiency": f"{full} of {len(considered)} non-excluded companies have all four minimum proofs",
        "quality": "mean evidence confidence of non-excluded companies"
        + (" with a conflict kept in the records" if any(c["conflict"] for c in considered) else ""),
        "criticalUnknowns": "minimum proofs still unknown" if states["criticalUnknowns"] == "open"
        else "from the companies' remaining unknowns",
    }
    return {
        **states,
        "detail": {
            k: {"state": v, "reason": reasons[k], "assessedBy": assessed_by.get(EVIDENCE_DIMENSIONS[k], "")}
            for k, v in states.items()
        },
    }


def research_packet(child_id: str, companies: list[Doc], error: str | None = None) -> Doc:
    """The Research Evidence Packet Search & Research hands to Position & Evaluation for one path."""
    counts = Counter(c["disposition"] for c in companies)
    gaps = Counter(u for c in companies if c["disposition"] != "exclude" for u in c["unknowns"])
    if error:
        completion = "research failed"
    elif counts["include"]:
        completion = "sufficient" if counts["include"] >= max(1, len(companies) // 2) else "partial"
    elif counts["needs_verification"]:
        completion = "evidence ceiling"
    else:
        completion = "no verified company"
    return {
        "childRunId": child_id,
        "found": len(companies),
        "included": counts["include"],
        "needsVerification": counts["needs_verification"],
        "excluded": counts["exclude"],
        "contradictions": [c["name"] for c in companies if c["conflict"]],
        "gaps": [{"field": f, "companies": n} for f, n in gaps.most_common()],
        "completionReason": completion,
        "error": error,
    }


def merge_market_companies(run_id: str, per_path: list[tuple[str, str, list[Doc]]]) -> list[Doc]:
    """One `marketCompanies` document per domain key, linking every path that found it (data-model.md)."""
    merged: dict[str, Doc] = {}
    for path_id, child_id, companies in per_path:
        for c in companies:
            doc = merged.setdefault(c["domainKey"], {
                "marketRunId": run_id,
                "domainKey": c["domainKey"],
                "name": c["name"],
                "domain": c["domain"],
                "url": c["url"],
                "hq": c["hq"],
                "sizeStatus": c["sizeStatus"],
                "evidenceConfidence": c["evidenceConfidence"],
                "confidenceBand": c["confidenceBand"],
                "links": [],
            })
            doc["evidenceConfidence"] = max(doc["evidenceConfidence"], c["evidenceConfidence"])
            doc["links"].append({
                "pathId": path_id,
                "childRunId": child_id,
                "companyRecordId": c["companyRecordId"],
                "disposition": c["disposition"],
                "verified": c["disposition"] == "include",
                "reason": c["reason"],
            })
    for doc in merged.values():
        doc["conflict"] = len({link["disposition"] for link in doc["links"]}) > 1
        doc["disposition"] = _best_disposition(doc["links"])
    return list(merged.values())


def _best_disposition(links: list[Doc]) -> str:
    found = {link["disposition"] for link in links}
    for disposition in ("include", "needs_verification", "exclude"):
        if disposition in found:
            return disposition
    return "needs_verification"
