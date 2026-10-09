"""Shaping functions over ReadStore for the viewer API (contracts/viewer-api.md)."""

from __future__ import annotations

from typing import Any

from hipstraw_mm.store.base import Doc


def shape_runs(store: Any) -> list[Doc]:
    runs = store.list_market_runs()
    result = []
    for r in runs:
        result.append({
            "marketRunId": r.get("marketRunId"),
            "status": r.get("status"),
            "programId": r.get("programId"),
            "model": r.get("model"),
            "createdAt": r.get("createdAt"),
            "counts": r.get("counts", {}),
            "marketStatus": r.get("marketStatus"),
        })
    return result


def shape_steps(
    store: Any,
    run_id: str,
    *,
    after: int | None = None,
    refresh: list[int] | None = None,
) -> list[Doc]:
    if refresh is not None:
        result: list[Doc] = store.get_trace_steps(run_id, refresh)
        return result
    steps: list[Doc] = store.list_trace_steps_after(run_id, after or 0)
    for s in steps:
        s.pop("createdAt", None)
    return steps


def shape_step(store: Any, run_id: str, seq: int) -> Doc | None:
    results: list[Doc] = store.get_trace_steps(run_id, [seq])
    if not results:
        return None
    step = results[0]
    step.pop("createdAt", None)
    return step


def shape_blob(store: Any, blob_id: str) -> Doc | None:
    blob = store.get_trace_blob(blob_id)
    if blob is None:
        return None
    return {
        "blobId": blob.get("blobId"),
        "kind": blob.get("kind"),
        "content": blob.get("content"),
        "truncated": blob.get("truncated", False),
        "bytes": blob.get("bytes", 0),
    }


def shape_deliberations(store: Any, run_id: str) -> list[Doc]:
    delibs: list[Doc] = store.list_deliberations(run_id)
    return delibs


def shape_graph(store: Any, run_id: str, version: int | None = None) -> Doc | None:
    """Seed graph at `version` (default: latest), or None if the run has no graph."""
    graphs: list[Doc] = store.list_seed_graphs(run_id)
    if not graphs:
        return None
    versions = sorted(int(g.get("version", 0)) for g in graphs)
    wanted = versions[-1] if version is None else version
    chosen = next((g for g in graphs if int(g.get("version", 0)) == wanted), None)
    if chosen is None:
        return None
    return {
        "version": wanted,
        "nodes": chosen.get("nodes", []),
        "edges": chosen.get("edges", []),
        "structural": chosen.get("structural", []),
        "coverage": chosen.get("coverage", []),
        "unresolved": chosen.get("unresolved", []),
        "excluded": chosen.get("excluded", []),
        "versions": versions,
    }


def shape_run_detail(store: Any, run_id: str) -> Doc | None:
    run: Doc | None = store.get_market_run(run_id)
    if run is None:
        return None
    run.pop("createdAt", None)
    return run


def shape_beam(store: Any, run_id: str) -> list[Doc]:
    """Beam levels with per-factor search scores, kept apart from every confidence."""
    levels: list[Doc] = store.list_beam_levels(run_id)
    for lv in levels:
        lv.pop("createdAt", None)
    return levels


def shape_companies(store: Any, run_id: str) -> list[Doc]:
    """Companies with their path links and buyer roles (each role doc: roles[] or an explicit unknown)."""
    companies: list[Doc] = store.list_market_companies(run_id)
    roles: list[Doc] = store.list_buyer_roles(run_id)
    by_domain: dict[str, list[Doc]] = {}
    for r in roles:
        by_domain.setdefault(str(r.get("domainKey")), []).append(r)
    for c in companies:
        c.pop("createdAt", None)
        c["buyerRoles"] = [
            {"pathId": r.get("pathId"), **role}
            for r in by_domain.get(str(c.get("domainKey")), [])
            for role in r.get("roles", [])
        ]
        c["buyerRoleUnknowns"] = [
            {"pathId": r.get("pathId"), "reason": (r.get("unknown") or {}).get("reason")}
            for r in by_domain.get(str(c.get("domainKey")), [])
            if r.get("unknown")
        ]
    return companies


def shape_documents(store: Any, run_id: str) -> list[Doc]:
    """Objective documents without their full text: name, size, and an opening excerpt."""
    out = []
    for d in store.list_objective_documents(run_id):
        text = " ".join(p for p in d.get("pages", []) if p)
        out.append({
            k: d.get(k) for k in ("documentId", "fileName", "sha256", "pageCount", "chars", "keptChars", "truncated")
        } | {"excerpt": text[:1500]})
    return out


def shape_decisions(store: Any, run_id: str) -> Doc:
    run: Doc | None = store.get_market_run(run_id)
    decisions: list[Doc] = store.list_path_decisions(run_id)
    for d in decisions:
        d.pop("createdAt", None)
    return {
        "decisions": decisions,
        "marketStatus": run.get("marketStatus") if run else None,
        "unassessed": run.get("unassessed", []) if run else [],
    }


def shape_links(store: Any, run_id: str) -> list[Doc]:
    links: list[Doc] = store.list_link_checks(run_id)
    return links


def shape_paths(store: Any, run_id: str) -> list[Doc]:
    paths: list[Doc] = store.list_paths(run_id)
    return paths
