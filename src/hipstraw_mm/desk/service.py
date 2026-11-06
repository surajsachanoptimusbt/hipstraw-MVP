"""The desk's operations: the CLI (`hipstraw-mm desk ...`) and the API call these and nothing else, so the authority
gate and the ledger apply to every action alike (constitution XIII).

- `submit`: a customer's market validation request becomes a case; the agent then works it (`run`).
- `decide`: a reviewer approves the agent's plan or returns it. The approval is bound to the plan's payload hash,
  so it cannot be applied to a plan that has changed since it was shown.
- Reads: the cases, their ledger events, the chain check, the playbook library and the offerings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hipstraw_mm.desk.agent import now, run_agent
from hipstraw_mm.desk.models import OFFERINGS, STAGES, Approval, Case, Event
from hipstraw_mm.desk.store import DeskStore
from hipstraw_mm.errors import PreconditionError, UsageError
from hipstraw_mm.foundry.demand import DemandRubric, check_case, load_demand_rubric
from hipstraw_mm.foundry.walkthrough import Thesis, case_for, load_thesis

DB_PATH = Path(".runs/desk.db")


class AuthorityError(PreconditionError):
    """The role may not take this action. Fails closed: an unknown or missing role is refused."""


class StaleError(PreconditionError):
    """The case is not in a state for this action, or the plan changed since it was shown."""


# --- a customer's request -----------------------------------------------------------------------------------------

class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriceFloorIn(_In):
    amount: float = Field(gt=0)
    currency: str = "USD"
    per: str = "month"


class HypothesisIn(_In):
    name: str = Field(min_length=2)
    demand: str = Field(min_length=5)
    segment: str = Field(min_length=3)
    profile: Literal["small_business", "mid_market", "enterprise"] = "small_business"
    offering: str = Field(min_length=2)
    description: str = ""
    recurring: bool = False
    priceFloor: PriceFloorIn | None = None
    triggers: list[str] = []
    buyerRole: str = ""
    motion: Literal["sales_led", "self_serve"] | None = None


class RequestIn(_In):
    """A market validation request as a customer fills it in: the thesis from market discovery and the demand
    hypotheses to validate."""
    product: str = Field(min_length=2)
    market: str = Field(min_length=2)
    geography: str = ""
    statement: str = Field(min_length=10)
    buyer: Literal["b2b", "b2c"] = "b2b"
    motion: Literal["sales_led", "self_serve"] = "sales_led"
    hypotheses: list[HypothesisIn] = Field(min_length=1, max_length=5)


def thesis_from_request(req: RequestIn, rubric: DemandRubric, when: date | None = None) -> Thesis:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{req.product} {req.market}".lower()).strip("-")[:48]
    thesis = Thesis.model_validate({
        "thesis": slug, "product": req.product, "statement": req.statement, "market": req.market,
        "geography": req.geography, "source": "Submitted in the customer workspace",
        "asOf": (when or date.today()).isoformat(), "buyer": req.buyer, "motion": req.motion,
        "hypotheses": [{
            "id": f"H{n}", "name": h.name, "demand": h.demand, "priority": n,
            "segment": {"name": h.segment, "profile": h.profile},
            "offering": {"name": h.offering, "description": h.description, "recurring": h.recurring,
                         **({"priceFloor": h.priceFloor.model_dump()} if h.priceFloor else {})},
            "triggers": [t.strip() for t in h.triggers if t.strip()], "buyerRole": h.buyerRole,
            **({"motion": h.motion} if h.motion else {}),
        } for n, h in enumerate(req.hypotheses, 1)],
    })
    errors = [f"{h.id}: {e}" for h in thesis.hypotheses for e in check_case(case_for(thesis, h, rubric), rubric)]
    if errors:
        raise UsageError("request: " + "; ".join(errors))
    return thesis


# --- the desk -----------------------------------------------------------------------------------------------------

@dataclass
class Desk:
    store: DeskStore
    config_dir: Path = Path("config")
    pace: float = 0.0  # seconds between the agent's steps, so a person can follow them
    rubric: DemandRubric = field(init=False)
    roles: dict[str, list[str]] = field(init=False)

    def __post_init__(self) -> None:
        self.rubric = load_demand_rubric(self.config_dir)
        with open(self.config_dir / "desk" / "roles.yaml", encoding="utf-8") as f:
            self.roles = yaml.safe_load(f)["roles"]

    def authorize(self, role: str, action: str) -> None:
        if action not in self.roles.get(role, []):
            raise AuthorityError(f"role {role or '(none)'!r} may not {action.replace('_', ' ')}")

    # -- changes -------------------------------------------------------------------------------------------------

    def submit(self, thesis: Thesis, *, actor: str, role: str) -> Case:
        """A request becomes a case, waiting on the agent. Call `run` to let the agent work it."""
        self.authorize(role, "submit_request")
        at = now()
        case = Case(id=self.store.next_case_id(), offering="shadow_launch", caseType="Market validation",
                    company=thesis.product, market=thesis.market, state="agent_working", waitingOn="agent",
                    stage="ingest", createdAt=at, updatedAt=at, requestedBy=actor,
                    thesis=thesis.model_dump(mode="json"))
        self.store.commit(case, [{
            "caseId": case.id, "at": at, "stage": "ingest", "actor": "customer" if role == "customer" else "reviewer",
            "who": actor, "kind": "request", "title": "Submitted a market validation request",
            "detail": f"{thesis.product}: {thesis.market}. {len(thesis.hypotheses)} demand hypotheses.",
            "data": {"role": role}}])
        return case

    def run(self, case_id: str) -> Case:
        return run_agent(self.store, case_id, self.rubric, self.pace)

    def decide(self, case_id: str, *, action: Literal["approve", "return"], payload_hash: str, actor: str,
               role: str, note: str = "") -> Case:
        self.authorize(role, "approve_plan" if action == "approve" else "return_plan")
        case = self.get(case_id)
        if case.state != "waiting_review" or case.payloadHash is None:
            raise StaleError(f"{case_id} is {case.state.replace('_', ' ')}, not waiting for review")
        if payload_hash != case.payloadHash:
            raise StaleError(f"{case_id}: the plan changed since it was shown; reload it before deciding")
        if action == "return" and not note.strip():
            raise UsageError("a returned plan needs a note saying why")
        at = now()
        approval = Approval(action=action, actor=actor, role=role, at=at, note=note, payloadHash=payload_hash)
        case = case.model_copy(update={
            "state": "approved" if action == "approve" else "returned",
            "waitingOn": "people" if action == "approve" else "customer", "updatedAt": at, "approval": approval})
        title = ("Approved the plan: the Moves may run, people carry out those that contact, publish or spend"
                 if action == "approve" else "Returned the plan to the customer")
        self.store.commit(case, [{"caseId": case.id, "at": at, "stage": "approval", "actor": "reviewer",
                                  "who": actor, "kind": "decision", "title": title, "detail": note,
                                  "data": {"action": action, "role": role, "payloadHash": payload_hash}}])
        return case

    def seed(self, theses_dir: Path) -> list[str]:
        """Open a case for each thesis file not yet at the desk, and let the agent work it at once."""
        known = {c.thesis.get("thesis") for c in self.store.cases()}
        opened = []
        for path in sorted(theses_dir.glob("*.yaml")):
            thesis = load_thesis(path, self.rubric)
            if thesis.thesis in known:
                continue
            case = self.submit(thesis, actor="Hipstraw (sample request)", role="reviewer")
            run_agent(self.store, case.id, self.rubric)
            opened.append(case.id)
        return opened

    # -- reads ---------------------------------------------------------------------------------------------------

    def get(self, case_id: str) -> Case:
        case = self.store.case(case_id)
        if case is None:
            raise UsageError(f"no case {case_id}")
        return case

    def summary(self, case: Case) -> dict[str, Any]:
        keys = [s[0] for s in STAGES]
        rec = case.recommendation or {}
        return {
            "id": case.id, "company": case.company, "market": case.market, "caseType": case.caseType,
            "offering": case.offering, "state": case.state, "waitingOn": case.waitingOn, "stage": case.stage,
            "stageIndex": keys.index(case.stage), "stages": len(keys), "createdAt": case.createdAt,
            "updatedAt": case.updatedAt, "requestedBy": case.requestedBy,
            "hypotheses": len(case.thesis.get("hypotheses", [])),
            "lines": [[t["lineId"] for t in h["tasks"]] for h in rec.get("hypotheses", [])],
        }

    def detail(self, case_id: str) -> dict[str, Any]:
        case = self.get(case_id)
        events = self.store.events(case_id)
        reached = {e.stage for e in events}
        keys = [s[0] for s in STAGES]
        current = keys.index(case.stage)
        stages = []
        for n, (key, name, what) in enumerate(STAGES):
            done = n < current or (key == "approval" and case.state in ("approved", "returned"))
            status = "done" if done else ("active" if n == current else "pending")
            stages.append({"key": key, "name": name, "what": what, "status": status,
                           "events": sum(e.stage == key for e in events), "reached": key in reached})
        return {"case": self.summary(case), "thesis": case.thesis, "recommendation": case.recommendation,
                "payloadHash": case.payloadHash, "approval": case.approval.model_dump() if case.approval else None,
                "stages": stages, "events": [e.model_dump() for e in events]}

    def events(self, case_id: str, after: int = 0) -> list[Event]:
        self.get(case_id)
        return self.store.events(case_id, after)

    def library(self) -> dict[str, Any]:
        r = self.rubric
        dims = {q: g.name for g in r.demandDimensions for q in g.questions}
        return {
            "repertoireVersion": r.repertoireVersion, "rubricVersion": r.version,
            "ranking": "Eligible Lines are ranked in playbook order; the first is picked. Jev is deferred.",
            "tasks": [{"id": t.id, "name": t.name, "question": t.question, "lines": [x.id for x in r.task_lines(t)]}
                      for t in r.tasks],
            "lines": [{"id": x.id, "name": x.name, "phase": x.phase, "purpose": x.purpose, "exit": x.exit,
                       "useWhen": {k: v for k, v in x.useWhen.items()}, "endsProgram": x.endsProgram,
                       "stages": x.stages} for x in r.lines],
            "moves": [{"id": m.id, "name": m.name, "effect": m.effect, "does": m.does, "how": m.how,
                       "records": m.records, "tests": sorted({dims[q] for q in r.tested_by(m.id) if q in dims}),
                       "watchOut": m.watchOut} for m in r.moves],
            "metrics": [{"id": i.id, "label": i.label, "dimension": dims.get(i.fills, ""),
                         "targets": {p: v[i.target] for p, v in r.profiles.items()}} for i in r.scorecard],
        }

    @staticmethod
    def offerings() -> list[dict[str, Any]]:
        return OFFERINGS

    def request_model(self, body: dict[str, Any]) -> Thesis:
        try:
            return thesis_from_request(RequestIn.model_validate(body), self.rubric)
        except ValidationError as exc:
            raise UsageError(f"request: {exc.error_count()} problem(s): "
                             + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())) from exc
