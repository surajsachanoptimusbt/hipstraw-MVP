"""Model- and search-backed stage orchestration, one function per `market <stage>` command.

Each stage checks the run's status, does its work inside traced steps, writes its artifacts, and moves
the run to the next status. Every model call is traced as a child `workers` step with its prompt and
response stored as blobs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from hipstraw_mm import prompts
from hipstraw_mm.context import Context
from hipstraw_mm.errors import ExternalServiceError, PreconditionError
from hipstraw_mm.market.assess import LAYER as ASSESS_LAYER
from hipstraw_mm.market.assess import PER_PATH_KEYS, assess_records
from hipstraw_mm.market.assess import RIGHT as ASSESS_RIGHT
from hipstraw_mm.market.beam import (
    build_scored_record,
    diversity_filter,
    filter_beam,
    keep_top,
    select_final,
)
from hipstraw_mm.market.buyers import validate_buyer_role
from hipstraw_mm.market.grammar import load_grammar
from hipstraw_mm.market.graph import apply_caps, apply_filters, apply_parent_cap, assign_node_ids
from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.links import check_link_coverage, chunk_links, link_record
from hipstraw_mm.market.meaning import load_graph_meaning
from hipstraw_mm.market.paths import path_id, paths_below
from hipstraw_mm.market.repair import bounded_repair
from hipstraw_mm.market.schemas import (
    GRAPH_LEVELS,
    BeamScoring,
    BuyerRoles,
    CoverageJudgement,
    DimensionDeliberation,
    DimensionRepair,
    GraphLevelProposal,
    LinkVerification,
    PathAssessment,
    VicharaProposals,
)
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import ModelCallCeilingError, Tracer
from hipstraw_mm.market.vichara import check_item_grounding

T = TypeVar("T", bound=BaseModel)
Doc = dict[str, Any]

BEAM_SCORING_CHUNK = 15


def make_tracer(ctx: Context, run_id: str, config_dir: Path) -> Tracer:
    return Tracer(
        store=ctx.store,
        layers=load_layers(config_dir),
        settings=load_pipeline_settings(config_dir),
        run_id=run_id,
        clock=ctx.now,
    )


def load_run(ctx: Context, run_id: str, expected: str) -> Doc:
    run = ctx.store.get_market_run(run_id)
    if run is None:
        raise PreconditionError(f"market run {run_id!r} not found")
    if run.get("status") != expected:
        raise PreconditionError(f"market run {run_id!r} is '{run.get('status')}', expected '{expected}'")
    return run


def objective_text(ctx: Context, run: Doc) -> str:
    """The objective bundle as plain text: program objective plus uploaded objective documents.

    Grounding checks and prompts use this same string.
    """
    from hipstraw_mm.market.objective import documents_text

    obj = run.get("objective") or {}
    lines = [f"Objective: {str(obj.get('text', '')).strip()}"]
    contexts = obj.get("experimentContexts") or []
    if contexts:
        labels = [str(c.get("label", c.get("id", ""))) if isinstance(c, dict) else str(c) for c in contexts]
        lines.append("Experiment contexts: " + "; ".join(labels))
    constraints = obj.get("constraints") or {}
    if constraints:
        lines.append("Constraints: " + "; ".join(f"{k}: {v}" for k, v in constraints.items()))
    docs = documents_text(ctx.store.list_objective_documents(run["marketRunId"]))
    if docs:
        lines.append(docs)
    return "\n".join(lines)


def model_call(
    ctx: Context,
    tracer: Tracer,
    schema: type[T],
    messages: list[dict[str, str]],
    *,
    match_key: str,
    prompt_version: str,
    run_id: str,
) -> T:
    """One traced model call (a `workers` child step holding the prompt and response blobs)."""
    with tracer.step("workers", "llm_worker", "call_model", right="call_model") as worker:
        worker.set_inputs({"schema": schema.__name__, "promptVersion": prompt_version, "matchKey": match_key})
        tracer.observe_model_call()
        result = ctx.llm.parse(
            schema, messages, match_key=match_key, prompt_version=prompt_version, run_id=run_id, step=match_key
        )
        worker.record_model_call(
            name=ctx.llm.model or "",
            prompt_version=prompt_version,
            schema=schema.__name__,
            attempt=1,
            prompt_content=json.dumps(messages, ensure_ascii=False),
            response_content=result.model_dump_json(),
            usage=getattr(ctx.llm, "last_usage", None),
        )
        worker.set_outputs({"ok": True})
    return result


def _digest(deliberations: list[Doc], keys: set[str] | None = None) -> list[Doc]:
    """Answered and model-proposed items, compact, for prompts that need vichara results as context.

    Each item says where it came from: `objective` (grounded in the objective text) or `model`
    (a hypothesis the model proposed because the objective was silent).
    """
    out: list[Doc] = []
    for d in deliberations:
        if keys is not None and d["dimensionKey"] not in keys:
            continue
        items = [
            {
                "itemId": it.get("itemId"),
                "question": it.get("question"),
                "answer": it.get("answer"),
                "source": "model" if it.get("status") == "proposed" else "objective",
            }
            for it in d.get("items", [])
            if it.get("status") in ("answered", "proposed")
        ]
        out.append({"dimensionKey": d["dimensionKey"], "items": items})
    return out


def _latest_graph(ctx: Context, run_id: str) -> Doc:
    graphs = ctx.store.list_seed_graphs(run_id)
    if not graphs:
        raise PreconditionError(f"market run {run_id!r} has no seed graph")
    return graphs[-1]


# --------------------------------------------------------------------------------------------------
# vichara
# --------------------------------------------------------------------------------------------------


def stage_vichara(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    run = load_run(ctx, run_id, "opened")
    tracer = make_tracer(ctx, run_id, config_dir)
    settings = load_pipeline_settings(config_dir)
    grammar = load_grammar(config_dir)
    text = objective_text(ctx, run)
    max_items = settings.vichara.maxItemsPerDimension

    items_by_dim: dict[str, Any] = {}
    for dim in grammar.dimensions:
        payload = {"dimensionKey": dim.key, "question": dim.question, "objectiveText": text}
        with tracer.step("search_research", "vichara", "deliberate_dimension", right="ask_dimension") as step:
            step.set_inputs({"dimensionKey": dim.key})
            result = model_call(
                ctx, tracer, DimensionDeliberation, prompts.messages(prompts.VICHARA, payload),
                match_key=f"vichara:{dim.key}", prompt_version=prompts.VICHARA, run_id=run_id,
            )
            items_by_dim[dim.key] = [i.model_dump() for i in result.items][:max_items]
            step.set_outputs({"items": len(items_by_dim[dim.key])})

    def check(current: Doc) -> list[Doc]:
        failures: list[Doc] = []
        for key, items in current.items():
            bad = [f for item in items for f in check_item_grounding(item, text)]
            if bad:
                failures.append({
                    "key": key, "items": items,
                    "reason": f"{len(bad)} basis excerpt(s) are not word for word in the objective text",
                })
        return failures

    repair_calls = 0

    def repair(failures: list[Doc]) -> Doc:
        nonlocal repair_calls
        repair_calls += 1
        payload = {
            "failingDimensions": [
                {"dimensionKey": f["key"], "items": f["items"], "reason": f["reason"]} for f in failures
            ],
            "objectiveText": text,
        }
        wanted = {f["key"] for f in failures}
        with tracer.step("search_research", "vichara", "repair_deliberation", right="ask_dimension") as step:
            step.set_inputs({"dimensions": sorted(wanted), "attempt": repair_calls})
            result = model_call(
                ctx, tracer, DimensionRepair, prompts.messages(prompts.VICHARA_REPAIR, payload),
                match_key=f"vichara_repair:{repair_calls}", prompt_version=prompts.VICHARA_REPAIR, run_id=run_id,
            )
            patches = {e.dimensionKey: [i.model_dump() for i in e.items][:max_items]
                       for e in result.dimensions if e.dimensionKey in wanted}
            step.set_outputs({"repaired": sorted(patches)})
        return patches

    outcome = bounded_repair(
        items=items_by_dim, check_fn=check, repair_fn=repair, max_attempts=settings.repair.maxAttempts
    )

    unresolved: list[Doc] = [
        {"kind": "deliberation", "ref": u["key"], "reason": u["reason"]} for u in outcome.unresolved
    ]

    coverage_payload = {
        "dimensions": [{"dimensionKey": k, "items": v} for k, v in items_by_dim.items()],
        "objectiveText": text,
    }
    with tracer.step("search_research", "vichara", "judge_coverage", right="ask_dimension") as step:
        step.set_inputs({"dimensions": len(items_by_dim)})
        coverage = model_call(
            ctx, tracer, CoverageJudgement, prompts.messages(prompts.VICHARA_COVERAGE, coverage_payload),
            match_key="vichara_coverage", prompt_version=prompts.VICHARA_COVERAGE, run_id=run_id,
        )
        gaps = [d for d in coverage.dimensions if not d.addressesDimension]
        unresolved.extend({"kind": "coverage", "ref": g.dimensionKey, "reason": g.reason} for g in gaps)
        step.set_outputs({"gaps": [g.dimensionKey for g in gaps]})

    exhausted = {u["key"] for u in outcome.unresolved}
    for key in exhausted:
        items_by_dim[key] = [
            {**item, "status": "unresolved", "answer": None, "basis": [],
             "reason": "its basis was not found word for word in the objective after repair"}
            if check_item_grounding(item, text) else item
            for item in items_by_dim[key]
        ]

    meaning = load_graph_meaning(config_dir)
    not_proposable = set(meaning.managerOnly) | set(meaning.verificationResults)
    gap_keys = {g.dimensionKey for g in gaps}
    to_propose = [
        dim for dim in grammar.dimensions
        if dim.key not in not_proposable
        and (dim.key in gap_keys or not any(i.get("status") == "answered" for i in items_by_dim.get(dim.key, [])))
    ]
    if to_propose:
        propose_payload: Doc = {
            "objectiveText": text,
            "dimensions": [{"dimensionKey": d.key, "question": d.question} for d in to_propose],
            "groundedAnswers": [
                {"dimensionKey": k, "answers": [i["answer"] for i in v if i.get("status") == "answered"]}
                for k, v in items_by_dim.items() if any(i.get("status") == "answered" for i in v)
            ],
            "maxItems": max_items,
        }
        with tracer.step("search_research", "vichara", "propose_hypotheses", right="ask_dimension") as step:
            step.set_inputs({"dimensions": [d.key for d in to_propose]})
            proposals = model_call(
                ctx, tracer, VicharaProposals, prompts.messages(prompts.VICHARA_PROPOSE, propose_payload),
                match_key="vichara_propose", prompt_version=prompts.VICHARA_PROPOSE, run_id=run_id,
            )
            wanted = {d.key for d in to_propose}
            proposed_keys: list[str] = []
            for entry in proposals.dimensions:
                if entry.dimensionKey not in wanted:
                    continue
                proposed_keys.append(entry.dimensionKey)
                items_by_dim.setdefault(entry.dimensionKey, []).extend(
                    {
                        "question": p.question, "status": "proposed", "answer": p.answer, "basis": [],
                        "reason": None, "rationale": p.rationale, "confidence": p.confidence,
                        "source": "model", "label": "hypothesis",
                    }
                    for p in entry.items[:max_items]
                )
            unresolved.extend(
                {"kind": "deliberation", "ref": key,
                 "reason": "the objective gives no information; a model-proposed hypothesis is recorded instead"}
                for key in proposed_keys
            )
            step.set_outputs({"proposed": proposed_keys})

    for key, items in items_by_dim.items():
        for i, item in enumerate(items):
            item["itemId"] = f"{key}#{i}"
        ctx.store.create_deliberation({
            "deliberationId": f"{run_id}__{key}",
            "marketRunId": run_id,
            "dimensionKey": key,
            "items": items,
            "repairAttempts": outcome.attempts,
            "repairExhausted": key in exhausted,
        })
    ctx.store.transition_market_run(
        run_id, "opened", "deliberated", {"unresolved": [*run.get("unresolved", []), *unresolved]}
    )
    return {"dimensions": len(items_by_dim), "unresolved": len(unresolved), "repairAttempts": outcome.attempts}


# --------------------------------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------------------------------


def _label_key(label: str) -> str:
    return " ".join(str(label).lower().split())


def stage_graph(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    run = load_run(ctx, run_id, "defined")
    tracer = make_tracer(ctx, run_id, config_dir)
    meaning = load_graph_meaning(config_dir)
    text = objective_text(ctx, run)
    constraints = run.get("constraintsInForce") or {}
    metros = list(constraints.get("metroIds", []))
    deliberations = ctx.store.list_deliberations(run_id)
    level_defs = {lv.level: lv for lv in meaning.levels}

    nodes_by_level: dict[str, list[Doc]] = {}
    excluded: list[Doc] = []
    counter = 0

    for idx, level in enumerate(GRAPH_LEVELS):
        lv = level_defs[level]
        prev_nodes = nodes_by_level.get(GRAPH_LEVELS[idx - 1], []) if idx else []
        payload = {
            "level": level,
            "dimension": lv.dimension,
            "objectiveText": text,
            "deliberation": _digest(deliberations, {lv.dimension}),
            "previousLevels": [
                {
                    "level": prev,
                    "nodes": [
                        {"label": n["label"], "description": n["description"]}
                        for n in nodes_by_level.get(prev, [])
                    ],
                }
                for prev in GRAPH_LEVELS[:idx]
            ],
            "metros": metros if level == "segment" else [],
            "constraints": constraints,
            "minNodes": min(lv.minNodes, lv.maxNodes),
            "maxNodes": lv.maxNodes,
        }
        if idx:
            payload["allowedParentLabels"] = [n["label"] for n in prev_nodes]
        prev_by_key = {_label_key(n["label"]): n["label"] for n in prev_nodes}
        with tracer.step("search_research", "graph_builder", "build_level", right="build_graph") as step:
            step.set_inputs({"level": level, "maxNodes": lv.maxNodes, "maxParents": lv.maxParents})
            for attempt in (1, 2):
                proposal = model_call(
                    ctx, tracer, GraphLevelProposal, prompts.messages(prompts.GRAPH_LEVEL, payload),
                    match_key=f"graph:{level}:{attempt}", prompt_version=prompts.GRAPH_LEVEL, run_id=run_id,
                )
                nodes = [{**n.model_dump(), "level": level} for n in proposal.nodes]
                kept, dropped = apply_filters(nodes, level, metros)
                lost: list[Doc] = []
                if idx:
                    linked: list[Doc] = []
                    for n in kept:
                        wanted = (_label_key(p) for p in n.get("parentLabels", []))
                        parents = list(dict.fromkeys(prev_by_key[k] for k in wanted if k in prev_by_key))
                        if parents:
                            linked.append({**n, "parentLabels": parents})
                        else:
                            lost.append({
                                "label": n["label"], "level": level, "filterId": "no_valid_parent",
                                "reason": "none of its parentLabels is on the previous level",
                            })
                    kept = linked
                if kept or not idx or attempt == 2:
                    break
                payload["feedback"] = (
                    "None of your nodes had a parentLabels entry that exactly matches allowedParentLabels. "
                    "Every node must list at least one label copied verbatim from allowedParentLabels."
                )
            excluded.extend({**d, "level": level} for d in dropped)
            excluded.extend(lost)

            kept = [apply_parent_cap(n, lv.maxParents) for n in kept]
            kept, capped = apply_caps(kept, lv.maxNodes)
            excluded.extend({
                "label": n["label"], "level": level, "filterId": "cap",
                "reason": f"more than {lv.maxNodes} nodes proposed for this level",
            } for n in capped)

            kept = assign_node_ids(kept, level, counter)
            counter += len(kept)
            nodes_by_level[level] = kept
            step.set_outputs({"proposed": len(nodes), "kept": len(kept)})

    edges: list[Doc] = []
    seen_edges: set[tuple[str, str]] = set()
    for idx in range(1, len(GRAPH_LEVELS)):
        by_label: dict[str, Doc] = {}
        for n in nodes_by_level[GRAPH_LEVELS[idx - 1]]:
            by_label.setdefault(n["label"], n)
        for n in nodes_by_level[GRAPH_LEVELS[idx]]:
            for parent_label in n.get("parentLabels", []):
                parent = by_label.get(parent_label)
                if parent and (parent["nodeId"], n["nodeId"]) not in seen_edges:
                    seen_edges.add((parent["nodeId"], n["nodeId"]))
                    edges.append({
                        "edgeId": f"{parent['nodeId']}->{n['nodeId']}",
                        "fromNodeId": parent["nodeId"],
                        "toNodeId": n["nodeId"],
                    })

    touched = {e["fromNodeId"] for e in edges} | {e["toNodeId"] for e in edges}
    for level in GRAPH_LEVELS:
        connected = [n for n in nodes_by_level[level] if n["nodeId"] in touched]
        excluded.extend({
            "label": n["label"], "level": level, "filterId": "no_connection",
            "reason": "no edge to or from this node after the other filters",
        } for n in nodes_by_level[level] if n["nodeId"] not in touched)
        nodes_by_level[level] = connected

    all_nodes = [n for level in GRAPH_LEVELS for n in nodes_by_level[level]]
    ctx.store.create_seed_graph({
        "graphId": f"{run_id}__graph_v1",
        "marketRunId": run_id,
        "version": 1,
        "nodes": all_nodes,
        "edges": edges,
        "excluded": excluded,
        "structural": [],
        "coverage": [],
        "unresolved": [],
        "metrosInForce": metros,
    })
    ctx.store.transition_market_run(run_id, "defined", "graphed")
    return {"nodes": len(all_nodes), "edges": len(edges), "excluded": len(excluded)}


# --------------------------------------------------------------------------------------------------
# links
# --------------------------------------------------------------------------------------------------


def stage_links(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    run = load_run(ctx, run_id, "validated")
    tracer = make_tracer(ctx, run_id, config_dir)
    settings = load_pipeline_settings(config_dir)
    threshold = settings.links.lowConfidenceThreshold
    graph = _latest_graph(ctx, run_id)
    nodes = {n["nodeId"]: n for n in graph.get("nodes", [])}
    text = objective_text(ctx, run)
    digest = _digest(ctx.store.list_deliberations(run_id))

    links = [
        {
            "fromNodeId": e["fromNodeId"],
            "toNodeId": e["toNodeId"],
            "fromLabel": nodes[e["fromNodeId"]]["label"],
            "fromDescription": nodes[e["fromNodeId"]]["description"],
            "toLabel": nodes[e["toNodeId"]]["label"],
            "toDescription": nodes[e["toNodeId"]]["description"],
        }
        for e in graph.get("edges", [])
        if e["fromNodeId"] in nodes and e["toNodeId"] in nodes
    ]

    flagged = 0
    for i, chunk in enumerate(chunk_links(links, settings.links.linksPerCall)):
        payload = {"links": chunk, "objectiveText": text, "deliberations": digest}
        with tracer.step("search_research", "link_verifier", "verify_links", right="verify_link") as step:
            step.set_inputs({"chunk": i, "links": len(chunk)})
            problem = ""
            returned: list[Doc] = []
            for attempt in (1, 2):
                result = model_call(
                    ctx, tracer, LinkVerification, prompts.messages(prompts.LINK_VERIFICATION, payload),
                    match_key=f"links:{i}:{attempt}", prompt_version=prompts.LINK_VERIFICATION, run_id=run_id,
                )
                returned = [e.model_dump() for e in result.links]
                try:
                    check_link_coverage(chunk, returned)
                    break
                except ValueError as exc:
                    problem = str(exc)
            else:
                raise ExternalServiceError(f"link verification chunk {i} is incomplete after a retry: {problem}")
            for link in returned:
                record = link_record(link, threshold, step.step_id)
                flagged += 1 if record["flagged"] else 0
                ctx.store.create_link_check({
                    **record,
                    "linkCheckId": f"{run_id}__{link['fromNodeId']}__{link['toNodeId']}",
                    "marketRunId": run_id,
                    "fromLabel": nodes[link["fromNodeId"]]["label"],
                    "toLabel": nodes[link["toNodeId"]]["label"],
                })
            step.set_outputs({"verified": len(returned), "flaggedSoFar": flagged})

    ctx.store.transition_market_run(run_id, "validated", "linked")
    return {"links": len(links), "flagged": flagged}


# --------------------------------------------------------------------------------------------------
# beam
# --------------------------------------------------------------------------------------------------


def _candidate(
    node_ids: list[str], nodes: dict[str, Doc], confidence: dict[tuple[str, str], float], run_id: str
) -> Doc:
    levels = {nodes[n]["level"]: nodes[n]["label"] for n in node_ids}
    edge_conf = [
        confidence[(a, b)] for a, b in zip(node_ids, node_ids[1:], strict=False) if (a, b) in confidence
    ]
    return {
        "pathId": path_id([run_id, *node_ids]),
        "nodeIds": node_ids,
        "nodeId": node_ids[-1],
        "nodeLabels": [nodes[n]["label"] for n in node_ids],
        "segment": levels.get("segment"),
        "problem": levels.get("problem"),
        "linkConfidences": edge_conf,
        "meanLinkConfidence": sum(edge_conf) / len(edge_conf) if edge_conf else None,
    }


def stage_beam(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    run = load_run(ctx, run_id, "linked")
    tracer = make_tracer(ctx, run_id, config_dir)
    settings = load_pipeline_settings(config_dir)
    text = objective_text(ctx, run)
    graph = _latest_graph(ctx, run_id)
    nodes = {n["nodeId"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    node_levels = {nid: n["level"] for nid, n in nodes.items()}
    levels = [lv for lv in GRAPH_LEVELS if lv in set(node_levels.values())]
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e["fromNodeId"]].append(e["toNodeId"])
    confidence = {
        (c["fromNodeId"], c["toNodeId"]): float(c["linkConfidence"]) for c in ctx.store.list_link_checks(run_id)
    }
    digest = _digest(ctx.store.list_deliberations(run_id))
    constraints = run.get("constraintsInForce") or {}
    weights = settings.factorWeights

    current: list[Doc] = []
    for level_no, level in enumerate(levels, start=1):
        if level_no == 1:
            candidates = [
                _candidate([nid], nodes, confidence, run_id) for nid, lv in node_levels.items() if lv == level
            ]
        else:
            candidates = [
                _candidate([*c["nodeIds"], child], nodes, confidence, run_id)
                for c in current
                for child in children.get(c["nodeId"], [])
                if node_levels.get(child) == level
            ]
        if not candidates:
            current = []
            break

        scored: list[Doc] = []
        unscored: list[Doc] = []
        for start in range(0, len(candidates), BEAM_SCORING_CHUNK):
            chunk = candidates[start : start + BEAM_SCORING_CHUNK]
            payload = {
                "candidates": [{"pathId": c["pathId"], "labels": c["nodeLabels"]} for c in chunk],
                "objectiveText": text,
                "deliberations": digest,
                "linkConfidences": {c["pathId"]: c["linkConfidences"] for c in chunk},
            }
            with tracer.step("search_research", "beam_search", "score_candidates", right="keep_path") as step:
                step.set_inputs({"level": level, "candidates": len(chunk)})
                result = model_call(
                    ctx, tracer, BeamScoring, prompts.messages(prompts.BEAM_SCORING, payload),
                    match_key=f"beam:{level}:{start}", prompt_version=prompts.BEAM_SCORING, run_id=run_id,
                )
                by_id = {s.pathId: s for s in result.candidates}
                for c in chunk:
                    s = by_id.get(c["pathId"])
                    if s is None:
                        unscored.append({
                            **c, "searchScore": 0.0, "outcome": "pruned", "reason": "the model did not score this path",
                            "pathsBelow": 0,
                        })
                        continue
                    factors = {
                        "relevance": s.relevance.model_dump(),
                        "feasibility": s.feasibility.model_dump(),
                        "timing": s.timing.model_dump(),
                        "cost": s.cost.model_dump(),
                    }
                    record = build_scored_record(c["pathId"], factors, weights, c["meanLinkConfidence"])
                    scored.append({
                        **c, **record,
                        "pathsBelow": paths_below(edges, levels, node_levels, {c["nodeId"]}),
                    })
                step.set_outputs({"scored": len(chunk) - sum(1 for c in chunk if c["pathId"] not in by_id)})

        with tracer.step("search_research", "beam_search", "prune_level", right="prune_path") as step:
            step.set_inputs({"level": level, "scored": len(scored), "beamWidth": settings.beam.width})
            passed, dropped = filter_beam(scored, constraints, {"nodes": nodes})
            diverse, duplicates = diversity_filter(passed, level)
            kept, pruned = keep_top(diverse, settings.beam.width)
            step.set_outputs({"kept": len(kept), "pruned": len(pruned) + len(dropped) + len(duplicates)})
            step.set_decision(f"kept {len(kept)} of {len(candidates)}")

        outcomes = [*kept, *pruned, *dropped, *duplicates, *unscored]
        ctx.store.create_beam_level(run_id, level_no, {
            "levelNo": level_no,
            "levelName": level,
            "scored": [
                {
                    "pathId": c["pathId"],
                    "label": " > ".join(c["nodeLabels"]),
                    "searchScore": c.get("searchScore", 0.0),
                    "factors": c.get("factors", {}),
                    "meanLinkConfidence": c.get("meanLinkConfidence"),
                    "outcome": c.get("outcome", "pruned"),
                    "reason": c.get("reason"),
                    "rank": c.get("rank"),
                    "pathsBelow": c.get("pathsBelow", 0),
                }
                for c in outcomes
            ],
        })
        current = kept

    complete = [c for c in current if len(c["nodeIds"]) == len(levels)] if levels else []
    final, deferred, shortfall = select_final(complete, settings.beam.finalPaths)
    if not complete and levels:
        shortfall = {"wanted": settings.beam.finalPaths, "found": 0, "reason": "no path reached the last level"}

    with tracer.step("search_research", "beam_search", "select_final_paths", right="keep_path") as step:
        step.set_inputs({"complete": len(complete), "finalPaths": settings.beam.finalPaths})
        now = ctx.now().isoformat()
        for status, group in (("final", final), ("deferred", deferred)):
            for c in group:
                ctx.store.upsert_path({
                    "pathId": c["pathId"],
                    "marketRunId": run_id,
                    "nodeIds": c["nodeIds"],
                    "nodeLabels": c["nodeLabels"],
                    "searchScore": c.get("searchScore", 0.0),
                    "factors": c.get("factors", {}),
                    "meanLinkConfidence": c.get("meanLinkConfidence"),
                    "status": status,
                    "isFinal": status == "final",
                    "statusHistory": [{
                        "status": status, "reason": c.get("reason") or "selected from the last beam level",
                        "level": levels[-1] if levels else None, "at": now, "stepId": step.step_id,
                    }],
                })
        step.set_outputs({"final": len(final), "deferred": len(deferred), "shortfall": shortfall})

    ctx.store.transition_market_run(run_id, "linked", "searched", {"finalPathShortfall": shortfall})
    return {"finalPaths": len(final), "deferred": len(deferred), "shortfall": shortfall}


# --------------------------------------------------------------------------------------------------
# assess
# --------------------------------------------------------------------------------------------------


def stage_assess(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    run = load_run(ctx, run_id, "searched")
    tracer = make_tracer(ctx, run_id, config_dir)
    grammar = load_grammar(config_dir)
    text = objective_text(ctx, run)
    digest = _digest(ctx.store.list_deliberations(run_id), set(PER_PATH_KEYS))
    allowed = {k: [] if (dim := grammar.by_key(k)) is None else dim.states for k in PER_PATH_KEYS}

    finals = [p for p in ctx.store.list_paths(run_id) if p.get("isFinal")]
    for path in finals:
        payload = {
            "path": path.get("nodeLabels", []),
            "objectiveText": text,
            "deliberations": digest,
            "allowedStates": allowed,
        }
        with tracer.step(ASSESS_LAYER, "path_assessor", "assess_path", right=ASSESS_RIGHT) as step:
            step.set_inputs({"pathId": path["pathId"]})
            problem = ""
            records: list[Doc] = []
            for attempt in (1, 2):
                result = model_call(
                    ctx, tracer, PathAssessment, prompts.messages(prompts.PATH_ASSESSMENT, payload),
                    match_key=f"assess:{path['pathId']}:{attempt}", prompt_version=prompts.PATH_ASSESSMENT,
                    run_id=run_id,
                )
                try:
                    records = assess_records(grammar, [d.model_dump() for d in result.dimensions])
                    break
                except ValueError as exc:
                    problem = str(exc)
            else:
                raise ExternalServiceError(f"assessment of path {path['pathId']} is invalid after a retry: {problem}")
            ctx.store.upsert_path({"pathId": path["pathId"], "marketRunId": run_id, "assessment": records})
            step.set_outputs({"dimensions": len(records)})

    ctx.store.transition_market_run(run_id, "searched", "assessed")
    return {"assessedPaths": len(finals)}


# --------------------------------------------------------------------------------------------------
# companies: one feature 002 child run per final path (research R1, R13)
# --------------------------------------------------------------------------------------------------


def _child_steps() -> tuple[tuple[str, str, str, str, Any], ...]:
    """(operation, layer, actor, right, step function) for feature 002's three steps, called unchanged."""
    from hipstraw_mm.steps.discover import discover
    from hipstraw_mm.steps.review import review
    from hipstraw_mm.steps.verify import verify

    return (
        ("discover_companies", "search_research", "company_search", "discover_companies", discover),
        ("verify_companies", "search_research", "company_search", "discover_companies", verify),
        ("review_companies", "market_manager", "review", "record_disposition", review),
    )


def _research_path(ctx: Context, tracer: Tracer, child_id: str) -> str | None:
    """discover, verify, review on one child run, each a traced step. Returns an error message or None.

    A failed child run is a process failure, not evidence against the path (MDC spec 2.9): the error is
    recorded on the path and the other paths continue.
    """
    for operation, layer, actor, right, step_fn in _child_steps():
        llm_before, search_before = ctx.llm.calls, ctx.search.calls
        try:
            with tracer.step(layer, actor, operation, right=right) as step:
                step.set_inputs({"childRunId": child_id})
                result = step_fn(ctx, child_id)
                child = ctx.store.get_run(child_id) or {}
                step.set_outputs({
                    "message": result.message, "counts": result.counts, "childStatus": child.get("status"),
                })
                for warning in result.warnings:
                    step.add_check("child_run_warning", "fail", warning)
        except ModelCallCeilingError:
            raise
        except Exception as exc:  # noqa: BLE001 - recorded on the path; one path failing must not stop the others
            return f"{operation}: {type(exc).__name__}: {exc}"
        finally:
            tracer.record_usage(model_calls=ctx.llm.calls - llm_before, searches=ctx.search.calls - search_before)
    child = ctx.store.get_run(child_id) or {}
    tracer.record_usage(fetches=int((child.get("counts") or {}).get("fetches") or 0))
    return None


def stage_companies(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    from hipstraw_mm.market import companies as comp
    from hipstraw_mm.steps.position import create_run

    run = load_run(ctx, run_id, "assessed")
    tracer = make_tracer(ctx, run_id, config_dir)
    settings = load_pipeline_settings(config_dir)
    grammar = load_grammar(config_dir)
    program = ctx.store.get_program(run["programId"])
    if program is None:
        raise PreconditionError(f"program {run['programId']!r} not loaded (run intake first)")
    graph = _latest_graph(ctx, run_id)
    nodes = {n["nodeId"]: n for n in graph.get("nodes", [])}
    interests = comp.interest_ids_for(program, settings.defaultInterestIds)
    metro_names = [m.name for m in ctx.config.metros_in_force()]
    evidence_settings = settings.evidenceStates.model_dump()
    assessed_by = {d.key: d.assessedBy for d in grammar.dimensions}

    finals = [p for p in ctx.store.list_paths(run_id) if p.get("isFinal")]
    per_path: list[tuple[str, str, list[Doc]]] = []
    unresolved: list[Doc] = []
    for n, path in enumerate(finals, start=1):
        pid = path["pathId"]
        child_id = comp.child_run_id(run_id, n)
        candidate = comp.path_candidate(run_id, run["programId"], path)
        ctx.store.upsert_candidate(candidate)
        position = comp.position_for_path(path, nodes, interests, metro_names)
        if ctx.store.get_run(child_id) is None:
            create_run(
                ctx, program, candidate["candidateId"], position, child_id,
                budget_overrides={"companiesKept": settings.beam.companiesPerPath},
                parent_market_run_id=run_id, path_id=pid,
            )
        error = _research_path(ctx, tracer, child_id)
        found = comp.companies_from_child_run(ctx.store, child_id)
        if error:
            unresolved.append({"kind": "company_research", "ref": pid, "reason": error})

        with tracer.step(
            "position_evaluation", "evidence_evaluator", "evaluate_evidence", right="evaluate_evidence"
        ) as step:
            states = comp.evidence_states(found, evidence_settings, assessed_by)
            packet = comp.research_packet(child_id, found, error)
            summary = {k: states[k] for k in ("sufficiency", "quality", "criticalUnknowns")}
            step.set_inputs({"pathId": pid, "childRunId": child_id, "companies": len(found)})
            step.set_outputs({**summary, "completionReason": packet["completionReason"]})
            included = [c for c in found if c["disposition"] == "include"]
            status = "has_evidence" if included else "no_evidence_found"
            ctx.store.upsert_path({
                "pathId": pid,
                "marketRunId": run_id,
                "childRunId": child_id,
                "position": position.model_dump(),
                "evidenceStates": summary,
                "verification": states["detail"],
                "researchPacket": packet,
                "companyDomainKeys": [c["domainKey"] for c in found],
                "canStillFill": error is not None or any(c["needsVerification"] for c in found),
                "status": status,
                "statusHistory": [*path.get("statusHistory", []), {
                    "status": status,
                    "reason": f"{len(included)} included of {len(found)} companies in child run {child_id}",
                    "level": None, "at": ctx.now().isoformat(), "stepId": step.step_id,
                }],
            })
        per_path.append((pid, child_id, found))

    for doc in comp.merge_market_companies(run_id, per_path):
        ctx.store.upsert_market_company(doc)
    ctx.store.transition_market_run(
        run_id, "assessed", "verified", {"unresolved": [*run.get("unresolved", []), *unresolved]}
    )
    total = sum(len(cs) for _, _, cs in per_path)
    included_total = sum(1 for _, _, cs in per_path for c in cs if c["disposition"] == "include")
    return {"paths": len(finals), "companies": total, "included": included_total}


# --------------------------------------------------------------------------------------------------
# buyers: roles from the child runs' passing evidence (research R14)
# --------------------------------------------------------------------------------------------------


def stage_buyers(ctx: Context, run_id: str, config_dir: Path) -> Doc:
    load_run(ctx, run_id, "verified")
    tracer = make_tracer(ctx, run_id, config_dir)
    companies = ctx.store.list_market_companies(run_id)
    finals = [p for p in ctx.store.list_paths(run_id) if p.get("isFinal") and p.get("childRunId")]

    kept_total = 0
    for path in finals:
        pid, child_id = path["pathId"], path["childRunId"]
        evidence = {e["evidenceId"]: e for e in ctx.store.list_evidence(child_id)}
        on_path = [
            (c, link) for c in companies for link in c.get("links", [])
            if link["pathId"] == pid and link["disposition"] != "exclude"
        ]
        if not on_path:
            continue
        payload_companies = []
        for c, link in on_path:
            docs = [
                e for e in evidence.values()
                if e.get("companyRecordId") == link["companyRecordId"] and e.get("check", {}).get("status") == "pass"
            ][:8]
            payload_companies.append({
                "companyRecordId": link["companyRecordId"],
                "name": c["name"],
                "disposition": link["disposition"],
                "evidence": [
                    {"evidenceId": e["evidenceId"], "claimField": e["claimField"],
                     "claimValue": e["claimValue"], "excerpt": e["excerpt"][:400]}
                    for e in docs
                ],
            })
        payload = {"pathId": pid, "path": path.get("nodeLabels", []), "companies": payload_companies}
        with tracer.step(
            "position_evaluation", "buyer_role_finder", "identify_buyer_roles", right="identify_buyer_roles"
        ) as step:
            step.set_inputs({"pathId": pid, "companies": len(on_path)})
            result = model_call(
                ctx, tracer, BuyerRoles, prompts.messages(prompts.BUYER_ROLES, payload),
                match_key=f"buyers:{pid}", prompt_version=prompts.BUYER_ROLES, run_id=run_id,
            )
            roles_by_record: dict[str, list[Doc]] = defaultdict(list)
            rejected: dict[str, str] = {}
            for role in result.roles:
                owners = {evidence.get(e, {}).get("companyRecordId") for e in role.evidenceIds}
                if len(owners) != 1 or None in owners:
                    continue
                record_id = str(owners.pop())
                own_docs = {e: d for e, d in evidence.items() if d.get("companyRecordId") == record_id}
                verdict = validate_buyer_role(role.model_dump(), own_docs)
                if verdict["kept"]:
                    roles_by_record[record_id].append(
                        {k: verdict["role"][k] for k in ("role", "authority", "evidenceIds", "rationale")}
                    )
                else:
                    rejected[record_id] = verdict["unknown"]["reason"]
            kept = 0
            for c, link in on_path:
                record_id = link["companyRecordId"]
                roles = roles_by_record.get(record_id, [])
                kept += len(roles)
                ctx.store.create_buyer_roles({
                    "marketRunId": run_id,
                    "pathId": pid,
                    "domainKey": c["domainKey"],
                    "companyRecordId": record_id,
                    "roles": roles,
                    "unknown": None if roles else {
                        "reason": rejected.get(record_id, "no stored evidence names a buying function"),
                    },
                })
            kept_total += kept
            step.set_outputs({"rolesKept": kept, "companies": len(on_path)})

    ctx.store.transition_market_run(run_id, "verified", "roled")
    return {"paths": len(finals), "roles": kept_total}
