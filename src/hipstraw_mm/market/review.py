"""Market Manager Review: the playbook's quick picker (§6), by rules only.

Reads the seven-axis Position, names the binding constraint, checks the blocks, then chooses the
stance, Strategy, Play, Line, Moves and the Recommended next step from the playbook's own tables,
ending in a Disposition and an attention tier. Where the playbook leaves a choice open, the rule comes
from config/playbook/picker.yaml and is labelled a Hipstraw proposal.
"""

from __future__ import annotations

from typing import Any

from hipstraw_mm.market.playbook import STANCES, Playbook

Doc = dict[str, Any]


# ---------------------------------------------------------------- 2. Position from desk research


def assess_axes(pb: Playbook, path: Doc, case: Doc | None, buyer_roles: int) -> list[Doc]:
    """Seven axis states from what desk research can show, using the playbook's own state definitions.

    Desk research can identify a job, companies and buying roles, and model economics. It cannot show
    costly buyer behaviour, permissioned reach, a tested offer or route, working delivery or a repeat,
    so those axes stay at their first state (rule 10: missing evidence is never read as success).
    """
    case = case or {}
    packet = case.get("packet") or path.get("researchPacket") or {}
    estimate = case.get("economics")
    found = int(packet.get("found") or 0)
    if packet.get("contradictions"):
        mp1 = ("Contested", f"{len(packet['contradictions'])} contradiction(s) between sources and claims.")
    elif path.get("assessment"):
        mp1 = ("Hypothesis", "A specific job was found by desk research; no buyer has shown costly behaviour yet.")
    else:
        mp1 = ("Not mapped", "No job, actor or substitute assessed yet.")
    mp2_note = (f"{found} companies and {buyer_roles} buying role(s) identified from public sources; reach with "
                "permission is not tested (rule 10).")
    if estimate:
        mp6 = ("Assumed", f"A model estimate exists ({_money(estimate.get('valuePoolUsdLow'))}–"
                          f"{_money(estimate.get('valuePoolUsdHigh'))} a year, hypothesis); "
                          "no real cohort has tested it.")
    else:
        mp6 = ("Not modeled", "No cost-to-serve or acquisition model exists.")
    states = {
        "MP1": mp1,
        "MP2": ("Unknown", mp2_note),
        "MP3": ("Concept", "The proposition is described in the mandate, not yet experienced by buyers."),
        "MP4": ("Untested", "No route has run a capped test."),
        "MP5": ("Fragile", "Supply, quality and fulfilment are unproven."),
        "MP6": mp6,
        "MP7": ("First of its kind", "No repeat yet."),
    }
    out = []
    for axis in pb.axes:
        state, note = states[axis.id]
        registry = next(s.registry for s in axis.states if s.screen == state)
        out.append({"axis": axis.id, "screenName": axis.screenName, "state": state, "registryState": registry,
                    "note": note, "source": "desk research"})
    return out


def _money(v: Any) -> str:
    if v is None:
        return "?"
    v = float(v)
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}K"


def binding_constraint(pb: Playbook, axes: list[Doc]) -> str:
    rule = pb.picker.bindingConstraint
    state = {a["axis"]: a["state"] for a in axes}
    for axis, worst in rule.worstFirst:
        if state.get(axis) == worst:
            return axis
    return next((a for a in rule.order if state[a] not in rule.settled.get(a, [])), rule.order[0])


# ---------------------------------------------------------------- 4–7. Stance, Strategy, Play, Line


def choose_stance(pb: Playbook, axes: list[Doc], binding: str) -> Doc:
    """§7.1: the default for the binding axis state; a × on any axis rules a stance out."""
    matrix = pb.matrices.positionStance
    ruled_out: dict[str, list[str]] = {}
    for a in axes:
        for stance, cell in matrix[a["axis"]][a["state"]].items():
            if cell == "never":
                ruled_out.setdefault(stance, []).append(a["axis"])
    row = matrix[binding][next(a["state"] for a in axes if a["axis"] == binding)]
    default = next((s for s, c in row.items() if c == "default"), None)
    allowed = [s for s in STANCES if row.get(s) in ("default", "allowed") and s not in ruled_out]
    chosen = default if default and default not in ruled_out else (allowed[0] if allowed else "Listen")
    return {"stance": chosen, "default": default, "allowed": allowed,
            "ruledOut": [{"stance": s, "by": by} for s, by in ruled_out.items()]}


def _priority_plays(pb: Playbook, market_types: list[str]) -> list[str]:
    return list(dict.fromkeys(p for t in market_types for p in pb.market_type(t).priorityPlays))


def choose_strategy_and_play(pb: Playbook, binding_state: tuple[str, str], stance: str,
                             market_types: list[str]) -> Doc:
    """§2.2 calls for Strategies; §7.2 must allow the stance; §7.3 × §7.7 picks the Play."""
    calls = pb.calls_for(*binding_state)
    priority = _priority_plays(pb, market_types)
    fits = [s for s in calls if pb.strategy(s).stance.permits(stance)] or calls

    def plays_for(sid: str, which: str) -> list[str]:
        st = pb.strategy(sid)
        pool = st.plays.primary if which == "primary" else st.plays.primary + st.plays.also
        ranked = [p for p in priority if p in pool] if which != "any" else pool
        return [p for p in ranked if pb.play(p).stance.permits(stance)]

    for which, reason in (("primary", "its primary plays include a priority play for the market type"),
                          ("also", "it is used by a priority play for the market type"),
                          ("any", "no play matched the market type, so its first stance-compatible play is used")):
        for sid in fits:
            plays = plays_for(sid, which)
            if plays:
                return {"strategy": sid, "play": plays[0], "considered": calls,
                        "reason": f"{sid} is called for by {binding_state[0]} {binding_state[1]} (§2.2), allows "
                                  f"{stance} (§7.2), and {reason} (§7.3, §7.7)."}
    sid = fits[0]
    return {"strategy": sid, "play": None, "considered": calls,
            "reason": f"No play of {sid} allows {stance}; escalate to the Market Manager "
                      "(§7, 'nothing qualified fits')."}


def plan_line(pb: Playbook, play_id: str, stance: str, performed: set[str]) -> Doc:
    """§7.4 preferred Line sequence and §7.5 steps, each marked done, ruled out, or to do."""
    play = pb.play(play_id)
    sequence = play.lines.preferred
    current = sequence[0]
    line = pb.line(current)
    steps = []
    for s in line.steps:
        status = "to do"
        if s.id in performed:
            status = "done"
        elif s.id.startswith("M") and stance in pb.move(s.id).stance.never:
            status = "ruled out"
        steps.append({"id": s.id, "name": pb.step_name(s.id), "text": s.text, "status": status})
    nxt = next((s for s in steps if s["status"] == "to do"), None)
    return {"sequence": sequence, "sequenceText": play.lines.preferredText, "current": current,
            "currentName": line.name, "steps": steps, "next": nxt, "then": sequence[1] if len(sequence) > 1 else None,
            "window": line.window, "stopIf": line.stopIf, "doneWhen": line.doneWhen}


def next_step(pb: Playbook, plan: Doc, mode: str) -> Doc | None:
    step = plan["next"]
    if step is None:
        then = plan["then"]
        if not then:
            return None
        first = pb.line(then).steps[0].id
        step = {"id": first, "name": pb.step_name(first), "text": pb.line(then).steps[0].text}
        where = f"Line {then} {pb.line(then).name}, step 1 (Line {plan['current']} is done)"
    else:
        idx = next(i for i, s in enumerate(plan["steps"]) if s["id"] == step["id"])
        where = f"Line {plan['current']} {plan['currentName']}, step {idx + 1} of {len(plan['steps'])}"
    out: Doc = {"id": step["id"], "name": step["name"], "text": step.get("text"), "where": where}
    if step["id"].startswith("A"):
        a = pb.action(step["id"])
        out |= {"whoCanRun": a.whoCanRun, "tier": a.tier, "allowedInMode": a.tier <= 2,
                "example": a.showsInActivityAs}
    elif step["id"].startswith("M"):
        m = pb.move(step["id"])
        out |= {"doneWhen": m.doneWhen, "tasks": m.tasks,
                "allowedInMode": all(pb.action(t).tier <= 2 for t in m.tasks)}
    out["mode"] = mode
    return out


def gambit_options(pb: Playbook, play_id: str, stance: str) -> list[Doc]:
    out = []
    for gid in pb.play(play_id).gambits:
        g = pb.gambit(gid)
        cell = pb.matrices.gambitStance[gid].get(stance)
        out.append({
            "id": gid, "name": g.name, "give": g.give, "get": g.get, "maxLoss": g.maxLossIllustrative,
            "fallback": g.fallback, "approver": g.approver,
            "fitsStance": cell in ("default", "allowed"),
            "needsStance": None if cell in ("default", "allowed") else g.stance.default,
            "authorized": False,
        })
    return out


def actions_for(pb: Playbook, plan: Doc) -> list[Doc]:
    """Actions behind the steps still to do: who can run each, and whether Advisory mode allows it."""
    ids: list[str] = []
    for s in plan["steps"]:
        if s["status"] != "to do":
            continue
        if s["id"].startswith("A"):
            ids.append(s["id"])
        elif s["id"].startswith("M"):
            ids.extend(pb.move(s["id"]).tasks)
    out = []
    for aid in dict.fromkeys(ids):
        a = pb.action(aid)
        out.append({"id": aid, "name": a.name, "tier": a.tier, "tierName": a.tierName, "whoCanRun": a.whoCanRun,
                    "allowedInMode": a.tier <= 2})
    return out


# ---------------------------------------------------------------- 10. Disposition


def disposition(pb: Playbook, axes: list[Doc], stance: str, packet: Doc) -> Doc:
    rule = pb.picker.disposition
    state = {a["axis"]: a["state"] for a in axes}
    for o in rule.overrides:
        if state.get(o.axis) == o.state:
            d, why = o.disposition, f"{o.axis} is {o.state}"
            break
    else:
        found, included = int(packet.get("found") or 0), int(packet.get("included") or 0)
        if found and not included and not int(packet.get("needsVerification") or 0):
            d, why = rule.noIncludedCompanies, "research found companies but Review excluded every one"
        else:
            d, why = rule.byStance[stance], f"stance {stance}"
    return {"disposition": d, "attention": rule.attention[d], "reason": why}


def run_review(pb: Playbook, path: Doc, case: Doc | None, *, buyer_roles: int, market_types: list[str],
               performed: set[str]) -> Doc:
    """The full chain for one market unit."""
    axes = assess_axes(pb, path, case, buyer_roles)
    binding = binding_constraint(pb, axes)
    binding_state = next(a["state"] for a in axes if a["axis"] == binding)
    stance = choose_stance(pb, axes, binding)
    mode = pb.picker.executionMode
    blocks = {"mode": mode, "blocked": [],
              "notes": ["Advisory mode: assess, model and recommend; no external contact (§5.2).",
                        "Gambits are modeled, never authorized (rules 14 and 18)."]}
    pick = choose_strategy_and_play(pb, (binding, binding_state), stance["stance"], market_types)
    packet = (case or {}).get("packet") or path.get("researchPacket") or {}
    disp = disposition(pb, axes, stance["stance"], packet)
    chain: Doc = {
        "playbookVersion": pb.version, "pickerVersion": pb.picker.version,
        "axes": axes, "bindingConstraint": {"axis": binding, "state": binding_state,
                                            "rule": "picker.yaml (Hipstraw proposal)"},
        "blocks": blocks, "stance": stance, "marketTypes": market_types,
        "strategy": pick["strategy"], "strategyName": pb.strategy(pick["strategy"]).name,
        "play": pick["play"], "playName": pb.play(pick["play"]).name if pick["play"] else None,
        "pickReason": pick["reason"],
        **disp,
    }
    if pick["play"]:
        plan = plan_line(pb, pick["play"], stance["stance"], performed)
        chain |= {"line": plan, "nextStep": next_step(pb, plan, mode),
                  "gambits": gambit_options(pb, pick["play"], stance["stance"]),
                  "actions": actions_for(pb, plan)}
    else:
        chain |= {"line": None, "nextStep": None, "gambits": [], "actions": []}
    return chain


def performed_steps(registry: Doc, operations_ran: set[str]) -> set[str]:
    """Playbook Moves and Actions our own capabilities and skills already carried out in this run.

    A registry item counts when one of its traced operations ran; items with no operations of their
    own (they run inside another traced step) count once the run has reached the Review.
    """
    done: set[str] = set()
    for agent in registry.get("agents", []):
        for item in [*agent.get("innateCapabilities", []), *agent.get("skills", [])]:
            ops = item.get("operations", [])
            if ops and not set(ops) & operations_ran:
                continue
            for link in item.get("playbook", []):
                ref = link.split()[0]
                if ref[:1] in ("M", "A") and ref[1:].isdigit():
                    done.add(ref)
    return done
