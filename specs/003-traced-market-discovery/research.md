# Research: Traced Market Discovery Pipeline

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-10-08

The spec has no open clarifications. The decisions below settle the technical unknowns it leaves
(Technical Context in the plan). Each has a decision, a reason, and the alternatives rejected.
Constitution v1.2.0 applies throughout.

## R1. How this feature relates to feature 002's runs

- **Decision**: A new `marketRuns` collection holds one run per program pass, with its own stage
  machine: `opened → deliberated → defined → graphed → validated → linked → searched → assessed →
  verified → roled → decided → reported` (any stage may go to `failed`). Companies are found by running feature
  002's own pipeline once per final path, as a **child run** in the existing `runs` collection. Child run
  IDs are `<marketRunId>_p1`, `_p2`, `_p3`, and each child has `parentMarketRunId` and `pathId`.
  Feature 002's `discover`, `verify`, and `review` functions are called unchanged. Two small changes to
  002: `position` can create a run from a path in code (explicit run ID, no file), and a child run's
  `companiesKept` budget is set to 5.
- **Why**: FR-003 says 002's rules apply unchanged. Child runs keep 002's evidence IDs, state machine,
  review decisions, baselines, and report working with no edits, and its tests keep passing. `new_run_id`
  is clock-based, so three child runs made in the same second would collide; explicit child IDs avoid
  that.
- **A company found for two paths** (spec edge case): each child run has its own `companyRecord`. A
  parent-level `marketCompanies` document, keyed by the company's domain key, links the records and
  shows every path's disposition. If the dispositions differ, both are shown (Constitution VIII: no
  silent resolution). It counts toward each path's limit of 5.
- **Alternatives rejected**: (a) one flat run with a `pathId` on every 002 record: touches every 002 step,
  query, and test. (b) Reusing `runs` for the parent: its status machine is 002's fixed five states.

## R2. Where traces are stored, and why they can be followed live

- **Decision**: Three create-or-seal collections:
  - `traceSteps/{marketRunId}__{seq}`: one document per step, with the FR-023 fields **except** large
    payloads. It is created when the step starts (`status: running`) and sealed once, at the step's
    end, to `ok` or `failed` (counts, outputs, checks, cost, latency, end time added). After sealing it
    never changes (FR-025). `seq` is a per-run counter, so the viewer can ask for "steps after N".
  - `traceBlobs/{marketRunId}__{seq}__{n}`: create-only payloads (a prompt, a structured response, a
    search result list), referenced from the step by ID. A blob over 900 KB is cut with an explicit
    `truncated: true` and its original byte size, because Firestore documents are limited to 1 MB.
  - Page text is **not** stored in traces. A fetched page appears as URL, final URL, HTTP status, fetch
    time, byte count, and content hash (the same hash feature 002 stores in evidence).
- **Why**: A start document makes a running step visible at once (FR-027). One allowed transition, like
  002's `transition_run`, makes immutability a store rule, not a convention. Keeping prompts and responses
  in blobs keeps the run timeline light to list.
- **Alternatives rejected**: (a) append-only event log, reassembled by the viewer: no single record to
  seal, harder to prove FR-025. (b) Writing traces to `.runs/*.log` only: not queryable by layer or step
  and not visible to the viewer through the store. The JSON-lines log stays as it is (Constitution V).

## R3. How steps report their layer, rights, and tool calls

- **Decision**: A `Tracer` (in `hipstraw_mm/market/trace.py`) is the only writer of trace records.
  - `with tracer.step(layer, actor, operation, ...) as step:` opens a step; `step.record_*` calls fill in
    inputs, outputs, decision, rationale, alternatives, and checks; leaving the block seals it (`failed`
    if an exception escaped).
  - The layer, actor, and **right** of every step must be declared in `config/layers.yaml`, which lists
    each layer's one responsibility, its actors, and the rights it may use. The Tracer rejects an
    undeclared combination, so a step cannot claim a right its layer does not have (Constitution XIV).
  - Adapters get an optional **observer** callback. `LLMClient`, `BraveSearch`, and `Fetcher` call it with
    what they sent and received (model, prompt, response, token usage, attempt; query and results; URL,
    status, hash). The Tracer attaches each call to the step that is open at that moment.
- **Why**: Feature 002's adapters are shared, and one observer hook is the smallest change that captures
  every tool call without each step repeating it. Making `layers.yaml` the source of rights keeps "who may
  decide what" in data that tests can check.
- **Cost**: the OpenAI response carries token counts; the LLM adapter records them in the replay file as
  `usage`. Cost is computed from `config/pipeline.yaml` `modelPricing` (price per million tokens by model
  name). Older recordings have no `usage`, so their cost is recorded as unknown, not zero. **Latency** is
  measured around each call and each step (milliseconds), in replay too.
- **Alternatives rejected**: a global/context-variable tracer that adapters find themselves (hidden
  coupling, hard to test); wrapping every adapter in a proxy class (more code than a callback).

## R4. Secrets never reach a trace

- **Decision**: The Tracer passes every string it stores through `logging_setup.scrub` (the function 002
  uses for logs), recursively over all fields and blobs, at the single point where records are written.
  Request headers are never recorded (the Brave key travels in a header; the OpenAI key never leaves the
  client). A test sets fake `OPENAI_API_KEY` and `BRAVE_API_KEY` values, runs a full replay scenario, and
  scans every stored trace and blob for them (SC-006).
- **Why**: One choke point can be tested; per-step redaction cannot.
- **Limit**: `scrub` works on values in the environment variables listed in `SECRET_ENV_VARS`. Any new
  secret must be added there. The plan adds no new secret.

## R5. The 19 dimensions

- **Decision**: Copy `hipstraw-faculty/seed_data/grammar.json` into this project as `config/grammar.yaml`
  with a header recording the source path, the SHA-256 of the source file, and the date. It is validated
  at load (exactly 19 unique keys; each with name, question, states, rank, level, `assessedBy`,
  `decidedBy`). A test checks the 19 keys against the spec's list.
- **Data fix**: four names and questions in the source contain a replacement character (�) where a dash
  was lost (for example "Risks / Critical Risks � Status"). The copy replaces each with an en dash and the
  header lists the four fixes, so the copy is not silently different from its source.
- **Why**: FR assumption: runs must not depend on a sibling project.
- **Alternatives rejected**: reading the sibling path at run time (breaks on any other machine); copying
  the JSON verbatim with the defects (they would show in the viewer).

## R6. Vichara (self-questioning)

- **Decision**: One model call per dimension (19 calls). Each call receives the dimension (key, name,
  question), the **objective bundle** (program objective, the six experiment contexts, and the
  constraints, as text) and returns 1 to 3 items, each either `answered` (question, answer, one or more
  `basis` excerpts) or `unresolved` (question and reason).
- **Grounding check (deterministic)**: every `basis` excerpt must appear in the objective bundle after
  the same normalization as feature 002's citation check (`excerpt_check.normalize`). An answered item
  whose basis fails is treated as failing the coverage check and goes to repair (R7). The model
  therefore cannot answer from its own memory without the system noticing (Constitution IX).
- **Thin versus zero information** (feature 001): thin information is still answered (the basis is the
  thin text, and downstream link confidence reflects it). Zero information is `unresolved` with the reason
  "no information in the objective". `unresolved` is never used to mean "I'd rather not".
- **Why one call per dimension**: it makes each question and answer its own traced Worker step (FR-004,
  story 1 scenario 5) and isolates a failure to one dimension. A single 19-dimension call would make the
  per-question trace a reconstruction.
- **Cost**: 19 calls, short inputs. Accepted.
- **Alternatives rejected**: one call for all 19 (loses per-dimension steps; a single failure repeats
  everything); a model-proposed list of dimensions (the grammar already defines them).

## R7. Coverage check and bounded repair, shared by vichara and the graph

- **Decision**: One mechanism, `bounded_repair(check, repair, limit=3)`, used twice (vichara coverage;
  graph coverage and structure):
  1. Run the deterministic check, then the model judgement. Collect the failing items.
  2. If none fail, stop. Otherwise make **one** repair call for all failing items in that attempt.
  3. Re-run both checks. An attempt that makes the deterministic check fail in a **new** way counts as a
     failed attempt (feature 001).
  4. After 3 attempts, record each still-failing item as an `UnresolvedItem` with reason `repair
     exhausted`, and continue. Nothing is dropped.
- **Why**: Batching all failing items into one repair call keeps the call count bounded at 3 repairs plus
  3 re-checks per phase, not per item.
- **Repair is additive**: a repair response may add nodes and edges (or re-answer named dimensions) but
  cannot delete or edit existing ones, so "touches only the gap" is checked by comparing before and after.

## R8. The graph's meaning (Market Development Controller)

- **Decision**: The Market Development Controller step is **deterministic**: it reads
  `config/graph_meaning.yaml` and records it as the run's meaning (FR-006). That file defines:
  - the six levels in order, each mapped to a grammar dimension: segment → `market_scope`, company
    archetype → `segment_fit`, problem → `problem`, trigger → `timing`, buyer role → `buyer`, use case →
    `use_case`;
  - the allowed relationships (each level links only to the next);
  - the mandatory filters, as structured rules over node attributes: segment nodes carry `metroIds`
    (each must be in the run's metros); archetype nodes carry `sizeBand` (one of `startup`, `small`,
    `mid_market`, `enterprise`; `enterprise` is excluded); and the run's size limits;
  - what a promising path is (the four scoring factors and their default weights);
  - the per-node caps (nodes per level, links per node).
- **Why**: FR-002 makes the controller the owner of what the graph means; a model must not invent it.
  Structured attributes with enumerated values are what make "within the mandatory filters" a
  deterministic check (FR-009) rather than another judgement.
- **Alternatives rejected**: a model call that "proposes" the meaning (the constitution and feature 001
  both put semantics with the controller, not a worker); putting the rules in code (not visible in the
  record the viewer shows).

## R9. Generating the graph

- **Decision**: Six model calls, one per level, in order. Level 1 receives the vichara answers and the
  graph meaning and returns segment nodes. Each later level receives the previous level's nodes and the
  relevant answers and returns that level's nodes with `parentIds`. Every node carries its attributes (R8),
  a short `label`, and `sourceQuestionIds` (the vichara items it came from). Edges are the `parentIds`.
- **Hard filters are applied before a node exists** (feature 001): after each call the system removes any
  node that breaks a mandatory filter and records "excluded by filter" with the node; if that empties a
  level, the level gets an `UnresolvedItem` (`excluded by filter`) and later levels are not generated
  from it.
- **Caps**: at most `nodesPerLevel` (default 5) nodes per level and `parentsPerNode` (default 2). Extra
  nodes are dropped in the model's order and logged as `over cap`; the caps keep the graph, and so the
  beam, bounded (Constitution XV).
- **Alternatives rejected**: one call for the whole graph (a single failure repeats everything, and the
  trace has one huge step); generating all level-to-level combinations (cross product, exhaustive).

## R10. Structural validation

- **Decision**: Pure functions over the graph document, so the verdict is repeatable. Rules (FR-009):
  orphan (no edge at all), dangling edge (an endpoint not in the graph), undefined level, edge that skips or
  reverses level order, duplicate node ID, schema violation (the Pydantic model rejects it first), node
  outside a mandatory filter, and a level with no nodes that has no `UnresolvedItem`. Each violation names
  the node or edge and the rule. A node with several parents is not a violation (feature 001).
- **Why**: Plain functions can be tested exhaustively with small hand-built graphs.

## R11. Link verification, and why no step lists all paths

- **Conflict found while planning**: FR-012 and FR-013 say each "full path" is verified, and story 3 puts
  this before the beam search. But Constitution XV says exhaustive traversal is a defect, and a graph with
  5 nodes per level and 2 parents per node can hold hundreds of full paths.
- **Decision**: No step enumerates every path. Verification is split by what is bounded:
  1. **Links** (bounded by the caps in R9, at most 5 × 5 × 2 per level pair): after validation, one model
     call per level pair (chunked at 12 links per call) gives each link a rationale and a link confidence.
     A link below the threshold (default 0.5) is flagged.
  2. **Deterministic path checks** run on every path the beam **reaches** (FR-012): the beam extends
     only the paths it keeps, and each extension is checked against the objective's constraints; a failing
     extension is pruned with its reason.
  3. **Per-path assessments** (the seven dimensions, FR-013) run on the paths that finish the beam (at
     most the beam width, default 5).
  A path the beam never reaches is not a stored path; its subtree is counted. For every pruned or deferred
  partial path the beam stores `pathsBelow`, the number of complete paths under it, computed by counting
  over edges (linear in the number of edges, not by listing the paths). The viewer shows that number so
  "what was never looked at" is visible.
- **Effect on the spec**: stories 3 and 4 still hold; the order of work differs from the order of stories
  (links first, path checks and assessments after the beam reaches paths). The plan keeps FR-012 to FR-014
  satisfied for every path that matters and records this as a flag in the plan.
- **Alternatives rejected**: enumerating all paths first (violates XV, and cost grows with the product of
  the level sizes); sampling paths at random (not reproducible, hides what was skipped).

## R12. Beam search

- **Decision**: Level by level from segment to use case. The beam holds at most `beamWidth` (default 5)
  partial paths. At each level, for every kept path, extend by each child node (so at most `beamWidth ×
  parentsPerNode × nodesPerLevel` candidates, a small fixed bound), then:
  1. **Filter**: drop an extension that breaks a mandatory constraint (deterministic).
  2. **Score**: one model call per level scores all remaining candidates on the four factors, each 0 to 1
     with a one-line rationale: objective fit, information value, evidence gap, cost. The system combines
     them with the configured weights (equal by default) into `searchScore`, and stores each factor, the
     weights, and the score. Link confidence of the path's links is shown beside the score and is **not**
     part of it.
  3. **Diversity**: walk the candidates in score order and skip any whose pair (segment, problem) already
     belongs to a kept path. Paths shorter than the problem level have no problem yet, so **no diversity check runs before the
     problem level** (two partial paths that share only a segment are both kept); diversity applies from
     the problem level on.
  4. **Keep** the top `beamWidth`. Everything else is stored as `pruned` (a constraint) or `deferred`
     (diversity, or below the beam width), each with its reason and `pathsBelow`.
  At the final level the kept paths are the complete paths. The top `finalPaths` (default 3) go to company
  discovery; the rest are `deferred` with "below the final-path limit".
- **Why scoring by a model**: objective fit, information value, and evidence gap are judgements. They are
  stored as labelled hypotheses with rationales, never as confidence (FR-016, Constitution XV). Filtering,
  diversity, and keeping are deterministic and fully tested.
- **Alternatives rejected**: deterministic factor formulas (they would need definitions of "information
  value" that the spec does not give); a larger beam with a cost penalty (adds knobs without a request).

## R13. Reusing company discovery for each final path

- **Decision**: For each final path the system builds a 002 position from its nodes: segment = segment
  label; company archetype = archetype label; buyer = buyer role label; problem = problem label; trigger =
  trigger label; `primaryInterestIds` = the program's interests named in `config/pipeline.yaml` `defaultInterestIds` (at
  least one; nodes carry no interest field, so a configured default is used, defaulting to the two
  interests of the first live run); `searchHints` = the path's use case label and the
  metro names. It then runs 002's `discover`, `verify`, and `review` on the child run.
- **Child-run candidate**: feature 002's run needs a `candidateId` (its report and Review read the candidate record), and `MarketCandidate.experimentContextId` and `origin` are required, non-optional fields. The system creates one synthetic `marketCandidates` document per final path, ID `<marketRunId>__<pathId>`, with the path's labels as its `label`, `experimentContextId` set to the path's `pathId` (there is no program experiment context for a traced path), and `origin: traced_path` — one new literal value added to `MarketCandidate.origin` (additive; feature 002's own candidates keep `program_experiment_context`, and its tests pass untouched). The record is used as the child run's `candidateId`. This reuses 002's run machinery unchanged; nothing in 002 learns about paths.
- **Within a path**, 002's own targeting (metro queries, round-robin reading, ranking before the cap)
  still orders candidates. The beam search replaces what 002 had *above* that: the single hand-written
  first position. This matches the spec's "replaces 002's flat candidate ranking" for choosing which
  micro-markets to search.
- **Limits**: `companiesKept` is 5 for a child run; all other 002 budgets are unchanged, per path.
- **Alternatives rejected**: calling only 002's discovery and skipping verify and review (violates
  FR-003, and a company would be unverified).

## R14. Buyer roles

- **Decision**: After a child run's Review, one model call per final path (batched over its at most 5
  companies) receives each company's name, the path's problem and buyer role, and the company's
  **already-stored, passing evidence documents** (ID, claim, excerpt). It returns roles: a function or
  title, an authority (`owns_budget`, `approves`, `uses`, or `influences`), and the `evidenceIds` that
  support it. The system keeps a role only if every cited ID is a passing evidence document of that
  company (the same rule as T065 for judgements); otherwise the company gets an explicit unknown for
  buyer role. Output has no field for a person's name, email, or phone number (FR-021, FR-030).
- **Why no new fetches**: it uses evidence 002 already collected and checked, so every cited excerpt has
  passed the citation check, and no new page is read.
- **Known limit**: roles are only as good as the evidence 002 gathered (job postings and about pages
  rarely state authority). Many companies will have an unknown role. That is shown, not hidden. A
  targeted fetch is deferred (Constitution X).
- **Alternatives rejected**: asking the model for roles from general knowledge (violates IX); adding role
  claims to `CompanyEvidence` (changes a schema whose real recordings were just remade, for no gain).

## R15. Decisions and Market Status (Market Manager)

- **Decision**: The Market Manager steps are deterministic rule tables, recorded with the rule that fired.
  - **Path decision** (FR-022): `pursue` if at least one company on the path is `include`d and the path's
    Evidence Sufficiency is at least `sufficient`; `drop` if the path has no verified company and its
    unknowns are not being reduced (no company reached `needs_verification` with a missing citation that
    more evidence could fill); otherwise `needs more evidence`.
  - **Market Status** (FR-022a): `progressing` if at least one path is `pursue`; `blocked` if every path
    is `drop` or no path survived; `at-risk` if no path is `pursue` and a repair or filter left an
    unresolved item at the segment or buyer level; `awaiting-evidence` if no path is `pursue` and at least
    one is `needs more evidence`; else `needs-attention`.
  - **Rights**: each records its right (`decide_path`, `set_market_status`) from `layers.yaml`.
- **The manager never traverses the graph**: its steps receive a `ManagerView`, an object built from the
  final paths, their evaluations, and the run summary only. It has no access to graph documents or the
  store. A test passes a store spy and asserts that the manager steps read no graph, node, edge, or beam
  document (FR-002).
- **Why rules, not a model**: decisions must be explainable from stored records (FR-022). The rule that
  fired is the rationale.
- **Alternatives rejected**: a judgement call for the decision (reintroduces an unverifiable step at the
  point where Constitution VI wants accountability).

## R16. Evidence results per path (FR-020)

- **Decision**: Deterministic, from the child run's stored records, using the grammar's states:
  - **Evidence Sufficiency** (`insufficient`, `partial`, `sufficient`, `decision-ready`): by the number of
    companies with all four minimum proofs (existence, location, size, interest signal) passing:
    none = `insufficient`; fewer than half of the companies = `partial`; at least half = `sufficient`;
    all of them and at least three = `decision-ready`.
  - **Evidence Quality & Confidence** (`weak`, `mixed`, `strong`, `stale`, `contradictory`,
    `high-confidence`): from the companies' evidence confidence (feature 002 bands): any conflict kept
    in the records = `contradictory`; else mean value under 0.5 = `weak`, 0.5 to 0.79 = `mixed`, 0.8 or
    more = `strong`; `high-confidence` needs `strong` and no needs-verification company. `stale` is not
    produced yet (it needs dated evidence; feature 002 records publish dates only when known).
  - **Critical Unknowns** (`unidentified`, `open`, `investigating`, `reduced`, `resolved`): `open` if any
    company has an unknown for a minimum proof; `reduced` if all companies have all four proofs but some
    other unknown remains; `resolved` if none remain; `unidentified` if there are no companies.
  The step runs in the **Position & Evaluation** layer with right `evaluate_evidence`; each result also
  stores the grammar's own `assessedBy` for that dimension as a field, which the viewer shows.
- **Why**: the thresholds are stated in one place and testable; the spec asks for states, not a method.
  They are defaults a reviewer may change in `pipeline.yaml`.

## R17. The viewer

- **Decision**: A small read-only web server in the same package, started by `hipstraw-mm view`:
  - Python standard library only (`http.server`), bound to `127.0.0.1`, serving one static HTML page with
    plain JavaScript (no build step, no framework) and a JSON API (`contracts/viewer-api.md`).
  - It is constructed with a `ReadStore`, a protocol that has **only read methods**. There is no write
    method on the object it holds, so the viewer cannot write by construction (Constitution XIII). The
    server accepts only `GET` and `HEAD`; every other method returns 405. A test lists every route and
    method, and a store spy confirms zero writes.
  - **Live updates**: the page polls `/api/runs/<id>/steps?after=<seq>` every 2 seconds and appends new or
    sealed steps. A step shows as running from the moment its start record is written, so a new step is
    visible within about 2 seconds, inside the 5-second target (FR-027). Server-sent events were not
    chosen: polling needs nothing the standard library lacks and is trivially testable.
  - Scores and confidences are different JSON fields (`searchScore`, `linkConfidence`,
    `evidenceConfidence`) and are drawn in separate, labelled columns (FR-029). A test asserts no API
    response combines them and that the page's labels exist.
- **Why**: no new dependency (Constitution technology section: minimize, justify each), a one-command
  start, and read-only that can be proved. The user's machine runs the emulator already.
- **Alternatives rejected**: (a) Firestore Web SDK with listeners and deny-write security rules: needs a
  JavaScript toolchain, a second runtime, and the Python client bypasses the rules anyway, so the guarantee
  would not hold for the pipeline. (b) FastAPI/uvicorn: two new dependencies for six GET routes. (c) The
  emulator's own UI on port 4005: not read-only, not grouped by layer, no scores view.

## R18. Budgets and run size

| Stage | Model calls | Notes |
|-------|-------------|-------|
| Vichara | 19 | one per dimension |
| Vichara coverage and repair | 1 + up to 3 × (1 repair + 1 re-check) = 7 | batched per attempt |
| Graph meaning | 0 | deterministic |
| Graph generation | 6 | one per level |
| Graph validation and repair | 1 + up to 3 × (1 + 1) = 7 | |
| Link verification | about 5 to 8 | one per level pair, chunked at 12 links |
| Beam scoring | 6 | one per level |
| Path assessment | up to 5 | one per kept final-level path |
| **Before companies** | **about 51 to 58** | |
| Companies (feature 002) | up to 3 × about 20 = 60 | its own budgets, per child run |
| Buyer roles | up to 3 | one per final path |
| **Whole run** | **about 115 to 125** | ceiling `modelCallsPerRun`: 150 |

- A run's wall-clock estimate is about 20 to 30 minutes, dominated by the three 002 child runs. This is a
  target, not a gate.
- Companies: at most 5 × 3 = 15 per run (spec assumption).
- Ceilings are configuration values. Running out stops the run with the stage marked `failed` and the
  partial counts kept (as 002's T055 will for verify).

## R19. Testing without a network

- **Decision**: The same replay approach as feature 002. `tests/fixtures/build_fixtures.py` gains the new
  response kinds, built from YAML scenarios on fictional `.test` companies. Match keys avoid run IDs
  where they can: `Vichara:<dimensionKey>`, `VicharaRepair:<attempt>`, `GraphLevel:<level>`,
  `GraphCoverage:<attempt>`, `GraphRepair:<attempt>`, `LinkVerification:<levelPair>:<chunk>`,
  `BeamScoring:<level>`, `PathAssessment:<pathKey>`, `BuyerRoles:<pathKey>`. Child-run keys for 002's calls
  are unchanged (they use child run IDs, which are explicit).
- **Layers of tests**: unit tests for every deterministic rule (validation, filters, diversity, rule
  tables, caps, `pathsBelow`); store contract tests for the new collections on both stores; integration
  tests per story with recorded responses; viewer API tests against a server on an ephemeral localhost
  port; and the two adversarial tests that matter most here: the manager never reads the graph, and a
  planted fake secret never appears in a trace.
- **The viewer page itself** is checked in a real browser during implementation, and quickstart lists the
  steps; there is no browser-automation dependency in the test suite.
- **Real recordings**: each new model schema gets one real recording like 002's (Constitution IV), made by
  a team member with keys.

## R20. Delivery in small increments (Constitution X)

This feature is larger than 002's slices. It is delivered in the spec's story order, each increment with
its tests approved before code (Constitution III) and runnable on its own:

1. **Trace foundation and viewer shell** (needed by every story): layers file, Tracer, trace collections,
   observers, read-only store, viewer with run list and timeline.
2. **Story 1 and 2**: grammar, vichara, coverage, graph meaning, graph generation, validation and repair,
   graph view.
3. **Story 3**: link verification (and the path checks and assessments that attach to the beam).
4. **Story 4**: beam search, child-run company discovery, buyer roles, path decisions, Market Status, beam
   and companies views.
5. **Story 5 completion**: the remaining viewer views and live updates for every view.

This is also flagged in the plan's Constitution Check (Principle X).
