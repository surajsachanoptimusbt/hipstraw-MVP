# Feature Specification: Traced Market Discovery Pipeline

**Feature Branch**: `003-traced-market-discovery`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "Traced market discovery pipeline. Objective -> vichara self-Q&A -> seed
graph -> validated and verified paths -> beam search -> real companies and buyer roles, with a
read-only trace viewer." (Full description, with references, layer responsibilities, user stories
P1–P4, trace requirements, and exclusions, as supplied on 2026-10-08.)

## References

- **Program**: Kozmo Invoice Alpha Genesis Cohort (https://kozmo.ai/invoice-alpha-genesis.html), as
  loaded by feature 002 (`config/programs/invoice_alpha.yaml`). Constraints unchanged: startups, small
  and mid-market companies only (no Fortune 500 companies or other large enterprises); headquarters in
  the Atlanta, San Francisco, or New York metro area, each drawn as its US Census combined statistical
  area.
- **The 19 Market Manager dimensions**: the HipStraw grammar, `hipstraw-faculty/seed_data/grammar.json`
  (each dimension has a key, a question, its states, the layer that assesses it, and the Market
  Manager as the decider). It is not yet copied into this project.
- **Feature 001 (seed graph)**: `HipStraw-Market-Discovery Agent/specs/001-seed-graph-generation/spec.md`
  in the sibling project. The requested path `docs/reference/001-seed-graph-spec.md` does not exist in
  this project. Decisions reused: self-posed questions and answers are kept as part of the record;
  a dimension with zero information is marked unresolved rather than forced; bounded repair touches
  only the gap and counts a repair that breaks structure as a failed attempt; every link gets its own
  rationale and confidence; a search score is kept apart from confidence.
- **Feature 002 (this project)**: discovery verification, evidence checks, Review, and the report are
  reused. This feature replaces 002's flat ranking of listing candidates with a beam search over the
  seed graph.
- **Constitution v1.2.0**: VI (Faculty Systems), VII (no agent SDK), VIII (evidence provenance), IX
  (real-world data integrity), XII (traceability), XIII (read-only viewer), XIV (layer boundaries),
  XV (bounded search).

## Clarifications

### Session 2026-10-08

- Q: Is "vichara" here the Jev technology that Constitution XI defers? → A: No. It is the bounded
  self-questioning of feature 001: the system asks itself questions per dimension and answers them
  from the objective only. Jev stays out of scope.
- Q: Should one run cover the whole program (all six experiment contexts feeding one seed graph) or
  one experiment context per run, as in feature 002? → A: Whole program per run. One vichara and one
  seed graph per run, with all six experiment contexts as input; the beam search chooses which paths
  matter. (FR-001)
- Q: At the end of a run, should the Market Manager record a state for Trajectory, Transition, and
  Market Status, or leave them unassessed? → A: Record Market Status only. Trajectory and Transition
  compare states across runs, so they stay unassessed until a later feature; vichara still asks about
  them. (FR-007, FR-022)
- Q: Should path verification follow a bounded approach (links verified up front; constraints checked
  and assessments made only for the paths the beam search reaches; paths never listed in full)? → A:
  Yes. Listing every full path is exhaustive traversal (Constitution XV). Links are verified up front
  (their number is bounded by the graph's caps), constraints are checked on every path the beam
  reaches, and the seven per-path assessments run only on paths that finish the beam. Paths the beam
  never reaches are counted, not stored one by one. (FR-012, FR-013)
- Q: If structural violations remain after the 3 repair attempts, should the run stop as failed or
  continue with a flagged graph? → A: Stop as failed. The run is marked failed at the validation
  stage with the remaining violations in its error message; every repaired graph version stays stored
  and visible in the viewer; the run cannot be resumed. Coverage gaps that remain are different: they
  are recorded as unresolved and the run continues. (FR-011)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Vichara and seed graph, fully traced and visible (Priority: P1)

As Search & Research, given the program objective and its constraints, I want to question myself
across all 19 Market Manager dimensions, record the graph's meaning as defined by the Market
Development Controller, and build a seed graph from my answers, with every question, answer, check,
and generation step stored as a trace, so that the hypothesis space is explicit and a reviewer can see
exactly how it was produced.

**Why this priority**: Every later step works on the seed graph. Without traced generation there is
nothing to validate, verify, or search, and nothing a reviewer can audit.

**Independent Test**: Run the vichara and generation steps on the program objective using recorded
model responses. Check that each of the 19 dimensions has at least one answered question or an
unresolved marker, that the graph-meaning record exists before generation, that the graph has the six
levels, and that a trace exists for every question, answer, check, and generation step.

**Acceptance Scenarios**:

1. **Given** the program objective and constraints, **When** vichara runs, **Then** each of the 19
   dimensions has at least one self-posed question with an answer drawn only from the objective, or an
   explicit unresolved marker stating that the objective gives no information for it.
2. **Given** the vichara answers, **When** the coverage check runs, **Then** a deterministic check
   confirms every dimension is answered or marked unresolved, and a model judgement confirms each answer
   addresses its own dimension; a failing dimension triggers repair, at most 3 attempts, and a gap still
   open after the last attempt is recorded as unresolved, never dropped.
3. **Given** a run, **When** the Market Development Controller step runs before generation, **Then**
   it records the graph's meaning: the six levels and their order, the allowed relationships between
   levels, the mandatory filters, and what counts as a promising path.
4. **Given** the vichara answers and the graph meaning, **When** generation runs, **Then** the graph
   has nodes at the six levels: segment (Market Scope), company archetype (Segment / Micro-market Fit),
   problem (Problem), trigger (Market Timing), buyer role (Buyer), and use case (Use Case / Entry
   Wedge), connected only by the allowed relationships, and no node falls outside the mandatory
   filters.
5. **Given** a completed vichara and generation, **When** the trace viewer is opened, **Then** every
   question, answer, coverage check, repair attempt, and generation step appears as its own traced step.

---

### User Story 2 - Graph validation (Priority: P1)

As Search & Research, I want each generated graph checked deterministically for structure and by
judgement for coverage of the vichara answers, with bounded repair of gaps, so that only a sound graph
reaches path verification and every remaining gap is visible.

**Why this priority**: A broken or partial graph makes every later step unreliable. It shares top
priority with generation because the two together are the first demonstrable unit.

**Independent Test**: Validate graphs with a known orphan node, a known dangling edge, a known
level-order violation, a known out-of-filter node, and a known coverage gap, using recorded model
responses. Check each is caught with its reason, that repair is attempted at most 3 times, and that an
unclosed gap is recorded as unresolved.

**Acceptance Scenarios**:

1. **Given** a graph with an orphan node, a dangling edge, a node at the wrong level, an edge skipping
   or reversing the level order, or a node outside a mandatory filter, **When** structural validation
   runs, **Then** each violation is reported with the node or edge and the rule it breaks, and the same
   unmodified graph always gets the same verdict.
2. **Given** a structurally valid graph, **When** coverage validation runs, **Then** a model judgement
   reports which vichara answers the graph does not cover, if any.
3. **Given** a coverage gap or a structural violation, **When** repair runs, **Then** it changes only
   the region of the gap, at most 3 attempts are made, a repair that introduces a new structural
   violation counts as a failed attempt, and a gap still open after the last attempt is recorded as
   unresolved.
4. **Given** any validation or repair step, **When** the trace viewer is opened, **Then** both the
   deterministic result and the model judgement appear with their pass or fail outcome and reason.

---

### User Story 3 - Path verification (Priority: P2)

As Search & Research, I want every link in the graph given a reasoned rationale and confidence, and every
path the search reaches checked against the objective's constraints and assessed, without ever listing
all paths, so that paths that cannot fit are pruned with a reason and weak paths are flagged before any
search spends effort on them.

**Why this priority**: It turns the graph into a set of candidate positions that can be searched. It
depends on a validated graph but is demonstrable on its own against any validated graph.

**Independent Test**: Verify a validated graph containing one path that breaks a constraint (for
example, an enterprise-only archetype) and one path with a weak link, using recorded model responses.
Check every link has a rationale and a link confidence and the weak link is flagged, the first path is
pruned with its reason when the search reaches it, and no step builds the full list of paths.

**Acceptance Scenarios**:

1. **Given** a path the beam search reaches, **When** its deterministic constraint check runs, **Then**
   a path outside the objective's constraints is pruned and records which constraint it breaks and the
   node that breaks it.
2. **Given** a validated graph, **When** link verification runs, **Then** every link has a rationale
   answering "why is this node connected to that one" and a link confidence from 0 to 1, and a link below
   the low-confidence threshold is flagged, so any path through it is flagged.
3. **Given** the paths that finish the beam search, **When** path assessment runs, **Then** each records
   a reasoned assessment, drawn from the objective only and labeled as hypothesis, for Value
   Proposition, Demand, Adoption Readiness, Economics, Alternatives, Risks, and Dependencies.
4. **Given** a path for which the beam search later finds no verified company, **When** the run ends,
   **Then** the path is marked "no real-world evidence found"; a path is never marked as existing in
   the real world before a verified company is found for it.

---

### User Story 4 - Beam search to real companies and buyer roles (Priority: P3)

As Search & Research, I want a bounded, level-by-level beam search over the verified paths that keeps
only the most promising and diverse ones, then sends the final paths to company discovery and
verification, so that real companies and their buyer roles are found for the paths most worth
pursuing, with every pruned or deferred path keeping its reason.

**Why this priority**: This is where the hypothesis meets the real world. It depends on verified paths
and reuses feature 002's verification and Review.

**Independent Test**: Run the beam search on a verified graph with more candidate paths than the beam
width, using recorded responses. Check that at each level the steps run in order (filter, score,
diversity, keep top N), that per-factor scores are stored apart from evidence confidence, that no two
kept paths share both segment and problem, that the final 3 paths each get company discovery with at
most 5 companies, and that each kept company has its buyer roles identified without any named person.

**Acceptance Scenarios**:

1. **Given** verified paths, **When** the beam search processes a level, **Then** it filters by the
   mandatory constraints, scores each partial path, applies the diversity check, and keeps the top 5
   (configurable), recording for every path whether it was kept, pruned, or deferred, and why.
2. **Given** a scored path, **When** its score is stored, **Then** each factor (objective fit,
   information value, evidence gap, cost) is stored separately with the weights used (equal by
   default), and the score is never stored or shown as evidence confidence.
3. **Given** two candidate paths sharing both segment and problem, **When** the diversity check runs,
   **Then** at most one of them is kept and the other records "diversity: same segment and problem as
   <kept path>".
4. **Given** the final level, **When** the beam search ends, **Then** the top 3 paths (configurable)
   each go to company discovery and verification using feature 002's rules, with at most 5 companies
   per path, and every other remaining path is deferred with its reason.
5. **Given** a kept company on a final path, **When** buyer-role identification runs, **Then** it
   records the buyer functions, their authority over the problem, and cited evidence of that ownership,
   as roles only, never named people.
6. **Given** a final path and its companies, **When** Review runs, **Then** each company gets exactly
   one disposition under feature 002's rules, and a path with at least one included company is marked
   as having real-world evidence.

---

### User Story 5 - Trace viewer (Priority: P4)

As a HipStraw team member, I want a read-only viewer over the stored state and traces, updated while a
run is in progress, so that I can follow and audit every step, decision, and score without operating
the pipeline and without any risk of changing data.

**Why this priority**: It makes stories 1–4 visible and demoable to people who do not operate the
system. It reads only stored records, so it adds no pipeline behavior.

**Independent Test**: Open the viewer on stored runs (from recorded scenarios), check every listed view
shows the stored values, start a recorded run and check new steps appear without reloading, and confirm
the viewer offers no way to create, change, or delete anything.

**Acceptance Scenarios**:

1. **Given** stored runs, **When** the viewer opens, **Then** it lists the runs, and for a chosen run
   shows its timeline grouped by layer in this order: Market Manager, Market Development Controller,
   Search & Research, Position & Evaluation, Workers.
2. **Given** a step, **When** it is opened in the viewer, **Then** the viewer shows its inputs, outputs,
   decision and right used, rationale, alternatives, checks with pass or fail and reason, model and
   prompt version, prompt and structured response, tool calls (searches and pages fetched), cost, and
   latency.
3. **Given** a run, **When** its graph view is opened, **Then** the viewer shows the seed graph with
   its validation results and the status of every path (pruned, flagged, kept, deferred, final, no
   real-world evidence found).
4. **Given** a run, **When** its beam view is opened, **Then** the viewer shows, per level, the kept and
   pruned paths, why, and each path's per-factor scores, with search scores and evidence confidence
   always labeled and shown as separate values.
5. **Given** a run, **When** its companies view is opened, **Then** the viewer shows each company with
   its evidence, buyer roles, and Review decision.
6. **Given** a run in progress, **When** the pipeline stores a new step, **Then** it appears in the
   viewer within 5 seconds without reloading.
7. **Given** the viewer, **When** any of its views is used, **Then** it offers no action that writes,
   edits, or deletes data, or starts or stops a pipeline step.

---

### Edge Cases

- **The objective says nothing about a dimension**: the dimension is marked unresolved with reason
  "no information in the objective"; nothing is invented for it (feature 001).
- **The objective says little about a dimension**: an answer is still given and the weakness shows in
  the link confidence of what it produces; unresolved is reserved for zero information (feature 001).
- **Repair breaks the graph's structure**: that attempt counts against the 3 repair attempts.
- **Structural violations remain after the last repair attempt**: the run fails at the validation stage
  with the violations listed; the graph versions stay visible (FR-011).
- **Every path breaks a constraint**: the beam search has nothing to keep; the run records that no
  path survived verification and why, and no company search runs.
- **Fewer paths than the beam width at a level**: all surviving paths are kept; nothing is padded.
- **Fewer than 3 paths reach the final level**: only those go to company discovery; the shortfall is
  recorded.
- **A final path finds no verified company**: it is marked "no real-world evidence found"; it is not
  dropped from the record.
- **The same company is found for two final paths**: it is one company record in the run, linked to
  both paths; it counts toward each path's limit of 5.
- **A trace field would contain a secret** (for example, an API key in a request): the secret is
  removed before the trace is stored.
- **The viewer is open while no run exists**: it shows an empty list and nothing else.

## Requirements *(mandatory)*

### Functional Requirements

**Input, layers, and scope**

- **FR-001**: A run MUST cover the whole program: it takes as input the program objective, all six of
  the program's experiment contexts, and its constraints (size limits, the three metro areas, and the
  exclusion of Fortune 500 companies and other large enterprises), as loaded for feature 002, and
  produces one vichara and one seed graph. The experiment contexts inform the vichara answers and the
  graph; they are not separate runs, and no path is limited to one context.
- **FR-002**: Each step MUST belong to exactly one layer and act only within that layer's
  responsibility (Constitution XIV):
  - **Market Manager**: decides. It records the decision for each final path and owns the Review
    dispositions, and it MUST NOT read or traverse the seed graph; it sees only the final paths and
    their evaluations handed to it.
  - **Market Development Controller**: defines the graph's meaning (levels, relationships, mandatory
    filters, what counts as a promising path) before generation.
  - **Search & Research**: runs vichara, builds and validates the graph, verifies paths, runs the beam
    search, and gathers evidence.
  - **Position & Evaluation**: assesses the final paths and their companies on the dimensions the
    grammar assigns to it.
  - **Workers**: perform bounded tasks (one model call, one search, one fetch) with explicit inputs and
    structured outputs.
- **FR-003**: Company discovery, evidence checks, Review, and the report MUST follow feature 002's rules
  unchanged (its FR-002 and FR-005 to FR-018), except that candidates come from the beam search's final
  paths instead of feature 002's flat ranking, and the per-run limit is at most 5 companies for each
  final path.

**Vichara and the graph meaning (story 1)**

- **FR-004**: Search & Research MUST pose at least one question to itself for each of the 19 dimensions
  in the grammar and answer it using only the objective and constraints. When the objective gives no
  information for a dimension, it MUST record an unresolved marker with that reason instead of an
  answer. Every question, answer, and marker MUST be kept as a stored record linked to its dimension,
  never discarded after the graph is built.
- **FR-005**: The coverage check MUST be deterministic for presence (every one of the 19 dimensions has
  at least one answer or an unresolved marker) and a model judgement for relevance (each answer
  addresses its own dimension). A failing dimension MUST trigger repair of that dimension only, at most
  3 attempts; a dimension still failing after the last attempt MUST be recorded as unresolved with
  reason "repair exhausted", never dropped.
- **FR-006**: Before generation, a Market Development Controller step MUST record the graph's meaning
  for the run: the six levels in order (segment, company archetype, problem, trigger, buyer role, use
  case) with the dimension each represents (Market Scope, Segment / Micro-market Fit, Problem, Market
  Timing, Buyer, Use Case / Entry Wedge), the allowed relationships (each level links only to the next),
  the mandatory filters (the program's size, location, and large-enterprise exclusions), and what
  counts as a promising path. Generation, validation, and the beam search MUST use this record and no
  other definition.
- **FR-007**: The dimensions Value Proposition, Demand, Adoption Readiness, Economics, Alternatives,
  Risks, and Dependencies MUST be assessed per path (FR-013), not as graph levels. Evidence
  Sufficiency, Evidence Quality & Confidence, and Critical Unknowns MUST be recorded as results of
  verification (FR-020). Trajectory, Transition, and Market Status MUST NOT appear in the graph; they
  belong to the Market Manager. Of these, only Market Status is recorded by this feature (FR-022a);
  Trajectory and Transition compare states across runs and are recorded as unassessed, with the reason
  "needs a comparison with an earlier run", until a later feature defines them.

**Seed graph and validation (stories 1 and 2)**

- **FR-008**: Generation MUST build nodes only at the six levels and edges only between adjacent levels
  in order, derived only from the vichara answers and the objective, with no external search. A node
  MAY have more than one parent when it is the same concept (feature 001). A node that would match a
  mandatory filter (for example, an enterprise archetype) MUST NOT be created; if that leaves a level
  with no node, the run MUST record it as unresolved with reason "excluded by filter".
- **FR-009**: Structural validation MUST be deterministic and MUST report every orphan node, dangling
  edge, node at an undefined level, edge that skips or reverses the level order, schema violation, and
  node outside a mandatory filter, each with the node or edge and the rule broken. The same unmodified
  graph MUST always get the same verdict.
- **FR-010**: Coverage validation MUST be a model judgement of whether the graph covers each answered
  vichara question, reporting each uncovered answer as a gap. It is advisory input to Search &
  Research, not a sufficiency verdict (feature 001).
- **FR-011**: Each structural violation or coverage gap MUST trigger repair of only that region, at most
  3 attempts per run of validation; structural and coverage validation MUST run again after each
  attempt; an attempt that introduces a new structural violation counts as a failed attempt; and a gap
  still open after the last attempt MUST be recorded as unresolved with reason "repair exhausted". If
  structural violations remain after the last attempt, the run MUST be marked failed at the validation
  stage with each remaining violation (node or edge, and rule) in its error message, and MUST NOT go on
  to path verification; every graph version written by the repairs MUST stay stored and visible.

**Path verification (story 3)**

- **FR-012**: No step MUST list or verify every full path of the graph (Constitution XV). Deterministic
  path verification MUST check every path the beam search reaches (each extension) against the
  objective's constraints and prune any that breaks one, recording the constraint and the node that
  breaks it. For each pruned or deferred partial path the run MUST record how many complete paths lie
  below it, counted without listing them, so what was never examined stays visible.
- **FR-013**: A model step MUST give every link of the graph a rationale ("why is this node connected to
  that one") and a link confidence from 0 to 1, and flag any link below the low-confidence threshold
  (default 0.5); a path through a flagged link is flagged. For each path that finishes the beam search, a
  model step MUST record a reasoned assessment for each of the seven per-path dimensions in FR-007, using
  the grammar's states for that dimension. These are hypotheses from the objective, MUST be labeled as
  such, and MUST NOT be presented as evidence (Constitution VIII, IX).
- **FR-014**: A path MUST be marked as having real-world evidence only when at least one company found
  for it is verified under feature 002's rules; a final path for which none is found MUST be marked "no
  real-world evidence found".

**Beam search (story 4)**

- **FR-015**: The beam search MUST proceed level by level from segment to use case and, at each level,
  in this order: filter the extended paths by the mandatory constraints; score them; apply the diversity
  check; keep the top N (beam width, default 5, configurable). It MUST NOT enumerate all paths before
  pruning; exhaustive traversal is a defect (Constitution XV).
- **FR-016**: Each path's score MUST be the weighted combination of four named factors (objective fit,
  information value, evidence gap, cost), each stored separately with its value, its rationale, and the
  weights used (equal by default, configurable). Scores MUST be stored and shown separately from link
  confidence and from evidence confidence, and MUST NEVER be labeled or presented as confidence.
- **FR-017**: The diversity check MUST keep at most one path for any pair of segment and problem; a path
  removed by it MUST record the kept path it duplicates.
- **FR-018**: Every path that is pruned at any level, or not chosen at the final level, MUST keep its
  status (pruned or deferred), the level, and the reason (constraint broken, diversity, or below the
  beam width with its score).
- **FR-019**: The top M paths at the final level (default 3, configurable) MUST each go to company
  discovery and verification under feature 002's rules, with the path's segment, company archetype,
  problem, trigger, and buyer role as the micro-market, and at most 5 companies kept per path.
- **FR-020**: After company verification, the run MUST record for each final path its Evidence
  Sufficiency, Evidence Quality & Confidence, and Critical Unknowns, using the grammar's states and the
  layer the grammar assigns to each, drawn only from the stored evidence and Review outcomes.

**Buyer roles**

- **FR-021**: For each kept company on a final path, the run MUST identify the buyer roles for the
  path's problem: the functions involved, their authority (owns the budget, approves, uses, or
  influences), and at least one cited excerpt showing that ownership, checked by feature 002's citation
  check. A role without a passing citation MUST be recorded as an explicit unknown. Buyer roles MUST be
  functions or titles only and MUST NOT name, describe, or contact any individual person (feature 002
  FR-018).

**Decisions**

- **FR-022**: The Market Manager MUST record exactly one decision for each final path (pursue, needs
  more evidence, or drop) with its reason and the right used, based only on the path's evaluation, its
  companies' Review dispositions, and the verification results (FR-020). Only the Market Manager MAY
  record this decision or a company disposition (Constitution VI).
- **FR-022a**: At the end of each run the Market Manager MUST record one Market Status for the run
  (progressing, needs-attention, at-risk, blocked, or awaiting-evidence, the grammar's states), with
  its reason and the right used, derived only from the run's stored results: the path decisions, the
  verification results (FR-020), and the unresolved items. It MUST be shown in the viewer and in
  traces like any other decision.

**Traces (all stories)**

- **FR-023**: Every step of every story MUST store a trace record with: run, parent step, layer, actor,
  operation, inputs, outputs, decision and right used, rationale, alternatives considered, checks (each
  with pass or fail and reason), model and prompt version, the prompt sent and the structured response
  received, tool calls (searches and pages fetched), cost, latency, and start and end timestamps. Fields
  that do not apply to a step MUST be recorded as empty, not omitted.
- **FR-024**: Traces MUST contain only what the system stored, sent, and received. They MUST NOT contain
  any hidden reasoning of the model, and MUST NOT contain secrets: keys and tokens MUST be removed
  before a trace is stored.
- **FR-025**: Traces MUST be stored as the step runs, so that a run in progress can be followed, and a
  trace MUST NOT be changed after the step ends.

**Viewer (story 5)**

- **FR-026**: The viewer MUST show, from stored records only: the list of runs; each run's timeline
  grouped by layer (Market Manager, Market Development Controller, Search & Research, Position &
  Evaluation, Workers); every trace field of FR-023 for each step; the seed graph with its validation
  results and path statuses; the beam search per level with kept and pruned paths, reasons, and
  per-factor scores; and the companies with their evidence, buyer roles, and Review dispositions.
- **FR-027**: The viewer MUST show new steps of a run in progress within 5 seconds without a reload.
- **FR-028**: The viewer MUST NOT create, change, or delete any stored record, and MUST NOT start, stop,
  or alter any pipeline step (Constitution XIII). It reads the local store only.
- **FR-029**: Wherever a search score and a confidence (link or evidence) appear together, the viewer
  MUST label them as different measures and never combine them into one value.

**Out of scope**

- **FR-030**: This feature MUST NOT include: named people, contacts, emails, or phone numbers; the
  Campaign Manager or any outreach; Jev; any agent SDK or agent framework; any writing from the viewer;
  or production deployment.

### Key Entities *(include if feature involves data)*

- **Run**: one pass of the pipeline over the objective, with its constraints, configuration (beam
  width, final paths, companies per path, factor weights, repair limit), status, and counts.
- **Trace Step**: one stored record per step with the FR-023 fields, linked to its run and parent step;
  the source for the viewer.
- **Vichara Question**: a self-posed question tied to one of the 19 dimensions, with its answer or
  unresolved marker and the reason.
- **Graph Meaning**: the Market Development Controller's record for the run: levels and their order,
  dimensions per level, allowed relationships, mandatory filters, and what counts as a promising path.
- **Seed Graph**: the nodes and edges built from the vichara answers, with structural and coverage
  validation results, repair attempts, and unresolved items.
- **Node**: one concept at one level (segment, company archetype, problem, trigger, buyer role, use
  case).
- **Link**: an edge between adjacent levels with its rationale and link confidence.
- **Path**: a chain of nodes from segment to use case, with its status (pruned, flagged, kept,
  deferred, final, has real-world evidence, no real-world evidence found), reason, the seven per-path
  dimension assessments, and, for final paths, the verification results.
- **Beam Level Record**: for one level, every candidate path with its per-factor scores, weights,
  diversity outcome, and kept, pruned, or deferred status and reason.
- **Unresolved Item**: a dimension or gap the run could not address, with reason "no information in the
  objective", "excluded by filter", or "repair exhausted".
- **Company Record, Evidence, Review Disposition**: as in feature 002, with each company linked to the
  final path or paths it was found for.
- **Buyer Role**: for one company and path, a function, its authority, and its cited evidence; never a
  person.
- **Path Decision**: the Market Manager's one decision per final path, with reason and the right used.
- **Market Status**: the Market Manager's one summary state per run, with reason and the right used;
  Trajectory and Transition are recorded as unassessed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of runs, all 19 dimensions have at least one answered vichara question or an
  unresolved marker with its reason.
- **SC-002**: 100% of graphs that reach path verification have zero structural violations; 100% of
  repairs stop at 3 attempts or fewer; 100% of runs whose graph still has a structural violation after
  repair end failed at the validation stage with the violations listed.
- **SC-003**: 100% of links in the graph have a rationale and a link confidence, and 100% of pruned or
  deferred paths have a recorded reason and a count of the complete paths below them.
- **SC-004**: At every beam level, no more than the beam width (5 by default) paths are kept, and no two
  kept paths share both segment and problem.
- **SC-005**: Every final path either has at least one verified company or is marked "no real-world
  evidence found"; no path is marked as existing in the real world without a verified company.
- **SC-006**: 100% of pipeline steps have a stored trace with every FR-023 field present, and an audit
  of stored traces finds zero secrets.
- **SC-007**: A team member can answer, from the viewer alone and in under 2 minutes per question, why
  a given path was pruned, kept, or deferred, and why a given company got its disposition.
- **SC-008**: During a run, each new step appears in the viewer within 5 seconds, and in 100% of
  attempts the viewer offers no way to change data or control the pipeline.
- **SC-009**: In 100% of displays and stored records, search scores are labeled and kept separate from
  link confidence and evidence confidence.
- **SC-010**: Every buyer role shown for an included company rests on at least one passing citation,
  and no stored record or display names an individual person.

## Assumptions

- **Default configuration**: beam width 5, final paths 3, companies per final path 5, repair limit 3,
  low link-confidence threshold 0.5, equal factor weights. All are configuration values.
- **Run size**: with these defaults a run verifies at most 15 companies, more than feature 002's limit
  of 10. The limit of 5 applies per final path, and feature 002's other budgets apply per path.
- **Inputs from feature 002**: the program file, metros, size thresholds, source policy, budgets, and
  the local emulator store are reused; this feature adds no new data source.
- **Company search per path**: each final path is used the way feature 002 uses a first position
  (segment, company archetype, buyer, problem, trigger), so its targeting, citation checks, and Review
  apply unchanged.
- **Grammar**: the 19 dimensions, their states, and the layer that assesses each come from the HipStraw
  grammar as it stands on 2026-10-08; it will be copied into this project so runs do not depend on a
  sibling project.
- **Viewer users**: HipStraw team members on the machine running the local emulator; no sign-in, and no
  access from other machines.
- **Recorded tests**: as in feature 002, behavior is tested with recorded model, search, and fetch
  responses on fictional `.test` companies; live runs are demos, not tests.
- **Feature 002 stays usable**: its existing commands and reports keep working; this feature adds a new
  pipeline that reuses its parts.
