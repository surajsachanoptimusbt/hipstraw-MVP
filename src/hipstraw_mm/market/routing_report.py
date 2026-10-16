"""Routing walk-through read back from a run's trace (read only).

For each vichara-stage task: the router's decision, every model attempt with its tier, answer preview,
tokens, latency and cost, the validator results, the escalation, and the saved record with its lineage.
The CLI simulation and the viewer's routing page both use it.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from hipstraw_mm import prompts
from hipstraw_mm.market.grammar import load_grammar
from hipstraw_mm.market.router import RoutingConfig, decide_route, load_routing
from hipstraw_mm.market.settings import load_pipeline_settings

Doc = dict[str, Any]

_TASK_BY_OPERATION = {
    "repair_deliberation": prompts.VICHARA_REPAIR,
    "judge_coverage": prompts.VICHARA_COVERAGE,
    "propose_hypotheses": prompts.VICHARA_PROPOSE,
}


def build_simulation(store: Any, run_id: str, config_dir: Path = Path("config")) -> Doc | None:
    run = store.get_market_run(run_id)
    if run is None:
        return None
    routing = load_routing(config_dir)
    settings = load_pipeline_settings(config_dir)
    entries = walkthrough(store, run_id, config_dir)
    attempts = [a for e in entries for a in e["attempts"]]
    ow_model = next((a["model"] for a in attempts if a["tier"] == "open_weight"), None)
    frontier_model = next((a["model"] for a in attempts if a["tier"] == "frontier"), None)
    for e in entries:
        e["costUsd"], e["allFrontierUsd"] = _entry_costs(e, settings, frontier_model or "")
    versions = [e["routerVersion"] for e in entries if e.get("routerVersion")]
    # The policy this run used, as its trace recorded it: R4 means the open-weight route was off.
    rules_seen = {e["router"]["ruleId"] for e in entries if e["router"]}
    route_on = "R4" not in rules_seen if rules_seen - {"R1", "R2", "R3"} else routing.openWeight.enabled
    policy = routing.model_copy(update={"openWeight": routing.openWeight.model_copy(update={"enabled": route_on})})
    program = store.get_program(run.get("programId", "")) or {}
    docs = store.list_objective_documents(run_id)
    program_chars = len(str((run.get("objective") or {}).get("text", "")))
    documents = [{"fileName": d.get("fileName"), "pages": len(d.get("pages") or []),
                  "chars": sum(len(p) for p in d.get("pages") or [])} for d in docs]
    return {
        "runId": run_id,
        "routerVersion": versions[0] if versions else routing.version,
        "program": {"programId": run.get("programId"), "name": program.get("name")},
        "objective": {"programTextChars": program_chars, "documents": documents,
                      "chars": program_chars + sum(d["chars"] for d in documents)},
        "openWeight": {"model": ow_model, "available": ow_model is not None},
        "frontier": {"model": frontier_model},
        "openWeightRouteOn": route_on,
        "rubric": rubric(policy, open_weight_available=ow_model is not None),
        "walkthrough": entries,
        "summary": summarize(entries),
    }


def rubric(config: RoutingConfig, *, open_weight_available: bool) -> list[Doc]:
    """Where each task goes by its class alone. Per-call facts (input size, failures in a row) can still
    send a simple task to frontier; the walk-through shows when they did."""
    rows = []
    for task, entry in config.tasks.items():
        d = decide_route(config, task, open_weight_available=open_weight_available,
                         input_chars=0, consecutive_failures=0)
        rows.append({"task": task, "class": entry.class_, "wired": entry.wired,
                     "ruleId": d.ruleId, "route": d.route, "why": d.why})
    return rows


def walkthrough(store: Any, run_id: str, config_dir: Path) -> list[Doc]:
    steps = store.list_trace_steps_after(run_id, 0)
    children: dict[str, list[Doc]] = defaultdict(list)
    for s in steps:
        if s.get("parentStepId"):
            children[s["parentStepId"]].append(s)
    questions = {d.key: d.question for d in load_grammar(config_dir).dimensions}
    saved = {d["dimensionKey"]: d for d in store.list_deliberations(run_id)}

    entries: list[Doc] = []
    for s in steps:
        if s.get("actor") != "vichara":
            continue
        inputs, outputs = s.get("inputs") or {}, s.get("outputs") or {}
        routing = outputs.get("routing")
        op = s["operation"]
        attempts = [_attempt(w, store) for w in children[s["stepId"]] if w.get("operation") == "call_model"]
        entries.append({
            "seq": s["seq"],
            "task": routing["task"] if routing else _TASK_BY_OPERATION.get(op, op),
            "routed": routing is not None,
            "routerVersion": routing.get("routerVersion") if routing else None,
            "operation": op,
            "subject": _subject(inputs),
            "question": questions.get(inputs.get("dimensionKey", "")),
            "inputChars": attempts[0]["promptChars"] if attempts else None,
            "router": {k: routing[k] for k in ("ruleId", "why", "route", "class")} if routing else None,
            "attempts": attempts,
            "checks": s.get("checks") or [],
            "outcome": {k: routing[k] for k in ("servedBy", "escalated", "escalationReason")} if routing else None,
            "saved": _saved(op, inputs, outputs, saved),
        })
    return entries


def _subject(inputs: Doc) -> str:
    dims = inputs.get("dimensions")
    if inputs.get("dimensionKey"):
        return str(inputs["dimensionKey"])
    if isinstance(dims, list):
        return ", ".join(dims)
    return f"{dims} dimensions" if dims else "all dimensions"


def _attempt(worker: Doc, store: Any) -> Doc:
    inputs, outputs, cost = worker.get("inputs") or {}, worker.get("outputs") or {}, worker.get("cost") or {}
    prompt = store.get_trace_blob(worker["promptBlobId"]) if worker.get("promptBlobId") else None
    response = store.get_trace_blob(worker["responseBlobId"]) if worker.get("responseBlobId") else None
    return {
        "seq": worker.get("seq"),
        "tier": inputs.get("route") or "frontier",
        "model": inputs.get("model"),
        "servedModel": outputs.get("servedModel"),
        "status": worker.get("status"),
        "latencyMs": worker.get("latencyMs"),
        "inputTokens": cost.get("inputTokens"),
        "outputTokens": cost.get("outputTokens"),
        "usd": cost.get("usd"),
        "error": worker.get("error"),
        "promptChars": (prompt or {}).get("bytes"),
        "answer": _answer_preview((response or {}).get("content")),
    }


def _clip(text: Any, limit: int) -> str | None:
    if not text:
        return None
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _answer_preview(content: str | None) -> Doc | None:
    """The first deliberation item of a vichara answer, shortened; None for other response shapes."""
    if not content:
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return {"status": "unparseable", "answer": _clip(content, 160), "basis": None, "reason": None}
    items = data.get("items") if isinstance(data, dict) else None
    if not items:
        return None
    first = items[0]
    return {"status": first.get("status"), "answer": _clip(first.get("answer"), 260),
            "basis": _clip((first.get("basis") or [None])[0], 200), "reason": _clip(first.get("reason"), 140)}


def _saved(op: str, inputs: Doc, outputs: Doc, saved: dict[str, Doc]) -> Doc:
    if op == "deliberate_dimension":
        doc = saved.get(inputs.get("dimensionKey", "")) or {}
        items = doc.get("items", [])
        statuses = Counter(i.get("status") for i in items)
        first = items[0] if items else {}
        return {"record": f"deliberation {doc.get('dimensionKey')}", "items": dict(statuses),
                "lineage": doc.get("deliberatedBy"), "repairExhausted": doc.get("repairExhausted"),
                "answer": {"status": first.get("status"), "answer": _clip(first.get("answer"), 260),
                           "basis": _clip((first.get("basis") or [None])[0], 200)} if first else None}
    if op == "judge_coverage":
        return {"record": "coverage gaps", "items": {"gaps": len(outputs.get("gaps") or [])}}
    if op == "propose_hypotheses":
        return {"record": "proposed hypotheses (labelled)", "items": {"dimensions": len(outputs.get("proposed") or [])}}
    return {"record": "repaired dimensions", "items": {"repaired": len(outputs.get("repaired") or [])}}


def _entry_costs(entry: Doc, settings: Any, frontier_model: str) -> tuple[float, float]:
    """What this task cost, and what it would have cost with every call on frontier."""
    actual = sum(a["usd"] or 0.0 for a in entry["attempts"])
    frontier = sum(a["usd"] or 0.0 for a in entry["attempts"] if a["tier"] == "frontier")
    if entry["routed"] and entry["outcome"]["servedBy"] == "open_weight":
        kept = entry["attempts"][-1]
        frontier += settings.model_cost(frontier_model, kept["inputTokens"] or 0, kept["outputTokens"] or 0) or 0.0
    return round(actual, 6), round(frontier, 6)


def summarize(entries: list[Doc]) -> Doc:
    routed = [e for e in entries if e["routed"]]
    reasons: Counter[str] = Counter()
    for e in routed:
        if not e["outcome"]["escalated"]:
            continue
        failed = [c["name"].split(".", 1)[1] for c in e["checks"]
                  if c["name"].startswith("open_weight.") and c["status"] == "fail"]
        reasons.update(failed or [e["outcome"]["escalationReason"].split(":", 1)[0]])

    calls: Counter[str] = Counter()
    usd: defaultdict[str, float] = defaultdict(float)
    unpriced: Counter[str] = Counter()
    for e in entries:
        for a in e["attempts"]:
            calls[a["tier"]] += 1
            if a["usd"] is None:
                unpriced[a["tier"]] += 1
            else:
                usd[a["tier"]] += a["usd"]
    actual = usd["open_weight"] + usd["frontier"]
    all_frontier = sum(e.get("allFrontierUsd") or 0.0 for e in entries)
    return {
        "routedCalls": len(routed),
        "keptOnOpenWeight": sum(1 for e in routed if e["outcome"]["servedBy"] == "open_weight"),
        "escalated": sum(1 for e in routed if e["outcome"]["escalated"]),
        "frontierDirect": sum(1 for e in routed if e["router"]["route"] == "frontier"),
        "notRouted": len(entries) - len(routed),
        "escalationReasons": dict(sorted(reasons.items())),
        "modelCalls": {"open_weight": calls["open_weight"], "frontier": calls["frontier"]},
        "cost": {
            "openWeightUsd": round(usd["open_weight"], 4),
            "frontierUsd": round(usd["frontier"], 4),
            "totalUsd": round(actual, 4),
            "frontierEquivalentOfKept": round(all_frontier - usd["frontier"], 4),
            "allFrontierEstimateUsd": round(all_frontier, 4),
            "unpricedCalls": dict(unpriced),
        },
    }
