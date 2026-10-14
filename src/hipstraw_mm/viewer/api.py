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


def shape_evaluation(store: Any, run_id: str) -> Doc:
    """Position & Evaluation output: evaluation cases, the comparison, and the economic screening."""
    docs: list[Doc] = store.list_evaluation_cases(run_id)
    for d in docs:
        d.pop("createdAt", None)
    return {
        "cases": [d for d in docs if d.get("kind") == "evaluation_case"],
        "comparison": next((d for d in docs if d.get("kind") == "comparison"), None),
        "economics": next((d for d in docs if d.get("kind") == "economic_screening"), None),
    }


def shape_market_map(store: Any, run_id: str) -> Doc | None:
    doc: Doc | None = store.get_market_map(run_id)
    if doc is not None:
        doc.pop("createdAt", None)
    return doc


def shape_positions(store: Any, run_id: str) -> list[Doc]:
    """Canonical positions committed in this run, each with its earlier versions (newest first)."""
    run = store.get_market_run(run_id)
    if run is None:
        return []
    all_versions: list[Doc] = store.list_market_positions(run.get("programId"))
    keys = {p["positionKey"] for p in all_versions if p.get("marketRunId") == run_id}
    out = []
    for key in sorted(keys):
        versions = sorted((p for p in all_versions if p["positionKey"] == key), key=lambda p: -int(p["version"]))
        for v in versions:
            v.pop("createdAt", None)
        out.append({"positionKey": key, "current": versions[0], "history": versions[1:]})
    return out


def shape_agents(store: Any, run_id: str) -> Doc | None:
    """The run's agent registry with what each capability, skill, and tool actually did in the trace."""
    run = store.get_market_run(run_id)
    if run is None or not run.get("agentRegistry"):
        return None
    steps: list[Doc] = store.list_trace_steps_after(run_id, 0)
    by_id = {s["stepId"]: s for s in steps}
    usage: dict[str, Doc] = {}
    for s in steps:
        op = str(s.get("operation"))
        if op == "call_model" and s.get("parentStepId") in by_id:
            parent_op = str(by_id[s["parentStepId"]].get("operation"))
            u = usage.setdefault(parent_op, {"steps": 0, "modelCalls": 0, "failed": 0, "usd": 0.0})
            u["modelCalls"] += 1
            u["usd"] += float((s.get("cost") or {}).get("usd") or 0.0)
        u = usage.setdefault(op, {"steps": 0, "modelCalls": 0, "failed": 0, "usd": 0.0})
        u["steps"] += 1
        u["failed"] += 1 if s.get("status") == "failed" else 0
    tool_kinds: dict[str, int] = {}
    for s in steps:
        for t in s.get("toolCalls", []):
            tool_kinds[t.get("kind", "")] = tool_kinds.get(t.get("kind", ""), 0) + 1
    counts = run.get("counts") or {}
    tool_kinds["model"] = int(counts.get("modelCalls") or 0)
    tool_kinds["search"] = max(tool_kinds.get("search", 0), int(counts.get("searches") or 0))
    tool_kinds["fetch"] = max(tool_kinds.get("fetch", 0), int(counts.get("fetches") or 0))
    registry = run["agentRegistry"]
    claimed: set[str] = set()
    agents = []
    for agent in registry.get("agents", []):
        def with_usage(items: list[Doc]) -> list[Doc]:
            out = []
            for item in items:
                ops = item.get("operations", [])
                claimed.update(ops)
                totals = {"steps": 0, "modelCalls": 0, "failed": 0, "usd": 0.0}
                for op in ops:
                    for k in totals:
                        totals[k] += usage.get(op, {}).get(k, 0)
                out.append({**item, "usage": totals})
            return out
        agents.append({
            **agent,
            "innateCapabilities": with_usage(agent.get("innateCapabilities", [])),
            "skills": with_usage(agent.get("skills", [])),
            "tools": [
                {**t, "usage": sum(tool_kinds.get(k, 0) for k in t.get("toolCallKinds", []))}
                for t in agent.get("tools", [])
            ],
        })
    unclaimed = sorted(op for op in usage if op not in claimed)
    current = any("playbook" in c for a in registry.get("agents", []) for c in a.get("innateCapabilities", []))
    return {
        "version": registry.get("version"),
        "agents": agents,
        "unclaimedOperations": unclaimed,
        "simple": plain_view(registry if current else _current_registry()),
    }


_HOW = {"model": "ai", "rule": "rule", "mixed": "mixed"}


def _current_registry() -> Doc:
    """Runs opened before the plain-language and playbook fields existed borrow them from the current config."""
    from pathlib import Path

    from hipstraw_mm.market.agents import load_agent_registry

    if not (Path("config") / "agents.yaml").exists():
        return {}
    return load_agent_registry().model_dump()


def plain_view(registry: Doc) -> Doc:
    """What each agent does, knows, and uses, in market-manager language, each item marked as decided
    by a fixed rule, by the AI model, by rules then the model, or built into the agent."""
    counts = {"rule": 0, "ai": 0, "mixed": 0, "built_in": 0}
    agents = []
    for a in registry.get("agents", []):
        if not a.get("title"):
            continue
        does = [
            {"text": c["plain"], "how": "built_in", "playbook": c.get("playbook", [])}
            for c in a.get("innateCapabilities", []) if c.get("plain")
        ]
        does += [
            {"text": s["plain"], "how": _HOW[s["kind"]], "playbook": s.get("playbook", [])}
            for s in a.get("skills", []) if s.get("plain")
        ]
        for d in does:
            counts[d["how"]] += 1
        uses = [t["plain"] for t in a.get("tools", []) if t.get("plain")]
        if any(d["how"] in ("ai", "mixed") for d in does):
            uses.append("AI model")
        agents.append({
            "id": a["id"], "title": a["title"], "role": a.get("role"),
            "does": does, "knows": a.get("knowledge", []), "uses": uses,
        })
    linked = sum(1 for a in agents for d in a["does"] if d["playbook"])
    return {"agents": agents, "counts": counts, "playbookLinked": linked, "glossary": registry.get("glossary", [])}
