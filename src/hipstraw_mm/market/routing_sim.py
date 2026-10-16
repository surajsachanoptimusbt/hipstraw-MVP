"""Routing simulation: run the real vichara stage with the open-weight route on, then read the trace back
as a walk-through in the order of the routing diagram (incoming task, router, open-weight, validation,
frontier, saved result and lineage).

Nothing here decides a route or calls a model directly: the stage and the router do that. This module
only switches the open-weight route on for one run and reports what the trace recorded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hipstraw_mm.context import Context
from hipstraw_mm.market.router import load_routing
from hipstraw_mm.market.routing_report import build_simulation

Doc = dict[str, Any]


def simulate(ctx: Context, program_id: str, objective_pdfs: list[Path], config_dir: Path) -> Doc:
    """Open a market run for the program and run the vichara stage with the open-weight route on."""
    from hipstraw_mm.market.stages import stage_vichara
    from hipstraw_mm.market.start import market_start

    base = load_routing(config_dir)
    routing = base.model_copy(update={"openWeight": base.openWeight.model_copy(update={"enabled": True})})
    run_id = market_start(ctx, program_id, objective_pdfs)
    stage_vichara(ctx, run_id, config_dir, routing_config=routing)
    # The run stops after vichara on purpose; the viewer labels it instead of showing it as running.
    ctx.store.upsert_market_run({
        "marketRunId": run_id, "simulation": {"stage": "vichara", "routerVersion": routing.version},
    })
    sim = build_simulation(ctx.store, run_id, config_dir)
    assert sim is not None
    if not sim["openWeight"]["available"] and ctx.open_llm is not None:
        sim["openWeight"] = {"model": ctx.open_llm.model, "available": True}
    return sim


# --------------------------------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------------------------------


def _secs(ms: int | None) -> str:
    return f"{(ms or 0) / 1000:.1f} s"


def _money(v: float | None) -> str:
    return "price unknown" if v is None else f"${v:.4f}"


def _attempt_line(a: Doc) -> str:
    who = a["model"] or "?"
    if a["status"] != "ok":
        return f"{who} failed after {_secs(a['latencyMs'])}: {(a['error'] or '')[:110]}"
    tokens = f"{a['inputTokens'] or 0:,} in / {a['outputTokens'] or 0:,} out tokens"
    return f"{who} answered in {_secs(a['latencyMs'])} ({tokens}, {_money(a['usd'])})"


def render_text(sim: Doc) -> str:
    out: list[str] = []
    ow = sim["openWeight"]
    out += [
        f"ROUTING SIMULATION  {sim['program']['name']} ({sim['program']['programId']})",
        f"run {sim['runId']}  |  router {sim['routerVersion']}",
        f"open-weight tier: {ow['model'] if ow['available'] else 'none configured (simple tasks go to frontier, R5)'}"
        f"  |  frontier tier: {sim['frontier']['model']}",
        f"objective: program text + {len(sim['objective']['documents'])} document(s), "
        f"{sim['objective']['chars']:,} characters",
        "",
        "1. RUBRIC: where each task goes, decided by rules (no model call)",
        f"   {'task':24s} {'class':8s} {'wired':6s} {'rule':5s} {'route':12s} why",
    ]
    for r in sim["rubric"]:
        out.append(f"   {r['task']:24s} {r['class']:8s} {'yes' if r['wired'] else 'no':6s} "
                   f"{r['ruleId']:5s} {r['route']:12s} {r['why']}")
    out += ["", "2. WALK-THROUGH: the vichara stage on this objective, read back from the trace"]
    for n, e in enumerate(sim["walkthrough"], start=1):
        out.append("")
        out.append(f"[{n}] {e['task']} | {e['subject']}")
        size = f"  [prompt {e['inputChars']:,} chars]" if e["inputChars"] else ""
        out.append(f"    Incoming task   {e['question'] or e['operation'].replace('_', ' ')}{size}")
        if not e["routed"]:
            out.append("    Router          not wired yet: stays on frontier as before")
            for a in e["attempts"]:
                out.append(f"    Frontier        {_attempt_line(a)}")
        else:
            r = e["router"]
            target = {"open_weight": "open-weight", "frontier": "frontier", "rules": "rules"}[r["route"]]
            out.append(f"    Router          {r['ruleId']} {r['why']} -> {target}")
            for a in e["attempts"]:
                label = "Open-weight" if a["tier"] == "open_weight" else "Frontier"
                if a["tier"] == "frontier" and e["outcome"]["escalated"]:
                    if any(c["name"].startswith("open_weight.") for c in e["checks"]):
                        out.append(f"    {'Validation':15s} {_checks(e['checks'], 'open_weight')}")
                        out.extend(_quote_lines(e, "open_weight"))
                    out.append(f"    {'Escalate':15s} {e['outcome']['escalationReason'][:140]}")
                out.append(f"    {label:15s} {_attempt_line(a)}")
            if not e["outcome"]["escalated"]:
                tier = e["outcome"]["servedBy"]
                if any(c["name"].startswith(f"{tier}.") for c in e["checks"]):
                    note = "" if tier == "open_weight" else " (recorded only)"
                    out.append(f"    {'Validation':15s} {_checks(e['checks'], tier)}{note}")
            elif any(c["name"].startswith("frontier.") for c in e["checks"]):
                out.append(f"    {'Frontier check':15s} {_checks(e['checks'], 'frontier')} (recorded only)")
                out.extend(_quote_lines(e, "frontier"))
        saved = e["saved"]
        items = ", ".join(f"{v} {k}" for k, v in saved["items"].items()) or "nothing"
        lineage = saved.get("lineage")
        line = f"    Saved           {saved['record']}: {items}"
        if lineage:
            line += f"  |  lineage {lineage['routerVersion']} {lineage['ruleId']}, served by {lineage['servedBy']}"
            line += f" ({lineage['model']})"
        out.append(line)

    s = sim["summary"]
    c = s["cost"]
    out += [
        "",
        "3. SUMMARY",
        f"   routed calls {s['routedCalls']}: kept on open-weight {s['keptOnOpenWeight']}, "
        f"escalated {s['escalated']}, sent straight to frontier {s['frontierDirect']}",
        "   escalation reasons: " + (", ".join(f"{k} {v}" for k, v in s["escalationReasons"].items()) or "none"),
        f"   model calls: open-weight {s['modelCalls']['open_weight']}, frontier {s['modelCalls']['frontier']}"
        " (frontier includes repair, which is not routed yet)",
        f"   cost: open-weight ${c['openWeightUsd']:.4f} + frontier ${c['frontierUsd']:.4f} = ${c['totalUsd']:.4f}",
        f"   the same kept answers at frontier price: ${c['frontierEquivalentOfKept']:.4f}  "
        f"(all-frontier estimate ${c['allFrontierEstimateUsd']:.4f})",
    ]
    if c["unpricedCalls"]:
        out.append(f"   calls with no price entry: {c['unpricedCalls']}")
    return "\n".join(out) + "\n"


def _quote_lines(entry: Doc, tier: str) -> list[str]:
    """One line per quote that failed grounding, with the diagnosis from the validation log."""
    lines = []
    for check in (entry.get("validation") or {}).get(tier) or []:
        if check["id"] != "grounding":
            continue
        for q in (check.get("details") or {}).get("quotes", []):
            d = q.get("diagnosis")
            if q["found"] or not d:
                continue
            quote = q["quote"] if len(q["quote"]) <= 70 else q["quote"][:69] + "…"
            lines.append(f"{'':20s}quote {quote!r}: {d['verdict'].replace('_', ' ')}. {d['explanation']}")
    return lines


def _checks(checks: list[Doc], tier: str) -> str:
    mine = [c for c in checks if c["name"].startswith(f"{tier}.")]
    parts = []
    for c in mine:
        name = c["name"].split(".", 1)[1]
        parts.append(f"{name} pass" if c["status"] == "pass" else f"{name} FAIL ({c['reason'].split(' (')[0]})")
    return "; ".join(parts) or "no checks"
