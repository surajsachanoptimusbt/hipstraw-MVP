"""The agent's run of a market validation request, stage by stage (Nov 6 architecture): ingest the request,
review its evidence against the demand rubric, set each hypothesis's position, let the playbook pick the Lines,
lay out the gated workflow of Moves, and stop for a reviewer's approval.

No model decides anything here: the rubric judges, the playbook's rules pick, and the run is the same every time
for the same request. Each step is written to the ledger as it happens, and the case moves to the step's stage in
the same transaction, so the desk can follow the agent live. `pace` waits between steps so a person can follow
them on screen; it changes nothing else.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from hipstraw_mm.desk.models import Case, Stage
from hipstraw_mm.desk.store import DeskStore
from hipstraw_mm.foundry.demand import DemandRubric
from hipstraw_mm.foundry.playbook import HypothesisPlay, Recommendation, recommend
from hipstraw_mm.foundry.walkthrough import Thesis

AGENT = "Hipstraw agent"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _count(n: int, noun: str, many: str = "") -> str:
    return f"{n} {noun if n == 1 else many or noun + 's'}"


def _state(s: str) -> str:
    return s.replace("_", " ")


def _steps(thesis: Thesis, rec: Recommendation, rubric: DemandRubric) -> list[dict[str, Any]]:
    """The agent's steps, in order: each {stage, actor, kind, title, detail, data}."""
    out: list[dict[str, Any]] = []

    def add(stage: Stage, kind: str, title: str, detail: str = "", data: dict[str, Any] | None = None,
            actor: str = "agent") -> None:
        out.append({"stage": stage, "actor": actor, "who": AGENT if actor == "agent" else "Hipstraw",
                    "kind": kind, "title": title, "detail": detail, "data": data or {}})

    hyps = rec.hypotheses
    evidence = {e.id for h in hyps for e in h.evidence}
    where = f"{thesis.market}" + (f", {thesis.geography}" if thesis.geography else "")
    add("ingest", "step", "Read the request",
        f"{thesis.product}: {where}. {_count(len(hyps), 'demand hypothesis', 'demand hypotheses')}, "
        f"{_count(len(evidence), 'evidence item')}. Buyer "
        f"{thesis.buyer}, sold {thesis.motion.replace('_', '-')}.")
    for h in hyps:
        add("ingest", "step", f"Framed {h.id} {h.name}",
            f"Does \"{h.segment}\" demand \"{h.offering}\"? Who decides and pays: {h.buyerRole}.",
            {"hypothesis": h.id})

    for h in hyps:
        rungs = Counter(f"{e.type.replace('_', ' ')} (rung {e.rung[1:]}{'' if e.demand else ', not demand'})"
                        for e in h.evidence)
        demand = sum(e.demand and e.fromSegment for e in h.evidence)
        add("review", "finding", f"Placed {h.id}'s evidence on the ladder",
            (", ".join(f"{n} {k}" for k, n in rungs.items()) or "No evidence yet")
            + f". {demand} items from the segment count as demand.", {"hypothesis": h.id})
        states = Counter(f.state for f in h.findings if f.dimension != "Gate")
        shown = [f"{f.ref} {_state(f.state)}" for f in h.findings if f.state in ("met", "partly", "not_met")]
        add("review", "finding", f"Judged {h.id} against the demand rubric",
            "; ".join(shown + [f"{n} {_state(s)}" for s, n in states.items() if s in ("unknown", "not_applicable")]),
            {"hypothesis": h.id, "findings": [f.model_dump() for f in h.findings]})

    for h in hyps:
        add("position", "step", f"Position of {h.id}: {_state(h.decision)}", f"{h.decisionText}. Next: {h.checkpoint}.",
            {"hypothesis": h.id, "decision": h.decision, "checkpoint": h.checkpoint})

    add("recommend", "step", "Opened the playbook",
        f"{rec.repertoireVersion}: {len(rubric.tasks)} tasks, {len(rubric.lines)} Lines, {len(rubric.moves)} Moves, "
        f"all predefined. {rec.ranking}.", actor="system")
    for h in hyps:
        for t in h.tasks:
            options = "; ".join(f"{o.lineId} {o.name}: " + (f"eligible, rank {o.rank}" if o.eligible else
                                "not eligible, " + ", ".join(c.text for c in o.checks if not c.ok))
                                for o in t.options)
            picked = f"{t.lineId} {t.lineName}" if t.lineId else "no Line"
            add("recommend", "pick", f"{h.id} · {t.taskId} {t.task} → {picked}", f"Available: {options}.",
                {"hypothesis": h.id, "task": t.taskId, "line": t.lineId})

    for h in hyps:
        add("workflow", "step", f"Laid out {h.id}'s workflow", _workflow(h), {"hypothesis": h.id})

    add("approval", "gate", "Waiting on a reviewer to approve the plan",
        f"Plan {rec.payload_hash()[:12]}: {_count(sum(t.lineId is not None for h in hyps for t in h.tasks), 'Line')} "
        f"across {_count(len(hyps), 'hypothesis', 'hypotheses')}. Moves that contact people, publish or spend run "
        "only after approval.",
        {"payloadHash": rec.payload_hash()})
    return out


def _workflow(h: HypothesisPlay) -> str:
    moves = [m for t in h.tasks for m in t.moves]
    lines = sum(t.lineId is not None for t in h.tasks)
    nxt = next((m for m in moves if m.status == "next"), None)
    return (f"{_count(len(moves), 'Move')} in {_count(lines, 'Line')}: {sum(m.status == 'done' for m in moves)} done, "
            f"{sum(m.needsCharter for m in moves)} need an approved charter."
            + (f" Next: {nxt.id} {nxt.name}." if nxt else ""))


def run_agent(store: DeskStore, case_id: str, rubric: DemandRubric, pace: float = 0.0) -> Case:
    case = store.case(case_id)
    if case is None:
        raise KeyError(case_id)
    thesis = Thesis.model_validate(case.thesis)
    rec = recommend(thesis, rubric)
    for step in _steps(thesis, rec, rubric):
        if pace:
            time.sleep(pace)
        at = now()
        case = case.model_copy(update={"stage": step["stage"], "updatedAt": at})
        if step["kind"] == "gate":
            case = case.model_copy(update={
                "state": "waiting_review", "waitingOn": "reviewer",
                "recommendation": rec.model_dump(mode="json"), "payloadHash": rec.payload_hash()})
        store.commit(case, [{"caseId": case.id, "at": at, **step}])
    return case
