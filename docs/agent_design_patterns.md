# Hipstraw MVP: agent design patterns

How each agent in the market pipeline is built: its innate capabilities, its skills, and its tools.
The machine-readable source is `config/agents.yaml`. Each run snapshots it, and the viewer's **Agents**
tab shows it with real usage counted from that run's trace. A test fails if any traced operation is
not claimed by a capability or a skill.

## Terms

- **Innate capability**: what the agent class does natively, without a model. Examples are its state
  machine, rights checks, queues, versioning, and lineage. These are code, not prompts.
- **Skill**: reusable, versioned competence. Either a **model skill** (a versioned prompt plus a strict
  output schema, traced with its prompt and response) or a **rule skill** (a versioned deterministic
  rule table, so the decision can be reproduced).
- **Tool**: a mechanism the agent calls: the store, Brave search, the page fetcher, the model gateway.
- **Right**: what an actor may do, enforced by the tracer from `config/layers.yaml` before a step runs.

## How the Agents screen shows this

By default the screen is written for a business reader. Each agent shows what it does, in
market-manager language, with every item marked **By rule**, **Uses AI**, **Rules, then AI**, or
**Built in**. It also shows what the agent knows (the Market Manager knows the playbook) and what it uses. A glossary
maps each system term to its Market Mastery Playbook term (for example path → market unit, market
run → Market Review, trace → Activity), and the viewer's labels use the playbook terms. Versions,
step counts, and cost are under **Technical details**. The wording comes from the `title`, `role`,
`plain`, `knowledge`, and `glossary` fields in `config/agents.yaml`. A skill that calls the model
can never be labelled a rule; a test checks this.

Where a capability or skill already performs an item from the Market Mastery Playbook, the
`playbook` field names it (for example "M09 Archetype Segmentation" or "A10 Create comparable
territory economics") and the screen shows it under the item. Links are added only where the match is
real; market status, company review and link verification have none yet. The playbook itself is
structured data in `config/playbook/` (extracted by `scripts/extract_playbook.py`, checked on load by
`hipstraw_mm.market.playbook`), and these links tell the quick picker which line steps a run has done.

## The Market Review follows the playbook grammar

For each market unit the Market Manager runs the playbook's §6 quick picker, by rules only
(`hipstraw_mm.market.review`, no model call):

1. **Position**: the seven axes MP1–MP7, set from desk research using the playbook's own states.
2. **Binding constraint**: the weakest axis, by the order in `config/playbook/picker.yaml`.
3. **Stance**: the §7.1 default for the binding state; any stance marked × on any axis is ruled out.
4. **Strategy → Play**: §2.2 "usually calls for", which must allow the stance (§7.2), then the
   strategy's plays (§7.3) that are priority plays for the program's `marketTypes` (§7.7).
5. **Line → steps**: the play's preferred lines (§7.4). A step is *done* when a capability linked to it
   ran in this run, *ruled out* when the stance forbids it, and otherwise *to do*.
6. **Recommended next step**: the first step still to do, with who can run it and whether Advisory
   mode allows it (action tiers 1–2).
7. **Gambits** are listed as options only, never authorized.
8. **Disposition** (EXPLORE, TEST, ACTIVATE, BUILD, SCALE, REFRAME, PARK, STOP) and attention tier,
   from `picker.yaml`. Disposition replaces the old Pursue / Needs more evidence / Drop decision.

Rules the playbook leaves open (binding-constraint order, disposition mapping) are marked
"Hipstraw proposal" in `picker.yaml` and listed in `docs/playbook_gaps.md`.

## Task router (router.v1)

Model tasks can be routed to rules, an open-weight model, or a frontier model. The choice is never a
model call: `hipstraw_mm.market.router.decide_route` applies ordered rules (R1–R8) to the task's class
in `config/routing.yaml` (rules, simple, complex) and to facts about the call (is the open-weight route
on, is an endpoint configured, input size, open-weight call failures in a row in this stage; a
rejected answer escalates on its own and does not count). A simple task
goes to open-weight first; if a blocking validator fails, or the call errors, the same messages go once
to frontier under the usual match key. Frontier results are validated too, but only recorded, since
frontier is the last tier. Each attempt is a normal `call_model` worker step with its route and model;
the route, rule and escalation are in the business step's checks and `outputs.routing`, and each
deliberation stores `deliberatedBy`.

Only the vichara stage is wired so far (`vichara.v1` simple; coverage and propose complex). The
open-weight route is off in `routing.yaml` and needs `OPEN_WEIGHT_BASE_URL` and `OPEN_WEIGHT_MODEL`
(any OpenAI-compatible endpoint), so runs go to frontier exactly as before until both are turned on.

`hipstraw-mm market --memory simulate --program <id> [--objective-pdf PATH] --serve` runs the vichara
stage with the open-weight route on for that run only and opens the viewer's **Routing** tab: the routing
diagram replayed task by task from the trace (router rule, open-weight answer, validator lamps,
escalation, frontier answer, saved lineage), kept/escalated counts, cost against an all-frontier
estimate, and a task table linking each model call to Activity. The run is marked as a simulation.

## Agents

| Agent | Central question | Innate capabilities | Skills | Tools |
|---|---|---|---|---|
| Market Manager | Where to direct attention and resources? | Run lifecycle; **Market Review** (only writer of the canonical Market Position, versioned); governance and ledger | **Quick picker** (rule, `playbook.v0.1` + `picker.v1`); Market status (rule, over dispositions); Company Review (rules, then a model judgement, `review.v1`) | Market Position store; decision ledger |
| Market Development Controller | Where should we play? | Graph semantic governance; synthesis of the market map | none yet | Graph and frontier service |
| Search & Research | What to investigate next, and is evidence sufficient? | Graph validation; worker orchestration (one company-research child run per final path) | Vichara, grounding repair, coverage, hypothesis proposal, seed-graph construction, link verification, frontier scoring, company discovery (model skills, versioned prompts); shortlisting (rule `beam.v1`: beam width, diversity, 75% search-score threshold) | Brave search; page fetcher; evidence store |
| Position & Evaluation | What to conclude, how confident, what is unknown, what next? | Evaluation case lifecycle (RECEIVED → QUEUED → EVALUATING → NEEDS_RESEARCH / DECIDING → READY); comparison set management | Path assessment (model); evidence states (rule); **economic evaluation** (model `economic_assessment.v1`); buyer roles (model); **confidence** (rule `confidence.v1`); **position transition rubric** (rule `position_transition.v1`) | Evidence store; Market Position read (read only); rubric service |
| Workers | Do one bounded task | Bounded execution: one model call, search, or fetch per step | none | Model gateway; Brave search |

## The Position & Evaluation pattern (P&E spec v0.4)

1. Search & Research hands over each final path with its Research Evidence Packet.
2. P&E sizes every micro market the beam reached with a **value-pool range, assumptions, and
   sensitivities**. The estimate is always labelled a hypothesis.
3. P&E opens an **Evaluation Case** per final path. Confidence comes from evidence quality, coverage,
   contradictions, open proofs, and economic fragility; it is never a model self-rating. The transition
   rubric recommends Recommend Transition / Strengthen / Maintain / Validate / Investigate Further /
   Weaken / Recommend Retirement. Every material gap becomes a **Research / Validation Requirement**.
4. P&E compares candidates on a common basis, keeping trade-offs and near ties instead of forcing a
   winner.
5. The **Market Manager** reviews each recommendation and commits the canonical Market Position as a
   new **version**, with trajectory against the earlier version and lineage to the evaluation case. Each
   P&E recommendation supports a disposition (for example Recommend Transition → TEST); if the quick
   picker chooses a different disposition, the review note says so.
6. The **Market Development Controller** builds the **market map**: one tile per micro market, sized by
   value pool and coloured by disposition group (ACTIVATE/BUILD/SCALE · EXPLORE/TEST · REFRAME/PARK ·
   STOP), or by change against the program's previous run.

## Known gaps

- Research requirements are issued and shown, but are not yet sent back to Search & Research
  automatically for another research pass.
- No challenger or independent evaluation worker yet; high-consequence recommendations are flagged
  for Market Manager Review instead.
- Exploration & Learning sub-controller is not built (optional in the architecture).
- Persistence between sessions needs Firestore (emulator, or cloud with `HIPSTRAW_FIRESTORE=cloud`);
  `--memory` keeps one run per process.
- Every axis except MP1 is set from desk research at its starting state; later evidence (contact,
  pilots, deals) does not yet move the axes.
