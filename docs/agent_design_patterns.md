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

## Agents

| Agent | Central question | Innate capabilities | Skills | Tools |
|---|---|---|---|---|
| Market Manager | Where to direct attention and resources? | Run lifecycle; **Market Review** (only writer of the canonical Market Position, versioned); governance and ledger | Path decision (rule `decide.v1`); Market status (rule); Company Review (rule `review.v1`) | Market Position store; decision ledger |
| Market Development Controller | Where should we play? | Graph semantic governance; synthesis of the market map | none yet | Graph and frontier service |
| Search & Research | What to investigate next, and is evidence sufficient? | Frontier management (beam width, diversity, 75% search-score threshold); worker orchestration (one company-research child run per final path) | Vichara, grounding repair, coverage, hypothesis proposal, seed-graph construction, link verification, frontier scoring, company discovery (all model skills, versioned prompts) | Brave search; page fetcher; evidence store |
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
   new **version**, with trajectory against the earlier version and lineage to the evaluation case. If
   its rule disagrees with the recommendation, the review note says so.
6. The **Market Development Controller** builds the **market map**: one tile per micro market, sized by
   value pool and coloured by position, or by change against the program's previous run.

## Known gaps

- Research requirements are issued and shown, but are not yet sent back to Search & Research
  automatically for another research pass.
- No challenger or independent evaluation worker yet; high-consequence recommendations are flagged
  for Market Manager Review instead.
- Exploration & Learning sub-controller is not built (optional in the architecture).
- Persistence between sessions requires the Firestore emulator; `--memory` keeps one run per process.
