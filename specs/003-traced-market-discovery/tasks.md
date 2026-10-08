# Tasks: Traced Market Discovery Pipeline

**Input**: Design documents from `specs/003-traced-market-discovery/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R20), data-model.md, contracts/ (cli, config,
llm-outputs, viewer-api), quickstart.md. Constitution v1.2.0.

**Tests**: Required. Constitution III makes test-first mandatory, and each phase below has an **approval
checkpoint** after its tests and before its code: the tests are run to show they fail for the intended
reason, then presented to the user. No code task in a phase starts before its checkpoint is approved.

**Organization**: Tasks are grouped by user story. The plan's five delivery increments map to phases as
follows: increment 1 = Phase 2, increment 2 = Phases 3 and 4, increment 3 and the path machinery of
story 3 = Phase 5, increment 4 = Phase 6, increment 5 = Phase 7.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 to US5, as in spec.md (US1 vichara and seed graph, US2 graph validation, US3 path
  verification, US4 beam search to companies and buyer roles, US5 trace viewer)
- Paths are from the repository root. `config/` files are new unless stated.
- Constraints from data-model.md and the contracts are quoted in the task that implements them.
- Commit after each task (message ends with the attribution line required in this session).

## Conventions that apply to every task

- Every step records its trace through the `Tracer`; no step writes a trace record any other way.
- Every model call goes through `LLMClient.parse`, with the replay match key from
  contracts/llm-outputs.md.
- Field names for the three measures are fixed: `searchScore`, `linkConfidence`, `evidenceConfidence`.
  The bare word `confidence` is never a field of a search score (FR-016, FR-029).
- No schema, record, or prompt has a field for a person's name, email, or phone number (FR-030).
- Plan addition: pure path helpers live in `src/hipstraw_mm/market/paths.py` and settings loading in
  `src/hipstraw_mm/market/settings.py` (not listed in the plan's tree).

---

## Phase 1: Setup

**Purpose**: package skeleton and test plumbing.

- [x] T001 Create `src/hipstraw_mm/market/__init__.py` and `src/hipstraw_mm/viewer/__init__.py`, each with a docstring stating the package's purpose and bounded responsibility (Constitution I, VI: the market package runs the traced pipeline and writes findings and decisions only through its steps; the viewer package only reads), and the empty directory `src/hipstraw_mm/viewer/static/`.
- [x] T002 [P] Update `pyproject.toml`: include `src/hipstraw_mm/viewer/static/*` and `src/hipstraw_mm/prompts/*.txt` in the wheel; add the pytest marker `viewer` ("starts the read-only viewer on 127.0.0.1"). In `tests/conftest.py`, give tests marked `viewer` the `allow_hosts(["127.0.0.1", "localhost", "::1"])` socket exception, as the `emulator` marker has.

**Checkpoint**: `pytest tests -q` still passes unchanged.

---

## Phase 2: Foundational (increment 1): layers, traces, read-only store, viewer shell, `market start`

**Purpose**: everything every story needs: declared layers and rights, the Tracer and its stored records, the
adapter observers, the read-only store, and a viewer that lists runs and shows a run's timeline.

**CRITICAL**: no story phase starts until this phase is done.

### Tests for the foundation (write first; they must fail)

- [ ] T003 [P] Unit tests in `tests/unit/test_layers.py` for `config/layers.yaml` and `src/hipstraw_mm/market/layers.py`: the five layer ids are `market_manager`, `market_development_controller`, `search_research`, `position_evaluation`, `workers`, in that order; a right belongs to exactly one layer; actors are unique; `check(layer, actor, right)` accepts every declared triple and raises for an undeclared actor, an undeclared right, or a right declared under another layer (for example `decide_path` under `search_research`).
- [ ] T004 [P] Unit tests in `tests/unit/test_pipeline_settings.py` for `config/pipeline.yaml` and `src/hipstraw_mm/market/settings.py`, one case per rule in contracts/config.md: `beam.finalPaths <= beam.width`; `beam.companiesPerPath <= 10`; factor weights all above 0 and normalized when used; `repair.maxAttempts` between 1 and 3; `viewer.host` must be a loopback address (`127.0.0.1`, `localhost`, `::1`); a model missing from `modelPricing` gives unknown cost; defaults equal the contract's values.
- [ ] T005 [P] Unit tests in `tests/unit/test_trace.py` for `src/hipstraw_mm/market/trace.py`, with a fake clock and the memory store:
  - opening a step writes a `running` record at once, with every FR-023 field present and empty when it does not apply (never omitted);
  - leaving the block seals it `ok`; an exception inside seals it `failed` with a scrubbed `error` and re-raises;
  - sealing twice raises `InvalidTransitionError` (FR-025);
  - `seq` increases by 1 per step and `marketRuns.lastSeq` follows; `parentStepId` is the step open when the child opened;
  - an undeclared layer, actor, or right raises before anything is written (Constitution XIV);
  - observer events attach as `toolCalls` of the step open at that moment and a model call stores `promptBlobId` and `responseBlobId`;
  - latency is measured from the clock; cost is `{inputTokens, outputTokens, usd}` with `null` for any unknown part, never 0 for unknown;
  - a blob over `trace.maxBlobBytes` (900000) is stored with `truncated: true` and its original `bytes`;
  - the Tracer counts every model call it observes (including feature 002's calls in child runs) and, when a step's model call would exceed `budgets.modelCallsPerRun` (150), raises so the stage seals `failed`; the run's `counts.modelCalls` and the partial records are kept (contracts/cli.md exit code 4).
- [ ] T006 [P] Unit tests in `tests/unit/test_trace_scrub.py`: every string in a trace record and blob, at any depth in dicts and lists, passes through `logging_setup.scrub`; a value of `OPENAI_API_KEY` or `BRAVE_API_KEY` (set to fake values of at least 8 characters) is replaced by `[redacted]`; request headers are never recorded in a tool call.
- [ ] T007 [P] Store contract tests in `tests/contract/test_trace_store_contract.py`, run on both stores (the emulator ones marked `emulator`): `traceSteps` seal-once rule (`running` to `ok` or `failed` once, then `InvalidTransitionError`); `traceBlobs` create-only (`AlreadyExistsError` on the second create); `list_trace_steps_after(run, seq)` returns ascending order and includes running steps; `get_trace_steps(run, [seqs])` returns current state; `transition_market_run` follows `opened → deliberated → defined → graphed → validated → linked → searched → assessed → verified → roled → decided → reported`, any stage may go to `failed`, nothing else is allowed (data-model.md).
- [ ] T008 [P] Contract tests in `tests/contract/test_read_store.py`: `ReadStore` (in `src/hipstraw_mm/store/base.py`) exposes only read methods, checked by listing its public methods and asserting none starts with `create`, `upsert`, `transition`, `finish`, `seal`, `delete`, `set`, or `put`; both stores satisfy it; the viewer's constructor rejects an object that has any such method.
- [ ] T009 [P] Unit tests in `tests/unit/test_adapter_observers.py`: `LLMClient`, `BraveSearch`, and `Fetcher` call an optional observer once per call with what was sent and received (model, prompt version, messages, response, attempt, token `usage`; query and result list; URL, final URL, HTTP status, fetch time, byte count, content hash, never page text or headers); with no observer, behavior is unchanged and feature 002's tests need no edits; in record mode the model recording gains `usage` when the response has it, and an old recording without `usage` replays with `usage: null`.
- [ ] T010 [P] Integration test in `tests/integration/test_market_start.py`: `market start --program invoice_alpha` through `cli.main` creates a `marketRuns` document `opened` with the objective bundle (program objective text, all six experiment contexts, the constraints), the frozen pipeline settings, `lastSeq`, and one `market_manager` step (right `open_run`) that is `ok` with the run's ID in its outputs; a program that was not loaded exits with code 2; `market show` prints stage and counts.
- [ ] T011 [P] Unit tests in `tests/unit/test_viewer_api.py` for `src/hipstraw_mm/viewer/api.py`: `/api/runs` newest first with `marketStatus`; `steps?after=N` returns only `seq > N`, running steps included, bodies omitted but blob IDs present; `steps?refresh=1,4` returns current states; one step returns every FR-023 field; unknown run or step gives a 404 body `{"error": ...}`; blobs return `{blobId, kind, content, truncated, bytes}`; feature 002's company `confidence` is renamed `evidenceConfidence` in every response (contracts/viewer-api.md).
- [ ] T012 [P] Integration tests in `tests/integration/test_viewer_server.py` (marker `viewer`), against a server on an ephemeral `127.0.0.1` port: `GET` and `HEAD` work on every route; `POST`, `PUT`, `PATCH`, and `DELETE` on every route (including `/`) return 405 with `Allow: GET, HEAD`; starting with a non-loopback host raises; a request with a `Host` header that is not `127.0.0.1`, `localhost`, or the configured host returns 403; starting with an object that has a write method raises; a store spy records zero write calls across a request to every route; a port already in use exits with code 2.
- [ ] T013 [P] Integration test in `tests/integration/test_trace_secrets.py`: set fake `OPENAI_API_KEY` and `BRAVE_API_KEY` values, plant them in a step's inputs and in a simulated tool-call payload, run `market start`, then scan every stored `traceSteps` and `traceBlobs` document as JSON text and assert neither value appears (FR-024, SC-006). This test is run again in Phase 8 over a full run.

### Approval checkpoint

- [ ] T014 Run T003 to T013 and confirm each fails for the intended reason (missing module, missing method), then present them for **user approval** (Constitution III). Do not start T015 before approval.

### Implementation for the foundation

- [ ] T015 [P] Write `config/layers.yaml` exactly as in contracts/config.md and `src/hipstraw_mm/market/layers.py` (Pydantic model, loader, `check(layer, actor, right)`), making T003 pass.
- [ ] T016 [P] Write `config/pipeline.yaml` as in contracts/config.md and `src/hipstraw_mm/market/settings.py` (`PipelineSettings`, loader, the validation rules of T004, pricing lookup), making T004 pass.
- [ ] T017 Create `src/hipstraw_mm/market/models.py` with Pydantic records `MarketRun`, `TraceStep`, `TraceBlob`, `UnresolvedItem`, `ToolCall`, `Check`, `Cost`, following data-model.md field for field. Quote these constraints in the models: `layer` is one of the five layer ids; `status` of a trace step is `running`, `ok`, or `failed`; a market run's `status` is one of `opened`, `deliberated`, `defined`, `graphed`, `validated`, `linked`, `searched`, `assessed`, `verified`, `roled`, `decided`, `reported`, `failed`; an unresolved item's `reason` is `no information in the objective`, `excluded by filter`, or `repair exhausted`; `marketStatus.state` is `progressing`, `needs-attention`, `at-risk`, `blocked`, or `awaiting-evidence`.
- [ ] T018 In `src/hipstraw_mm/store/base.py`, add the `ReadStore` protocol (all `get_*` and `list_*` methods for the new and existing collections, nothing that writes), make `Store` extend it, and add the write methods for `marketRuns` (`upsert_market_run`, `transition_market_run`), `traceSteps` (`create_trace_step`, `finish_trace_step`), and `traceBlobs` (`create_trace_blob`); add `check_market_transition`. Write rules as in data-model.md: `traceSteps` seal-once, `traceBlobs` create-only.
- [ ] T019 [P] Implement the new methods in `src/hipstraw_mm/store/memory.py`, making the memory half of T007 and T008 pass.
- [ ] T020 [P] Implement the new methods in `src/hipstraw_mm/store/firestore.py` (the seal is a transaction that checks `status == "running"`), making the emulator half of T007 pass with `--emulator`.
- [ ] T021 Add the optional observer to `LLMClient` (`src/hipstraw_mm/adapters/llm.py`, also recording token `usage` in new recordings), `BraveSearch` (`adapters/search.py`), and `Fetcher` (`adapters/fetch.py`), making T009 pass. Feature 002's existing tests must pass without edits.
- [ ] T022 Write `src/hipstraw_mm/market/trace.py` (the `Tracer`: `step(layer, actor, operation, right=None, parent=None)`, the step object's `inputs`, `outputs`, `decision`, `rationale`, `alternatives`, `checks`, `model`, `blob` helpers, `observer` sink, scrub at the single write point, blob truncation, cost from `PipelineSettings`, and the `modelCallsPerRun` ceiling that seals a stage `failed` on exceed), making T005 and T006 pass.
- [ ] T023 Add `tracer: Tracer | None` to `Context` in `src/hipstraw_mm/context.py` and build it in the CLI's real context and in `tests/integration/conftest.py`; add a `market_harness` fixture to `tests/integration/conftest.py` that drives `market` commands through `cli.main` with the memory store and replay adapters, as the feature 002 harness does.
- [ ] T024 Write `src/hipstraw_mm/market/start.py` (Market Manager, right `open_run`) and the `market` command group in `src/hipstraw_mm/cli.py` with `start` and `show` (contracts/cli.md), making T010 and T013 pass.
- [ ] T025 [P] Write `src/hipstraw_mm/viewer/api.py` (shaping functions over `ReadStore`, the `evidenceConfidence` rename), making T011 pass.
- [ ] T026 Write `src/hipstraw_mm/viewer/server.py` (GET and HEAD only, loopback only, accepts only a `ReadStore`, routes from contracts/viewer-api.md for runs, steps, blobs) and the `view` command in `src/hipstraw_mm/cli.py`, making T008 and T012 pass.
- [ ] T027 [P] Write `src/hipstraw_mm/viewer/static/index.html` (plain JavaScript, no build step): the **Runs** list and the **Timeline** grouped by the five layers in `layersOrder`, and the **Step** view showing every FR-023 field (prompt and response loaded from the blob route on demand), with empty states ("No runs yet", "No steps yet"). Polling comes in Phase 7.
- [ ] T028 Check the viewer in a real browser: start the emulator, run `market start`, run `view`, and confirm the run and its `open_run` step show with the right layer, the empty state shows on an empty store, and no control writes anything. Record what was checked in the commit message.
- [ ] T029 Run `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; fix what fails; confirm feature 002's tests are unchanged and green.

**Checkpoint**: the foundation works: a run can be started, its trace is stored and sealed, and the viewer shows it, read-only.

---

## Phase 3: User Story 1 - Vichara and seed graph, fully traced and visible (Priority: P1) 🎯 MVP

**Goal**: ask and answer the 19 dimensions from the objective, record the graph's meaning, and generate a
filtered, capped seed graph, with every question, answer, check, and generation step traced and visible.

**Independent Test**: run `market vichara`, `market meaning`, and `market graph` on the recorded scenario;
every dimension has an answered item or an unresolved marker; the meaning record exists before the graph;
the graph has the six levels with no node outside the filters; the viewer shows each step.

### Tests for User Story 1 (write first; they must fail)

- [ ] T030 [P] [US1] Unit tests in `tests/unit/test_grammar.py` for `src/hipstraw_mm/market/grammar.py` and `config/grammar.yaml`: exactly 19 unique keys, equal to `market_scope, problem, segment_fit, buyer, use_case, value_proposition, demand_signals, adoption_readiness, economics, timing, alternatives, risks, dependencies, evidence_sufficiency, evidence_quality, critical_unknowns, trajectory, transition, market_status`; every `rank` key is in `states`; `decidedBy` is `market_manager`; the file header records the source path, the SHA-256 of the source, and the four replaced dashes; no U+FFFD character anywhere in the file.
- [ ] T031 [P] [US1] Unit tests in `tests/unit/test_schemas_vichara.py` for `DimensionDeliberation`, `CoverageJudgement`, and `DimensionRepair` in `src/hipstraw_mm/market/schemas.py` (contracts/llm-outputs.md §1 to §3): strict (extra fields rejected); 1 to `maxItems` items; `answered` needs `answer` and at least one `basis`; `unresolved` needs `reason` and an empty `basis`; a repair response containing a dimension that was not asked for is rejected; no field named like a person, email, or phone.
- [ ] T032 [P] [US1] Unit tests in `tests/unit/test_vichara_grounding.py`: a `basis` is accepted only if it appears in the objective bundle after `excerpt_check.normalize` (case, dashes, quotes, spacing); a paraphrase fails; an answered item whose basis fails is reported as a failing dimension with the reason `basis_not_in_objective`; zero-information items must be `unresolved` with the reason "no information in the objective"; thin information is accepted as answered.
- [ ] T033 [P] [US1] Unit tests in `tests/unit/test_repair.py` for `bounded_repair(check, repair, limit)` in `src/hipstraw_mm/market/repair.py`, using fake callables: no failing item means zero repair calls; one repair call per attempt covers all failing items together; at most 3 attempts; both checks re-run after each attempt; an attempt that makes the deterministic check fail in a new way counts as a failed attempt; items still failing after the last attempt come back as `UnresolvedItem` with reason `repair exhausted` and nothing is dropped; the limit is read from settings.
- [ ] T034 [P] [US1] Unit tests in `tests/unit/test_graph_meaning.py` for `config/graph_meaning.yaml` and `src/hipstraw_mm/market/meaning.py`: the six level dimensions, `perPathDimensions` (7), `verificationResults` (3), and `managerOnly` (3) name each of the 19 grammar keys exactly once; levels are in the order segment, archetype, problem, trigger, buyerRole, useCase; each level links only to the next; filters `metro_in_force` and `no_enterprise` exist; the step makes no model call and writes the `graphMeanings` record with the file's SHA-256, under layer `market_development_controller` and right `define_graph_meaning`.
- [ ] T035 [P] [US1] Unit tests in `tests/unit/test_graph_filters.py` for the generation helpers in `src/hipstraw_mm/market/graph.py`: a segment node's `metroIds` must be a non-empty subset of the run's metros (a node with `["dallas"]` is removed and listed in `excluded` with `filterId: metro_in_force`); an archetype's `sizeBand` is one of `startup`, `small`, `mid_market`, `enterprise` and `enterprise` is removed (`no_enterprise`); nodes over `nodesPerLevel` and parents over `parentsPerNode` are dropped in the model's order and counted as `over cap`; a `parentLabels` entry matching no previous-level node is rejected; if filtering empties a level it gets an `UnresolvedItem` (`excluded by filter`) and later levels are not generated; node IDs are assigned by the system.
- [ ] T036 [P] [US1] Unit tests in `tests/unit/test_schemas_graph_level.py` for `GraphLevelProposal` (contracts/llm-outputs.md §4): `metroIds` required and non-empty for `segment` and empty otherwise; `sizeBand` required for `archetype` and null otherwise; `sourceItemIds` must name existing vichara item IDs (checked by the system, not the schema).
- [ ] T037 [US1] Extend `tests/fixtures/build_fixtures.py` for the new response kinds used here (`Vichara`, `VicharaCoverage`, `VicharaRepair`, `GraphLevel`) with its usual builder checks (every `basis` marked verbatim is in the objective text and every one marked `verbatim: false` is not; every response validates against its schema; keys unique), then write `tests/fixtures/scenarios/traced_basic.yaml` (fictional objective bundle and six experiment contexts) covering: 19 dimensions with at least 4 unresolved for lack of information; one dimension whose first answer has an ungrounded basis and is fixed by repair attempt 1; one dimension still failing after 3 attempts; graph levels including one segment outside the metros, one `enterprise` archetype, and one over-cap level. Build `tests/fixtures/recorded/traced_basic/`.
- [ ] T038 [US1] Integration test `tests/integration/test_story1_vichara.py` (acceptance scenarios 1 to 5 of story 1): every dimension has an answered grounded item or an unresolved marker with a reason; the coverage check stores both results; repair stops at 3 attempts and the still-failing dimension is recorded as unresolved (`repair exhausted`) and kept; `market meaning` writes its record and the `graphed` stage cannot run before it (exit code 2); the graph has the six levels, excludes the out-of-metro segment and the enterprise archetype with recorded reasons, and every node cites existing vichara item IDs; every question, answer, check, repair attempt, and generation step is its own `traceSteps` record with the layer from contracts/cli.md, and every model call has its prompt and response blobs; a second run of a stage exits with code 2.
- [ ] T039 [P] [US1] Extend `tests/unit/test_viewer_api.py` and `tests/integration/test_viewer_server.py` for `/api/runs/<id>/deliberations`: 19 dimension records with items, `basisCheck`, `coverage`, `repairAttempts`, and unresolved reasons.

### Approval checkpoint

- [ ] T040 [US1] Run T030 to T039, confirm they fail for the intended reason, and present them for **user approval**. Do not start T041 before approval.

### Implementation for User Story 1

- [ ] T041 [P] [US1] Write `scripts/copy_grammar.py` (reads `hipstraw-faculty/seed_data/grammar.json`, replaces each U+FFFD with an en dash and lists the four affected keys, writes `config/grammar.yaml` with the header of contracts/config.md) and run it once. The generated file is committed. Run `python -I` for the script.
- [ ] T042 [US1] Write `src/hipstraw_mm/market/grammar.py` (loader, validation of T030, lookup by key and by `assessedBy`), making T030 pass (needs `config/grammar.yaml` from T041, so not parallel with it).
- [ ] T043 [P] [US1] Add the schemas `DimensionDeliberation`, `CoverageJudgement`, `DimensionRepair`, and `GraphLevelProposal` to `src/hipstraw_mm/market/schemas.py` (every field required, extra fields forbidden, the rules of contracts/llm-outputs.md), making T031 and T036 pass.
- [ ] T044 [P] [US1] Write the prompts `src/hipstraw_mm/prompts/vichara.v1.txt`, `vichara_coverage.v1.txt`, `vichara_repair.v1.txt`, and `graph_level.v1.txt` following the shared rules of contracts/llm-outputs.md (use only the input; no person fields; return only the schema; `basis` copied word for word).
- [ ] T045 [US1] Write `src/hipstraw_mm/market/repair.py` (`bounded_repair`), making T033 pass.
- [ ] T046 [US1] Write `src/hipstraw_mm/market/vichara.py` (Search & Research, right `ask_dimension`): one Worker step per dimension, the grounding check, the deterministic presence check and the model relevance check, repair through `bounded_repair`, `deliberations` records, unresolved items on the run, stage `deliberated`; make T032 pass.
- [ ] T047 [P] [US1] Write `config/graph_meaning.yaml` as in contracts/config.md and `src/hipstraw_mm/market/meaning.py` (Market Development Controller, right `define_graph_meaning`, no model call, stage `defined`), making T034 pass.
- [ ] T048 [US1] Write `src/hipstraw_mm/market/graph.py` (Search & Research, right `build_graph`): six level calls, system-assigned node IDs, mandatory-filter removal before a node exists, caps, unresolved items, `seedGraphs` version 1, stage `graphed`; make T035 and T038 pass. Add `deliberations`, `graphMeanings`, and `seedGraphs` methods to the store (base, memory, firestore) with the write rules of data-model.md and extend T007's contract tests for them.
- [ ] T049 [US1] Add `market vichara`, `market meaning`, and `market graph` to `src/hipstraw_mm/cli.py` (required stage, exit code 2 otherwise).
- [ ] T050 [P] [US1] Add the `/api/runs/<id>/deliberations` route and the **Questions** view (per dimension: question, answer or unresolved reason, basis excerpts, checks, repair attempts, link to the step) in `src/hipstraw_mm/viewer/api.py`, `server.py`, and `static/index.html`, making T039 pass.
- [ ] T051 [US1] Check the viewer in a real browser on the recorded scenario run: timeline grouped by layer, a Worker step's prompt and response, the Questions view, and the unresolved reasons. Record what was checked in the commit message.
- [ ] T052 [US1] Run `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; fix what fails.

**Checkpoint**: story 1 works on its own: vichara, graph meaning, and a generated graph, all traced and visible.

---

## Phase 4: User Story 2 - Graph validation (Priority: P1)

**Goal**: validate the graph deterministically for structure and by judgement for coverage, repair gaps in at
most 3 attempts, and record what stays unresolved.

**Independent Test**: validate graphs with a known orphan, dangling edge, level-order violation, out-of-filter
node, and coverage gap; each is caught with its reason, repair stops at 3 attempts, and an unclosed gap is
recorded as unresolved.

### Tests for User Story 2 (write first; they must fail)

- [ ] T053 [P] [US2] Unit tests in `tests/unit/test_graph_validate.py` for the pure rules in `src/hipstraw_mm/market/validate.py`, one case per rule with a small hand-built graph: orphan node (no edge at all); dangling edge (an endpoint not in the graph); node at an undefined level; edge that skips a level; edge that reverses level order; duplicate node ID; a schema violation (a node whose `level` is not one of the six); node outside a mandatory filter; a level with no nodes and no `UnresolvedItem`; a node with several parents is **not** a violation; each violation names the node or edge and the rule; the same graph gives an identical verdict on 100 repeated calls; the verdict does not depend on node or edge order.
- [ ] T054 [P] [US2] Unit tests in `tests/unit/test_schemas_graph_repair.py` for `GraphCoverage` and `GraphRepair` (contracts/llm-outputs.md §5, §6): strict; each gap names a vichara item ID; `addNodes` use the node shape of §4 plus `level`; `addEdges` use labels; repair is additive: a helper `check_additive(before, after)` fails if any existing node or edge was removed or changed.
- [ ] T055 [US2] Extend `tests/fixtures/build_fixtures.py` and `tests/fixtures/scenarios/traced_basic.yaml` for `GraphCoverage` and `GraphRepair` (one coverage gap closed by attempt 1; one orphan introduced by a repair that counts as a failed attempt; one gap never closed), and add `tests/fixtures/market_states.py` with `seed_run(store, stage)` that stores a run at a stage with a hand-built graph, so later stories can be tested without running the earlier ones. Rebuild `tests/fixtures/recorded/traced_basic/`.
- [ ] T056 [US2] Integration test `tests/integration/test_story2_graph.py` (acceptance scenarios 1 to 4 of story 2): structural violations are reported with node or edge and rule; if any remain after the 3rd repair attempt the run is marked `failed` at the validation stage (status `failed`, `errorStage: validate`) with every remaining violation (node or edge, and rule) in `errorMessage`, and `market links` on a failed run exits with code 2; coverage gaps trigger one batched repair per attempt, at most 3; both validations re-run after each attempt; a repair that introduces an orphan counts as a failed attempt; a gap still open after the last attempt is an `UnresolvedItem` (`repair exhausted`), the graph is still stored, and each repair makes a new `seedGraphs` version that leaves earlier versions unchanged; deterministic and judgement results are both traced with pass or fail and reason.
- [ ] T057 [P] [US2] Extend `tests/unit/test_viewer_api.py` and `tests/integration/test_viewer_server.py` for `/api/runs/<id>/graph?version=<n>`: nodes, edges, `structural`, `coverage`, `unresolved`, `excluded`, `versions`, and the default (latest) version.

### Approval checkpoint

- [ ] T058 [US2] Run T053 to T057, confirm they fail for the intended reason, and present them for **user approval**. Do not start T059 before approval.

### Implementation for User Story 2

- [ ] T059 [P] [US2] Write the structural rules of `src/hipstraw_mm/market/validate.py` as pure functions (no I/O), making T053 pass.
- [ ] T060 [P] [US2] Add the schemas `GraphCoverage` and `GraphRepair` and `check_additive` to `src/hipstraw_mm/market/schemas.py`, and the prompts `graph_coverage.v1.txt` and `graph_repair.v1.txt`, making T054 pass.
- [ ] T061 [US2] Write the validation step in `src/hipstraw_mm/market/validate.py` (Search & Research, right `repair_graph`): run both validations, repair through `bounded_repair`, write each repaired graph as a new `seedGraphs` version, record unresolved items; if structural violations remain after the last attempt mark the run `failed` (`errorStage: validate`, the violations in `errorMessage`) and stop, with every repaired version kept and visible (spec FR-011); otherwise stage `validated`; make T056 pass.
- [ ] T062 [US2] Add `market validate` to `src/hipstraw_mm/cli.py`.
- [ ] T063 [P] [US2] Add the `/api/runs/<id>/graph` route and the **Graph** view (levels as columns, nodes, edges, violations and gaps, repair versions, unresolved and excluded items, each linked to its step) in the viewer, making T057 pass.
- [ ] T064 [US2] Check the Graph view in a real browser on the recorded scenario run (versions, violations, unresolved reasons). Record what was checked in the commit message.
- [ ] T065 [US2] Run `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; fix what fails.

**Checkpoint**: stories 1 and 2 work: a validated graph, repaired within bounds, with every gap recorded.

---

## Phase 5: User Story 3 - Path verification (Priority: P2)

**Goal**: give every link a rationale and a link confidence, check constraints on every path the beam
reaches, assess the seven per-path dimensions, and mark a path real only after a verified company exists
(research R11).

**Independent Test**: on a seeded validated graph, run `market links` and `market assess` with recorded
responses: every link has a rationale and a link confidence, low ones are flagged, a constraint-breaking
path is pruned with its reason, every assessed path has the seven dimensions labelled as hypotheses, and a
path with no verified company is marked "no real-world evidence found".

### Tests for User Story 3 (write first; they must fail)

- [ ] T066 [P] [US3] Unit tests in `tests/unit/test_schemas_links_assess.py` for `LinkVerification` and `PathAssessment` (contracts/llm-outputs.md §7, §9): every input link appears exactly once; `linkConfidence` between 0 and 1; exactly the seven dimension keys, each `state` in that dimension's grammar states; no person fields.
- [ ] T067 [P] [US3] Unit tests in `tests/unit/test_links.py` for `src/hipstraw_mm/market/links.py`: links are chunked at `links.linksPerCall` (12); one call per level pair per chunk; a link below `links.lowConfidenceThreshold` (0.5) is flagged and one at exactly 0.5 is not; a response missing a link or repeating one fails the step with a clear error after one retry; each link record stores `rationale`, `linkConfidence`, `flagged`, `threshold`, and `stepId`.
- [ ] T068 [P] [US3] Unit tests in `tests/unit/test_paths.py` for `src/hipstraw_mm/market/paths.py`: `path_id` is deterministic (the node IDs joined with `>`, hashed to 8 hex characters); `paths_below(graph, node_ids)` counts complete paths under a node set by dynamic programming over edges, tested on a graph with 6 levels of 5 nodes fully linked (15,625 paths) in under 50 ms to show it does not list them; `check_path_constraints(path, graph, constraints)` returns the broken constraint and the node that breaks it (an `enterprise` archetype, a segment outside the metros, a node over the size limits), none for a good path; status rules: `no_evidence_found` only for a final path with no `include`d company in its child run, `has_evidence` only with at least one; `final` never goes back to `kept`; `statusHistory` appends `{status, reason, level, at, stepId}` on each change.
- [ ] T069 [P] [US3] Unit tests in `tests/unit/test_assess.py` for `src/hipstraw_mm/market/assess.py`: the seven keys are `value_proposition`, `demand_signals`, `adoption_readiness`, `economics`, `alternatives`, `risks`, `dependencies`; each result stores `state`, `rationale`, `assessedBy` (from the grammar), and `label: "hypothesis"`; a state not in the grammar's list is rejected; the step runs in layer `position_evaluation` with right `assess_path`.
- [ ] T070 [US3] Extend `tests/fixtures/build_fixtures.py`, `tests/fixtures/market_states.py` (a run seeded at `validated` and at `searched` with hand-set final paths), and `tests/fixtures/scenarios/traced_basic.yaml` for `LinkVerification` (including one chunk boundary and one low link) and `PathAssessment`. Rebuild the recorded scenario.
- [ ] T071 [US3] Integration test `tests/integration/test_story3_links.py` (acceptance scenarios 1 to 4 of story 3): `market links` on the seeded graph gives every edge a `linkChecks` record with a rationale and link confidence and flags the low one; `market assess` on the seeded `searched` run gives each final-level path its seven assessments; a path that breaks a constraint is stored `pruned` with the constraint and node named; no step enumerates all paths (a spy on `paths_below` and the beam input shows the full cross product is never built); stages run in order (exit code 2 otherwise).
- [ ] T072 [P] [US3] Extend `tests/unit/test_viewer_api.py` for `/api/runs/<id>/links` and `/api/runs/<id>/paths` (status, reason, history, `pathsBelow`, `meanLinkConfidence`, `assessments`), keeping `linkConfidence` separate from `searchScore`.

### Approval checkpoint

- [ ] T073 [US3] Run T066 to T072, confirm they fail for the intended reason, and present them for **user approval**. Do not start T074 before approval.

### Implementation for User Story 3

- [ ] T074 [P] [US3] Add the schemas `LinkVerification` and `PathAssessment` to `src/hipstraw_mm/market/schemas.py` and the prompts `link_verification.v1.txt` and `path_assessment.v1.txt`, making T066 pass.
- [ ] T075 [P] [US3] Write `src/hipstraw_mm/market/paths.py` (path ID, `paths_below`, `check_path_constraints`, status transitions with history), making T068 pass. Add `linkChecks` and `paths` methods to the store (base, memory, firestore) with the write rules of data-model.md and extend T007's contract tests for them.
- [ ] T076 [US3] Write `src/hipstraw_mm/market/links.py` (Search & Research, right `verify_link`), stage `linked`, making T067 pass; add `market links` to the CLI.
- [ ] T077 [US3] Write `src/hipstraw_mm/market/assess.py` (Position & Evaluation, right `assess_path`), stage `assessed`, making T069 pass; add `market assess` to the CLI. Make T071 pass.
- [ ] T078 [P] [US3] Add the `/api/runs/<id>/links` and `/api/runs/<id>/paths` routes and a **Links** panel in the Graph view (rationale, link confidence, flag) to the viewer, making T072 pass; check it in a real browser.
- [ ] T079 [US3] Run `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; fix what fails.

**Checkpoint**: link verification and path assessment work on a seeded graph; no step lists all paths.

---

## Phase 6: User Story 4 - Beam search to real companies and buyer roles (Priority: P3)

**Goal**: search the verified graph level by level within a bounded beam, hand the final paths to feature
002's company discovery, find buyer roles, and record decisions and Market Status.

**Independent Test**: on a seeded `linked` run with more candidate paths than the beam width, run `market
beam`, `assess`, `companies`, `buyers`, and `decide` with recorded responses: at most 5 kept per level, no
two kept paths sharing segment and problem, per-factor scores stored apart from every confidence, the final
3 paths searched with at most 5 companies each, buyer roles without any named person, and one decision per
final path with one Market Status.

### Tests for User Story 4 (write first; they must fail)

- [ ] T080 [P] [US4] Unit tests in `tests/unit/test_schemas_beam_buyers.py` for `BeamScoring` and `BuyerRoles` (contracts/llm-outputs.md §8, §10): values between 0 and 1; every candidate once; `authority` is `owns_budget`, `approves`, `uses`, or `influences`; at least one `evidenceId` per role; no person fields.
- [ ] T081 [P] [US4] Unit tests in `tests/unit/test_beam_filter_diversity.py` for `src/hipstraw_mm/market/beam.py`: filtering drops an extension that breaks a mandatory constraint with its reason; diversity keeps at most one path per (segment, problem) pair from the problem level on, walking in score order, and records `duplicateOf` for the one removed; no diversity check runs before the problem level (two paths sharing only a segment are both kept); keep takes the top `beam.width`; ties break by `pathId` so results are reproducible; fewer candidates than the width are all kept (nothing padded); the candidate set at a level never exceeds `width × parentsPerNode × nodesPerLevel`; every candidate ends `kept`, `pruned`, or `deferred` with a reason and `pathsBelow`; when no path survives the beam, `beam` records `finalPathShortfall` `{wanted, found: 0, reason}`, sets no final paths, and the later stages (`companies`, `buyers`, `decide`) still run and write empty results with a Market Status of `blocked`; when fewer than `finalPaths` survive, only those are final and `finalPathShortfall` is recorded.
- [ ] T082 [P] [US4] Unit tests in `tests/unit/test_beam_score.py`: the score is the weighted mean of the four factors with weights normalized (equal by default, and a changed weight changes the result); each factor is stored with its value, rationale, and the weights; `cost` higher means cheaper; the stored record has `searchScore` and `factors` and **no** field named `confidence`, `linkConfidence`, or `evidenceConfidence`; `meanLinkConfidence` is stored beside it and has no effect on the score.
- [ ] T083 [P] [US4] Unit tests in `tests/unit/test_evidence_states.py` for the FR-020 rule tables of research R16, with the settings thresholds: Evidence Sufficiency (`insufficient` with no company with all four proofs; `partial` below half; `sufficient` at half or more; `decision-ready` with all companies and at least `decisionReadyMinCompanies`); Evidence Quality (`contradictory` if any conflict is kept; `weak` below 0.5; `mixed` 0.5 to 0.79; `strong` at 0.8 or more; `high-confidence` only with `strong` and no needs-verification company); Critical Unknowns (`unidentified` with no companies; `open` if any company has an unknown minimum proof; `reduced` if all four proofs exist but other unknowns remain; `resolved` if none); states come from the grammar; the step runs in `position_evaluation` with right `evaluate_evidence`, and each result stores the grammar's `assessedBy` as a field.
- [ ] T084 [P] [US4] Unit tests in `tests/unit/test_decide_rules.py` for the rule tables of research R15: path decision `pursue` (at least one `include`d company and sufficiency at least `sufficient`), `drop` (no verified company and nothing a missing citation could still fill), else `needs more evidence`; Market Status `progressing`, `blocked`, `at-risk`, `awaiting-evidence`, `needs-attention` in that order of the rules; each decision stores `ruleFired`, `reason`, and `right`; Trajectory and Transition are stored as unassessed with the reason "needs a comparison with an earlier run".
- [ ] T085 [P] [US4] Unit tests in `tests/unit/test_buyers.py` for `src/hipstraw_mm/market/buyers.py`: a role is kept only if every cited `evidenceId` is a passing evidence document of that company; otherwise the company gets `unknown: {reason}`; roles never carry a person; calls are batched per path (at most one per final path).
- [ ] T086 [P] [US4] Unit tests in `tests/unit/test_companies_child_runs.py` for `src/hipstraw_mm/market/companies.py` and the small change to `src/hipstraw_mm/steps/position.py`: child run IDs are `<marketRunId>_p1`, `_p2`, `_p3`; a child run gets the position built from the path's labels (segment, archetype, buyer role, problem, trigger), `primaryInterestIds` from the program's interests (at least one), and `companiesKept` 5; the child run's `candidateId` is a synthetic `marketCandidates` document `<marketRunId>__<pathId>` (label from the path, `origin: traced_path`) created by the step; its `parentMarketRunId` and `pathId` are set; a company found on two paths becomes one `marketCompanies` document with both links, and `conflict: true` with both dispositions kept when they differ; feature 002's own tests are unchanged.
- [ ] T087 [US4] Integration test `tests/integration/test_manager_never_traverses.py`: run `market decide` with a store spy; assert no read of `seedGraphs`, `graphMeanings`, `linkChecks`, `beamLevels`, or `deliberations`, and that the step receives a `ManagerView` built only from the final paths, their evaluations, and the run summary (FR-002).
- [ ] T088 [US4] Extend `tests/fixtures/build_fixtures.py` and `tests/fixtures/scenarios/traced_basic.yaml` for `BeamScoring` and `BuyerRoles`, and add the feature 002 company scenarios for the three final paths (reusing `.test` companies and the existing `us1`-style recordings, with child run IDs in the judgement keys); include a company found on two paths. Rebuild the recorded scenario.
- [ ] T089 [US4] Integration test `tests/integration/test_story4_beam_companies.py` (acceptance scenarios 1 to 6 of story 4): at every level at most 5 are kept; no two kept paths share segment and problem; pruned and deferred paths keep status, level, reason, and `pathsBelow`; the top 3 final paths each go to a child run with at most 5 companies, and the rest are `deferred` ("below the final-path limit"); every pruned and deferred path record stores `pathsBelow` (SC-003); `searchScore` and `factors` are stored apart from `linkConfidence` and `evidenceConfidence`; buyer roles are functions with authority and cited evidence, with an explicit unknown where none is cited and no person anywhere; each company has exactly one disposition per child run; a final path with no `include`d company is `no_evidence_found`; the Market Manager records one decision per final path and one Market Status; every step is traced in its layer; the whole run stays within `budgets.modelCallsPerRun`, and a scenario that would exceed it seals the stage `failed` with exit code 4 and keeps `counts.modelCalls` and the partial records (child-run calls count toward the ceiling).
- [ ] T090 [P] [US4] Extend `tests/unit/test_viewer_api.py` and `tests/integration/test_viewer_server.py` for `/api/runs/<id>/beam`, `/companies`, and `/decisions` (contracts/viewer-api.md), including `evidenceConfidence` for companies and the three measures never in one field.

### Approval checkpoint

- [ ] T091 [US4] Run T080 to T090, confirm they fail for the intended reason, and present them for **user approval**. Do not start T092 before approval.

### Implementation for User Story 4

- [ ] T092 [P] [US4] Add the schemas `BeamScoring` and `BuyerRoles` to `src/hipstraw_mm/market/schemas.py` and the prompts `beam_scoring.v1.txt` and `buyer_roles.v1.txt`, making T080 pass.
- [ ] T093 [US4] Write `src/hipstraw_mm/market/beam.py` (Search & Research, rights `prune_path`, `keep_path`, `defer_path`): level-by-level filter, score (one batched model call per level), diversity, keep; `beamLevels` records; final path selection; `paths` statuses; stage `searched`; make T081 and T082 pass. Add `beamLevels` methods to the store (base, memory, firestore) with the create-only rule and extend T007's contract tests; add `market beam` to the CLI.
- [ ] T094 [P] [US4] Write the evidence-state rules in `src/hipstraw_mm/market/companies.py` (pure functions of the child run's records and settings); they are applied in a Position & Evaluation step with right `evaluate_evidence`, and each result stores the grammar's `assessedBy` as a field; making T083 pass.
- [ ] T095 [US4] Add `"traced_path"` to the `origin` Literal of `MarketCandidate` in `src/hipstraw_mm/models.py` (additive; feature 002's tests must pass untouched). Change `src/hipstraw_mm/steps/position.py` to create a run in code from a position, an explicit run ID, and an explicit `candidateId` (no file, no clock-based ID); add the two optional fields `parentMarketRunId` and `pathId` to `Run`. A synthetic candidate is written with the existing `upsert_candidate`, `origin: traced_path`, `experimentContextId` set to the path's `pathId` (the model requires the field; there is no program experiment context for a traced path), and `label` from the path's node labels.
- [ ] T096 [US4] Write `src/hipstraw_mm/market/companies.py`'s step (Search & Research, right `discover_companies`; Review stays in the Market Manager layer with right `record_disposition`): build each final path's position, run feature 002's `discover`, `verify`, and `review` on the child run with `companiesKept` 5, each wrapped in a trace step (discover and verify under Search & Research, review under Market Manager right `record_disposition`) with the adapter observers attached so every child-run search, fetch, and model call is traced and counts toward the ceiling, write `marketCompanies` and the `verification` results per path (R16), set `has_evidence` or `no_evidence_found`, stage `verified`; make T086 pass. Add `marketCompanies` methods to the store and `market companies` to the CLI.
- [ ] T097 [US4] Write `src/hipstraw_mm/market/buyers.py` (Position & Evaluation, right `identify_buyer_roles`), stage `roled`, making T085 pass; add `buyerRoles` store methods and `market buyers` to the CLI.
- [ ] T098 [US4] Write `src/hipstraw_mm/market/decide.py` (Market Manager, rights `decide_path` and `set_market_status`; the `ManagerView`; the rule tables of research R15), stage `decided`, making T084 and T087 pass; add `pathDecisions` store methods and `market decide` to the CLI.
- [ ] T099 [US4] Write `src/hipstraw_mm/market/report.py` (Market Manager) and `market report` and `market run` in the CLI: a markdown summary of the run (final paths with decisions, Market Status, unassessed Trajectory and Transition with the reason, unresolved items, links to each child run's report path), stage `reported`; add its test to `tests/integration/test_story4_beam_companies.py`; make T089 pass.
- [ ] T100 [P] [US4] Add the `/api/runs/<id>/beam`, `/companies`, and `/decisions` routes and the **Beam** (kept and pruned paths per level with reasons and per-factor scores in a "Search score (not evidence)" column), **Companies** (companies with evidence, buyer roles, Review decision, "Evidence confidence"), and **Status** (path decisions and Market Status) views to the viewer, making T090 pass.
- [ ] T101 [US4] Check the Beam, Companies, and Status views in a real browser on the recorded scenario run, including a company on two paths, a path marked "no real-world evidence found", and the separate score and confidence labels. Record what was checked in the commit message.
- [ ] T102 [US4] Run `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; fix what fails.

**Checkpoint**: the whole pipeline runs on recorded scenarios, from objective to decisions.

---

## Phase 7: User Story 5 - Trace viewer, live and complete (Priority: P4)

**Goal**: the viewer follows a run while it executes, every view stays read-only, and the labels never mix
the three measures.

**Independent Test**: start a recorded run with the viewer open: new steps appear within 5 seconds without a
reload, a running step turns into its final state, and no control or route can change data.

### Tests for User Story 5 (write first; they must fail)

- [ ] T103 [P] [US5] Integration tests in `tests/integration/test_story5_viewer.py` (marker `viewer`), acceptance scenarios 1 to 7 of story 5: the runs list and the layer-grouped timeline; every FR-023 field on the step view; graph, beam, companies, and status views return their stored values; a step stored while the server is up is returned by `steps?after=` and a running step is returned in its sealed state by `steps?refresh=`, both within one `viewer.pollSeconds` of being stored (fake clock for the poll interval, real stored records); the static page's script contains the polling calls and the labels "Search score (not evidence)", "Link confidence", and "Evidence confidence" and no `POST`, `PUT`, `PATCH`, or `DELETE` fetch; no API response contains a field that combines a search score with a confidence.
- [ ] T104 [P] [US5] Unit test in `tests/unit/test_viewer_readonly_audit.py`: enumerate every route registered in `server.py` and assert each is read-only: the handler class defines no `do_POST`, `do_PUT`, `do_PATCH`, or `do_DELETE`; the `ReadStore` passed in is the only store reference in `viewer/`; `viewer/` does not import `hipstraw_mm.store.firestore`, `hipstraw_mm.store.memory`, or any `steps` or `market` module other than `models` (an import scan).

### Approval checkpoint

- [ ] T105 [US5] Run T103 and T104, confirm they fail for the intended reason, and present them for **user approval**. Do not start T106 before approval.

### Implementation for User Story 5

- [ ] T106 [US5] Add live polling to `src/hipstraw_mm/viewer/static/index.html`: poll `steps?after=<last seq>` and `steps?refresh=<running seqs>` every `viewer.pollSeconds`; update the timeline, step view, and the Graph, Beam, Companies, and Status views from their routes when a step in their stage is sealed; keep scroll position and the open step; show a visible "disconnected" state when a request fails, and recover on the next success; make T103 pass.
- [ ] T107 [US5] Fix whatever T104 finds (for example a stray import), and keep `viewer/` importing only the `ReadStore` protocol; make T104 pass.
- [ ] T108 [US5] Check live updates in a real browser: open the viewer, start `market run` on the recorded scenario in another terminal, and confirm steps appear within a few seconds, running steps settle, every view fills as its stage completes, and `curl -X POST http://127.0.0.1:8765/api/runs` returns 405. Record what was checked in the commit message.
- [ ] T109 [US5] Run `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; fix what fails.

**Checkpoint**: all five stories work; the viewer is live and read-only.

---

## Phase 8: Polish and cross-cutting

**Purpose**: real recordings, documentation, the whole-run audits, and the live demo.

- [ ] T110 Re-run `tests/integration/test_trace_secrets.py` (T013) over a full `market run` on the recorded scenario, extended to scan the child runs' evidence too, and add a whole-run assertion that every `traceSteps` document is `ok` or `failed` (none `running`) and every FR-023 field is present on all of them (SC-006).
- [ ] T111 [P] Extend `tests/fixtures/record_real.py` with one real recording for each of the nine new schemas (research R19; inputs shaped like the real calls, as T085 prep did for feature 002), and add `tests/contract/test_new_schemas_real.py`: each recording parses with its schema; the test is skipped **with a stated reason** while the recordings are absent, never passed silently.
- [ ] T112 **Needs the user's API keys.** Stop and tell the user when this task is reached: the user runs `tests/fixtures/record_real.py` with real keys to make the nine recordings (one call per schema, one Brave query, one page fetch), then commit them and confirm T111 passes. Do not run any live pipeline.
- [ ] T113 [P] Documentation: add a "Traced market discovery (feature 003)" section to the package README and the docstrings of `market/` and `viewer/` listing the five layers' bounded responsibilities (Constitution I, VI, XIV), and update `specs/003-traced-market-discovery/quickstart.md` with any command or output that differs from what was built.
- [ ] T114 Re-run the Constitution Check of plan.md against the finished code (traces on every step, read-only viewer, layers declared, no exhaustive traversal, three measures never combined, no person fields) and record the result in the plan's Constitution Check table.
- [ ] T115 Run quickstart sections 2 and 5 on the recorded scenario (scenarios 1 to 11) and record the outcomes.
- [ ] T116 **Live demo (needs the user's keys and approval).** After T112, ask the user before any live run; then run quickstart section 4 and compare with the expectations in quickstart section 5. Record the run ID, counts, model calls, time taken, and cost in the commit message (cost only if the prices in `config/pipeline.yaml` were checked).
- [ ] T117 Final `pytest tests -q --emulator`, `ruff check src tests scripts`, and `mypy src`; confirm feature 002's tests are unchanged and green.

---

## Dependencies and execution order

### Phase dependencies

- **Phase 1** has no dependency.
- **Phase 2 (foundation)** depends on Phase 1 and blocks every story.
- **Phase 3 (US1)** depends on Phase 2.
- **Phase 4 (US2)** depends on Phase 3 (it validates the graph US1 generates); its tests can use the seeded
  run builder from T055.
- **Phase 5 (US3)** depends on Phase 4 for the real graph, but its tests run on seeded graphs
  (`seed_run`), so it can be developed in parallel with Phase 4 once T055 exists. Note: `market assess`
  is built here (Phase 5) though the plan's delivery table lists it in increment 4; it is exercised on a
  seeded `searched` run until the beam exists in Phase 6.
- **Phase 6 (US4)** depends on Phase 5 (`paths.py`, links, assess) and on Phase 2; it uses feature 002.
- **Phase 7 (US5)** depends on the views built in Phases 2 to 6.
- **Phase 8** depends on all.

### Within each phase

- Tests, then the approval checkpoint, then code. A checkpoint blocks every task after it in that phase.
- Store methods are added in the story that first needs them, with the contract tests extended in the same
  task (T048, T075, T093, T096, T097, T098).
- Schemas and prompts before the steps that use them; pure functions before the steps that call them.

### Key task dependencies

- T017 before T018; T018 before T019 and T020; T022 needs T015, T016, T018, T021; T024 needs T022, T023;
  T026 needs T018, T025.
- T046 needs T042, T043, T044, T045; T048 needs T043, T047; T061 needs T059, T060.
- T093 needs T075 and T092; T096 needs T095 and T093; T097 and T098 need T096.

### Parallel opportunities

- Phase 2 tests T003 to T013 are all [P] (separate files); implementation T015 and T016, T019 and T020, and
  T025 can run side by side.
- Phase 3 tests T030 to T036 and T039 are [P]; T041 to T044 and T047 are [P].
- Phase 4: T053, T054, T057 [P]; T059 and T060 [P].
- Phase 5: T066 to T069 and T072 [P]; T074 and T075 [P].
- Phase 6: T080 to T086 and T090 [P]; T092 and T094 [P].
- Phase 7: T103 and T104 [P].

## Implementation strategy

### MVP first (User Story 1 with the foundation)

1. Phase 1, then Phase 2 (foundation). Stop and validate: a run starts, its trace is stored, and the viewer
   shows it.
2. Phase 3 (US1). Stop and validate on the recorded scenario: vichara, graph meaning, and a generated
   graph, all traced and visible. This is the smallest demoable result of the feature.

### Incremental delivery

3. Phase 4 (US2): a validated, repaired graph.
4. Phase 5 (US3): links and path assessment.
5. Phase 6 (US4): beam, companies, buyer roles, decisions. This is the first point at which the pipeline
   goes from objective to real companies.
6. Phase 7 (US5): live views and the read-only audits.
7. Phase 8: real recordings (the user's keys), documentation, the whole-run audits, and the live demo.

### Notes

- Do not run any live pipeline before T112 and the user's approval at T116.
- Feature 002's tests must stay green and unedited throughout (T021, T095, and every phase's final task).
- A trace field that would contain a secret is a defect, not a warning: T006 and T013 must always pass.
