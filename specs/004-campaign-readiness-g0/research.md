# Research: Hipstraw G0 Campaign Strategy & Readiness Testing

Phase 0 decisions. Each one gives the decision, the rationale and the alternatives considered. There are
no open NEEDS CLARIFICATION items; product-owner questions that do not block this feature are listed in
the spec's Assumptions.

## R1. Storage: SQLite behind a CampaignStore protocol

- **Decision**: a `CampaignStore` protocol with one implementation on `sqlite3` (standard library).
  Production uses a file (default `.runs/campaign.db`, overridable with `HIPSTRAW_CAMPAIGN_DB`); tests
  use `:memory:` through the same code. Records are stored as JSON documents in per-entity tables with
  indexed key columns (IDs, launch ID, version, state, timestamps). Conditional commit and every
  multi-record write run in one transaction.
- **Rationale**: HA asks for one SQL database (section 7) with conditional commits against a pinned
  version (C3). SQLite gives real transactions, adds no dependency, and keeps the SQL a later server
  database can take over. Using `:memory:` for tests exercises the real SQL, so no separate in-memory
  class can drift from it.
- **Alternatives**: the Firestore market store (no cross-record transactions, wrong schema, would couple
  G0 to market discovery); PostgreSQL with SQLAlchemy (new dependencies and a server before the stack
  question is answered); a separate pure-Python in-memory store (a second implementation to keep in
  step).

## R2. Placement: a subpackage, not a new repository

- **Decision**: `src/hipstraw_mm/campaign/` with its own CLI group `hipstraw-mm campaign`.
- **Rationale**: Hipstraw is built separately from Zimplii. Inside this repository it reuses the
  adapters, task router, tracer, replay and test harness already proven by features 002 and 003.
  Library-first is met by keeping the subpackage self-contained.
- **Alternatives**: a new repository (would copy the adapters and the router, and the stack question is
  still open); folding into `market/` (mixes two products and breaks layer boundaries).

## R3. Reusing the task router and tracer

- **Decision**: reuse `market.trace.Tracer` and `market.router.TaskRouter` as they are. The campaign
  store exposes a trace sink with the five methods the tracer calls (`get_market_run`,
  `upsert_market_run`, `create_trace_step`, `finish_trace_step`, `create_trace_blob`), backed by
  campaign trace tables. The tracer receives the campaign layer config. `model_call` and `TaskRouter`
  take a `ModelContext` protocol (attributes `llm` and `open_llm`) instead of the full `Context`; the
  market `Context` already satisfies it.
- **Rationale**: model calls stay routed, validated, replayable and traced in exactly one way (XII). The
  only shared-code edit is to type hints.
- **Alternatives**: a second tracer (two trace formats to maintain); calling `LLMClient` directly (loses
  routing, escalation and the trace shape the viewer reads).

## R4. Line conditions: typed facts, no expression language

- **Decision**: use-when and exclude-when are lists of `{fact, op, value}` checks, combined with `all`
  (default) or `any`. Facts are computed by code from the Position and mandate: `daysToDayZero`,
  `isLive`, `hasMetrics`, `openBlockers`, `openReadinessBlockers`, `unverifiedCoreAssumptions`,
  `contestedClaims`, `unknowns`, `authorizedTestChannel`, `testPlanBudgetSet`. Operators: `<`, `<=`,
  `>`, `>=`, `==`, `!=`. Every check produces a plain-language reason.
- **Rationale**: FR-021 requires typed, deterministic conditions, and the compiler spec requires branch
  predicates to be typed expressions over states. No `eval`, so config cannot run code.
- **Alternatives**: a small expression language (parser to build and secure); a model judging fit
  (forbidden: selection is never a model decision).

## R5. Stages: one group per stage, run in order

- **Decision**: the runner executes a stage's Moves one after another in-process, all reading the same
  stage-start snapshot of state; their outputs merge only after every Move in the stage has finished.
  The next stage starts after that.
- **Rationale**: this has the same meaning as "Moves in a stage run in parallel" without threads; G0
  volume does not need concurrency, and durable jobs belong to G2.
- **Alternatives**: threads or a job queue (complexity with no G0 benefit).

## R6. Human steps between stages: separate commands

- **Decision**: a Line run advances one stage per `campaign step` command, or all remaining stages with
  `campaign run`. Deviations are separate commands (`deviate --skip`, `deviate --add`, `stop`) that apply
  to the next stage. Every deviation needs `--by` and `--reason`.
- **Rationale**: the CLI is non-interactive (II); this lets a person pause at any stage boundary, which
  is HA's judgment point.
- **Alternatives**: interactive prompts (not scriptable, not testable).

## R7. Roles and authority

- **Decision**: actions take `--by <name> --as <role>`. `config/campaign/roles.yaml` lists which actions
  each role may take (Sponsor: accept or reject a Review, amend the mandate; Campaign Manager: choose a
  Line, deviate, run; reviewer: correct, reject or accept a finding, validate a Review). The authority
  gate (C7) checks role rights and, for each Move, its effect class: E0 always allowed, E1 only for
  sources the mandate names, E2 only for declared Moves with a versioned prompt, E3 never in this
  feature. The gate fails closed and writes a trace step with its decision.
- **Rationale**: HA separates the roles (section 9). G0 is used internally from the command line, so
  real authentication is out of scope, but every action is still attributed and audited.
- **Alternatives**: no role checks (loses the audit's "right used"); full authentication (out of
  scope).

## R8. E2 Moves through the router

- **Decision**: M02 (summary part), M06 and M07 call `TaskRouter.call` with tasks
  `campaign_source_summary.v1`, `campaign_synthesis.v1` and `campaign_variants.v1`. They stay out of the
  shared `config/routing.yaml` and the shared prompt registry, so router rule R1 sends them to frontier and
  the market Routing tab is unchanged. The calls run at temperature 0 so a review gives the same verdict on the same evidence.
  M02's summary step is deferred (spec Session 2026-10-29). Each call passes a
  validator: every cited evidence ID exists in the launch, and no output declares a claim state above
  `reported`. Prompts are versioned files in `src/hipstraw_mm/prompts/`.
- **Rationale**: one model path for the whole project; open-weight routing for these tasks is a later,
  measured decision (it changes routing behaviour, which needs sign-off).
- **Alternatives**: adding them as `simple` tasks now (behaviour change without evidence).

## R9. Review assembly is deterministic

- **Decision**: when a Line ends, code assembles the Review from the Move outputs. Findings come from
  blockers (M04, M05), metric checks (M03), contested or missing evidence (M02, M08), proposals (M06,
  M07), Test Plans (M09) and Deltas (M11). Each finding is typed `strategy` or `readiness`, carries
  evidence references and an uncertainty note, and is marked as a proposal when a model produced it. The
  proposed successor Position applies the transitions the Moves recorded to the base Position.
- **Rationale**: the Review is the interface to the Position (VI) and must be reproducible; the model
  work is already done inside the E2 Moves.
- **Alternatives**: a final model call to write the Review (an extra, unbounded judgment step at the
  point where honesty matters most).

## R10. Readiness criteria v1 (proposal for the domain owner)

- **Decision**: `config/campaign/criteria.yaml` version `readiness-criteria.v0.1`. M04 criteria:
  landing page address given; objective and success measure stated; audience stated; budget stated;
  approver (Sponsor) named; at least one authorized channel; for each authorized channel, the asset that
  channel needs (email copy for email, ad copy for paid social or search, creative description for
  display); tracking plan stated. M05 rules: Day Zero set and in the future, or the launch is live;
  each required asset has a ready date on or before Day Zero minus the configured lead time (default 3
  days); approver named at least the lead time before Day Zero.
- **Rationale**: FR-031 and FR-032 need a deterministic, versioned list. The list is a starting proposal
  marked for review, like `config/playbook/picker.yaml`.
- **Alternatives**: hard-coded checks (not reviewable by the domain owner).

## R11. No score fields, enforced by a test

- **Decision**: an architecture test walks every campaign pydantic model and structured-output schema and
  fails on any field named like `score`, `probability`, `forecast`, `likelihood` or `successRate`.
- **Rationale**: FR-003 and HA section 12 ("the Position and report schemas contain no
  success-probability or forecast fields").
- **Alternatives**: review discipline only.

## R12. Identifiers and versions

- **Decision**: launch `lch_<UTC timestamp>`; mandate versions `1, 2, ...` per launch; evidence
  `ev_<launch>_<n>`; Position snapshots `pos_<launch>_v<n>`; Line runs `lrun_<launch>_<n>`; Reviews
  `rev_<launch>_<n>`; findings `F01, F02, ...` within a Review. Move and Line IDs (M01, L01) are stable
  across versions; definitions carry a `version` field; the repertoire file carries
  `campaign-repertoire.v0.1`.
- **Rationale**: readable in the CLI, stable for G3 joins (compiler spec continuity rule 5).
- **Alternatives**: random UUIDs (hard to read in a review queue).

## R13. Mechanism stamp contents

- **Decision**: every Review run and Position snapshot stores `{codeVersion, gitCommit (if available),
  repertoireVersion, criteriaVersion, promptVersions[], models[] (configured and served), router
  version}`.
- **Rationale**: C8; lets later changes to prompts, models or the repertoire be told apart in history.
- **Alternatives**: stamp only the model (loses repertoire and criteria changes).
