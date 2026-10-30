---
description: "Task list for Hipstraw G0 Campaign Strategy & Readiness Testing"
---

# Tasks: Hipstraw G0 Campaign Strategy & Readiness Testing

**Input**: Design documents from `specs/004-campaign-readiness-g0/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli.md, config.md,
llm-outputs.md), quickstart.md

**Tests**: Required. Constitution III makes test-first non-negotiable: in every phase the test tasks
come first and must fail before the implementation tasks start.

**Organization**: Phases follow the eight units in plan.md (constitution X: each unit is specified,
reviewed, implemented and tested before the next). Each unit is labelled with the user story it
delivers.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story from spec.md (US1–US6)

---

## Phase 1: Setup

**Purpose**: Package, config folder and fixtures in place.

- [X] T001 Create the package skeleton `src/hipstraw_mm/campaign/__init__.py` and `src/hipstraw_mm/campaign/moves/__init__.py` (empty handler registry `HANDLERS: dict[str, Callable]`), and the folders `config/campaign/`, `tests/fixtures/campaign/`, `input/campaign/`
- [X] T002 [P] Write the sample launch `input/campaign/example_launch.yaml` per contracts/config.md "Launch file": market `US`, Day Zero 10 days after 2026-11-01, channels `email` and `paid_social`, no authorized test channels, a landing page URL, email copy and ad copy, no metrics file
- [X] T003 [P] Write test fixtures in `tests/fixtures/campaign/`: `launch_complete.yaml` (as T002), `launch_missing_landing.yaml` (no `landing_page` asset), `launch_bad_market.yaml` (market `DE`), `launch_live.yaml` (Day Zero in the past, `metricsFile: metrics.csv`), `metrics.csv` (one complete row, one row without `definition`)

---

## Phase 2: Foundational (blocks every unit)

**Purpose**: Records, store, campaign config, role checks, mechanism stamp, the type-only router change
and CLI wiring.

### Tests first

- [X] T004 [P] Store contract tests in `tests/integration/test_campaign_store.py`: on `:memory:`, insert and read every record type; updating an immutable record (mandate version, evidence record, accepted Position snapshot, correction, audit event) raises; `commit_position(launch, base_version, successor)` succeeds when the base is the head and refuses (raises `PreconditionError` "stale") when it is not, leaving no partial write; the head is the latest accepted snapshot, else the intake proposal v1
- [X] T005 [P] Trace sink test in `tests/integration/test_campaign_store.py`: a `market.trace.Tracer` built with the campaign store's trace sink and the campaign `LayerConfig` writes a step and a blob, and the run's `lastSeq` and counts advance
- [X] T006 [P] Config tests in `tests/unit/test_campaign_config.py`: `config/campaign/layers.yaml`, `roles.yaml` and `settings.yaml` load; unknown keys are rejected; `settings.launchMarkets == ["US", "IN"]`
- [X] T007 [P] Role-check tests in `tests/unit/test_campaign_gate.py`: `check_role(roles, role, action)` passes for `sponsor/accept_review` and refuses `reviewer/accept_review` with `PreconditionError`; an unknown role is refused
- [X] T008 [P] No-score architecture test in `tests/unit/test_campaign_no_score.py`: walk every pydantic model in `hipstraw_mm.campaign.models` and every schema in `contracts/llm-outputs.md` (once they exist) and fail on any field whose name contains `score`, `probability`, `forecast`, `likelihood` or `successRate` (FR-003, research R11)
- [X] T009 [P] CLI wiring test in `tests/unit/test_campaign_cli_wiring.py`: `main(["campaign", "--db", ":memory:", "lint"])` runs without calling the market `context_factory` (pass a factory that raises)

### Implementation

- [X] T010 Records in `src/hipstraw_mm/campaign/models.py` per data-model.md: `Launch`, `Mandate` (with `Product`, `Audience`, `Objective`, `Strategy`, `Budget`, `Asset` where `kind` is one of `landing_page`, `ad_copy`, `email_copy`, `creative`, `brief`, `other`), `EvidenceRecord` (`verificationState` one of `unverified`, `reported`, `observed`, `verified`, `stale`; `accessClass` `D2` or `D3`), `PositionItem` (kinds and states exactly as the data-model table), `PositionSnapshot` (`state` one of `proposed`, `accepted`, `superseded`), `LineRun` (`state` one of `opened`, `staged`, `completed`, `abandoned`), `MoveExecution` (`status` one of `succeeded`, `failed`, `blocked`), `Deviation` (`type` one of `skipped`, `added`, `reordered`, `stopped`), `ReviewRun` (`state` one of `requested`, `gathering`, `drafted`, `validated`, `accepted`, `rejected`, `failed`), `Finding` (`reviewState` one of `pending`, `accepted`, `rejected`, `corrected`), `Correction`, `AuditEvent`, `TestPlan` (`state` `draft` only reachable), `EvidenceRequest`, `Escalation`, `Delta` (`causal: Literal[False]`), `ReportRecord`, `MechanismStamp`; all `extra="forbid"`
- [X] T011 SQLite store in `src/hipstraw_mm/campaign/store.py`: `CampaignStore` protocol and `SqliteCampaignStore(path)` with per-entity tables (JSON document plus indexed key columns), insert-only enforcement for immutable records, `head_position(launch)`, `commit_position(...)` in one transaction (research R1), `append_audit(...)`, and `trace_sink()` exposing `get_market_run`, `upsert_market_run`, `create_trace_step`, `finish_trace_step`, `create_trace_blob` over `trace_runs`, `trace_steps`, `trace_blobs` (research R3); default path `$HIPSTRAW_CAMPAIGN_DB` else `.runs/campaign.db`
- [X] T012 [P] Campaign config files `config/campaign/layers.yaml`, `config/campaign/roles.yaml`, `config/campaign/settings.yaml` per contracts/config.md (scope statement verbatim from HA section 1)
- [X] T013 Config loaders in `src/hipstraw_mm/campaign/config.py`: `load_campaign_layers()` (returns `market.layers.LayerConfig`), `load_roles()`, `load_settings()`
- [X] T014 Role check in `src/hipstraw_mm/campaign/gate.py`: `check_role(roles, role, action)` raising `PreconditionError`; every refusal and pass is written as an audit event by the caller
- [X] T015 [P] Mechanism stamp in `src/hipstraw_mm/campaign/stamp.py`: `mechanism_stamp(repertoire_version, criteria_version, prompt_versions, models, router_version)` adding `codeVersion` (package version) and `gitCommit` when `git rev-parse HEAD` succeeds (research R13)
- [X] T016 Type-only change: add `ModelContext` protocol (attributes `llm: LLMClient`, `open_llm: LLMClient | None`) in `src/hipstraw_mm/market/router.py` and use it for the `ctx` type of `TaskRouter.__init__` and `model_call` in `src/hipstraw_mm/market/stages.py`; run the full existing test suite to confirm no behaviour change
- [X] T017 CLI wiring: `src/hipstraw_mm/campaign/cli.py` with `register(subparsers)` and `dispatch(args) -> CommandResult`; in `src/hipstraw_mm/cli.py` register the `campaign` group with `--db`, and in `main` dispatch `campaign` before the market context is built

**Checkpoint**: T004–T009 pass; `ruff check src tests` and `mypy src` clean; the full existing suite still passes.

---

## Phase 3: Unit 1 — Repertoire and Line lint [US2, part 1]

**Goal**: Moves and Lines as versioned config that cannot load if they break the lint (FR-015 to FR-019).

**Independent Test**: `hipstraw-mm campaign lint` passes on the shipped config and fails, naming the problem, on each broken copy.

### Tests first

- [X] T018 [P] [US2] Repertoire tests in `tests/unit/test_campaign_repertoire.py`: the shipped config loads 12 Moves (M01–M12) and 5 Lines (L01–L05) with the stages of HA section 5; M10 has effect class `E3` and `requiresApproval: test_plan`; M02 has `[E1, E2]`
- [X] T019 [P] [US2] Line lint tests in `tests/unit/test_campaign_lint.py`, one per rule in contracts/config.md: unknown Move ID; missing `version`; unknown handler; E3 Move with no earlier `producesTestPlan` Move; E3 Move without `requiresApproval`; E2 Move with a transition into `observed` or `verified`; unknown fact or operator; duplicate IDs. Each error names the Line or Move
- [X] T020 [P] [US2] CLI test in `tests/integration/test_campaign_cli.py`: `campaign lint --json` returns `repertoireVersion`, 12 Moves, 5 Lines, no errors; with a `--config-dir` copy holding `M99` it exits 1 and the message names `L0x` and `M99`

### Implementation

- [X] T021 [P] [US2] Write `config/campaign/moves.yaml` (M01–M12, `version: campaign-repertoire.v0.1`) and `config/campaign/lines.yaml` (L01–L05 with the use-when and exclude-when of contracts/config.md)
- [X] T022 [US2] Conditions model and validation in `src/hipstraw_mm/campaign/conditions.py`: `Check {fact, op, value}`, `Condition {all | any}`, the fact and operator lists of contracts/config.md (evaluation comes in Unit 3)
- [X] T023 [US2] Repertoire loader and lint in `src/hipstraw_mm/campaign/repertoire.py`: `MoveDef`, `LineDef`, `Repertoire`, `load_repertoire(config_dir)` raising `ConfigError` with every lint error; the handler check reads `moves.HANDLERS` names (register placeholder names for M01–M12 that raise `NotImplementedError` until their unit lands)
- [X] T024 [US2] `campaign lint` command in `src/hipstraw_mm/campaign/cli.py`

**Checkpoint**: Unit 1 reviewed with the user before Unit 2 (constitution X).

---

## Phase 4: Unit 2 — Launch intake [US1]

**Goal**: A launch file becomes a mandate, evidence records and a proposed Position v1 (FR-005 to FR-014).

**Independent Test**: `campaign submit` on the fixtures, then read back the records.

### Tests first

- [X] T025 [P] [US1] Intake tests in `tests/unit/test_campaign_intake.py`: complete launch → mandate v1, one `reported` evidence record per asset with `contentHash`, Position v1 `proposed` with claims (each citing evidence), the core assumptions from `settings.coreAssumptions` (one channel assumption per channel), and no unknowns; missing landing page → unknown `U..` "landing page not provided" and no landing-page claim; market `DE` → `UsageError` naming `US, IN`; metrics row without `definition` → evidence `unverified` with the reason
- [X] T026 [P] [US1] Amend test in `tests/unit/test_campaign_intake.py`: amending creates mandate v2, keeps v1 unchanged, adds evidence only for new or changed assets, and leaves the Position untouched
- [X] T027 [P] [US1] Trace and audit test in `tests/integration/test_campaign_intake_flow.py`: submit writes trace steps `campaign_manager/launch_desk/open_launch` and `campaign_manager/launch_desk/propose_position` with inputs and outputs, and audit events `submit_launch` with actor and role
- [X] T028 [P] [US1] CLI test in `tests/integration/test_campaign_cli.py`: `campaign submit --file ... --by ... --as sponsor --json` and `campaign show --launch ...`; `--as reviewer` is refused with exit 2

### Implementation

- [X] T029 [US1] Launch file schema and metrics CSV parser in `src/hipstraw_mm/campaign/intake.py` (`LaunchFile`, `parse_metrics_csv`), paths relative to the launch file
- [X] T030 [US1] `submit_launch(...)` and `amend_mandate(...)` in `src/hipstraw_mm/campaign/intake.py`: market check (FR-006), mandate version, evidence records (FR-008, FR-009), Position v1 items (claims no higher than `reported`, FR-012; unknowns for missing required inputs, FR-010), mechanism stamp, trace steps and audit events
- [X] T031 [US1] `campaign submit`, `campaign amend` and `campaign show` in `src/hipstraw_mm/campaign/cli.py`

**Checkpoint**: Unit 2 reviewed before Unit 3.

---

## Phase 5: Unit 3 — Line recommendation, choice and tactic record [US2, part 2]

**Goal**: Eligible and excluded Lines with reasons; a human choice opens the tactic record (FR-020 to FR-023).

**Independent Test**: recommendations for prepared Positions match the expected eligible and excluded sets.

### Tests first

- [X] T032 [P] [US2] Facts and evaluation tests in `tests/unit/test_campaign_conditions.py`: facts for the complete fixture on 2026-11-01 (`daysToDayZero 10`, `isLive false`, `unverifiedCoreAssumptions >= 3`, `authorizedTestChannel false`); `all` and `any`; every check yields a reason string
- [X] T033 [P] [US2] Recommendation tests in `tests/unit/test_campaign_selection.py`: complete launch → L01 and L02 eligible, L03 excluded (no authorized test channel), L04 excluded (not live); live fixture with metrics → L04 eligible, L01 excluded; a contested claim → L05 eligible
- [X] T034 [P] [US2] Choice tests in `tests/unit/test_campaign_selection.py`: choosing records Line ID and version, repertoire version, chooser, role, reason, time, the recommendation snapshot and the base Position version; choosing an excluded Line is refused; choosing a Line whose Move handler is withdrawn is refused (edge case)

### Implementation

- [X] T035 [US2] `compute_facts(mandate, position, today)` and `evaluate(condition, facts)` in `src/hipstraw_mm/campaign/conditions.py`
- [X] T036 [US2] `recommend_lines(...)` and `choose_line(...)` in `src/hipstraw_mm/campaign/selection.py` (trace `campaign_manager/line_selector/recommend_lines` and `choose_line`; audit `choose_line`)
- [X] T037 [US2] `campaign lines` and `campaign choose` in `src/hipstraw_mm/campaign/cli.py`

**Checkpoint**: Unit 3 reviewed before Unit 4.

---

## Phase 6: Unit 4 — Stage runner, E0/E1 Moves and the authority gate [US3, part 1]

**Goal**: Run a Line stage by stage with deviations; every Move passes the gate; M10 always blocked (FR-024 to FR-032, FR-034 to FR-037).

**Independent Test**: L01 runs end to end with no model call; a skip is recorded; M10 is blocked.

### Tests first

- [X] T038 [P] [US3] Gate tests in `tests/unit/test_campaign_gate.py`: E0 allowed; E1 allowed only for a URL named in the mandate; E2 allowed only with a `promptVersion`; E3 always refused in this feature with reason "no approved Test Plan"; each decision is a trace step `authority_gate/authority_gate/check_authority`
- [X] T039 [P] [US3] Readiness Move tests in `tests/unit/test_campaign_moves_readiness.py`: M04 opens a blocker per failed criterion in `criteria.yaml` and clears it when met; M05 opens `DZ02` for an asset whose `readyDate` is later than Day Zero minus `leadDays`; both deterministic
- [X] T040 [P] [US3] Evidence and testing Move tests in `tests/unit/test_campaign_moves_evidence.py`: M01 records any asset not yet captured; M02's read part fetches only mandate URLs through a fake fetcher and records an unreachable page as an unknown with the reason; M03 marks complete rows `observed` and rows without definition or capture time `stale`; M08 sets an assumption to `awaiting_evidence` and stores an `EvidenceRequest`; M09 drafts a `TestPlan` in `draft` and moves the hypothesis to `planned`; M10 returns `blocked`; M11 stores a `Delta` with `causal: false`; M12 stores an `Escalation` for open blockers and contested findings
- [X] T041 [P] [US3] Runner tests in `tests/unit/test_campaign_runner.py`: L01 order M01 → (M04, M05 reading the same stage-start state) → M12; `step` runs one stage; `deviate --skip` before a stage removes the Move and records the deviation; `deviate --add` inserts an approved Move; `stop` marks the run `abandoned`; the tactic record lists every execution in order; a Move that raises is recorded `failed` and the stage still completes
- [X] T042 [P] [US3] Readiness criteria config test in `tests/unit/test_campaign_moves_readiness.py`: `config/campaign/criteria.yaml` loads, version `readiness-criteria.v0.1`, every `check` name exists

### Implementation

- [X] T043 [P] [US3] `config/campaign/criteria.yaml` per contracts/config.md and research R10
- [X] T044 [US3] Effect-class gate `check_move(move, mandate, approvals)` in `src/hipstraw_mm/campaign/gate.py` (fails closed, traced)
- [X] T045 [P] [US3] M04 and M05 handlers in `src/hipstraw_mm/campaign/moves/readiness.py`
- [X] T046 [P] [US3] M01, M02 (read part only) and M03 handlers in `src/hipstraw_mm/campaign/moves/evidence.py`, using `adapters.fetch.Fetcher` through a `fetch_worker` trace step for M02
- [X] T047 [P] [US3] M08 in `src/hipstraw_mm/campaign/moves/strategy.py`; M09, M10 (always `blocked`) and M11 in `src/hipstraw_mm/campaign/moves/testing.py`; M12 in `src/hipstraw_mm/campaign/moves/escalation.py`; register all in `moves/__init__.py`
- [X] T048 [US3] Stage runner in `src/hipstraw_mm/campaign/runner.py`: `step`, `run_all`, `deviate`, `stop`; Move outputs merge after the stage; each Move is a trace step `readiness_testing/move_runner/run_move`; executions and deviations stored; audit for every deviation (research R5, R6)
- [X] T049 [US3] `campaign step`, `campaign run`, `campaign deviate` and `campaign stop` in `src/hipstraw_mm/campaign/cli.py` (Review drafting is stubbed to a `requested` Review until Unit 6)

**Checkpoint**: Unit 4 reviewed before Unit 5.

---

## Phase 7: Unit 5 — E2 Moves through the task router [US3, part 2]

**Goal**: M02's summary, M06 and M07 call the model only through the router, with validated, structured, traced output that cannot raise a claim (FR-029, FR-033, FR-044).

**Independent Test**: L02 runs with recorded model responses; outputs are proposals with evidence references; no claim goes above `reported`.

### Tests first

- [X] T050 [P] [US3] Output schema tests in `tests/unit/test_campaign_llm_outputs.py`: `SourceSummary`, `Synthesis`, `Variants` per contracts/llm-outputs.md reject unknown keys and any claim state other than `reported` or `contested`; the no-score test (T008) covers them
- [X] T051 [P] [US3] Validator tests in `tests/unit/test_campaign_llm_outputs.py`: a quote not in the page text fails; an evidence ID not in the launch fails; `contested` without an existing `contradictsItemIds` fails; more than `maxVariants` fails
- [X] T052 [P] [US3] E2 Move tests in `tests/unit/test_campaign_moves_strategy.py` with a fake `LLMClient`: M06 and M07 call `TaskRouter.call` with tasks `campaign_synthesis.v1` and `campaign_variants.v1`, store proposals with evidence references, change no item state, and create `proposed` hypotheses from variants; a failed validation leaves the Move with no proposals and a recorded check
- [X] T053 [US3] Traced model-call test in `tests/integration/test_campaign_line_run.py`: an L02 run on recorded responses writes `workers/llm_worker/call_model` steps with prompt and response blobs, cost and latency, and no secret

### Implementation

- [X] T054 [P] [US3] Prompts `src/hipstraw_mm/prompts/campaign_source_summary.v1.txt`, `campaign_synthesis.v1.txt`, `campaign_variants.v1.txt`
- [X] T055 [US3] Output models and validators in `src/hipstraw_mm/campaign/llm_outputs.py`
- [X] T056 [US3] M02 summary part, M06 and M07 in `src/hipstraw_mm/campaign/moves/evidence.py` and `moves/strategy.py`, calling `TaskRouter(ctx, tracer, load_routing(), run_id=launchId).call(...)` with the validators (research R8)
- [ ] T057 [US3] Record replay fixtures for L02 in `tests/fixtures/campaign/recorded/` with a small live run (`HIPSTRAW_REPLAY=record`, under $0.50) and commit them

**Checkpoint**: Unit 5 reviewed before Unit 6.

---

## Phase 8: Unit 6 — Review run, review queue, acceptance and audit [US3 end, US4]

**Goal**: Every Line ends in a deterministic Review; the reviewer validates; only the Sponsor's acceptance commits the successor Position (FR-026, FR-038 to FR-043).

**Independent Test**: correct one finding, reject one, validate, accept, and read back the corrections, audit events and Position v2; a stale commit is refused.

### Tests first

- [X] T058 [P] [US3] Review assembly tests in `tests/unit/test_campaign_review.py`: after L01, findings come from open blockers (readiness), M12 escalations, and unknowns; after L02, proposals are marked `isProposal`; each finding has an area, evidence references or item references, and an uncertainty note; the Review pins the base version and evidence cutoff, carries the scope statement and a mechanism stamp, and is `drafted`; a stopped Line also drafts a Review
- [X] T059 [P] [US4] Queue tests in `tests/unit/test_campaign_review.py`: `correct` keeps the original, the new text and the reason; `reject` drops the finding from the successor; `validate` is refused while any finding is `pending`; `accept` before `validate` is refused; `accept` by `reviewer` is refused
- [X] T060 [P] [US4] Commit tests in `tests/integration/test_campaign_line_run.py`: accept → Position v2 `accepted`, v1 `superseded`, both readable; a second Review pinned to v1 → refused as stale with exit 2; every action wrote an audit event with actor, role, right, before and after references and reason
- [X] T061 [P] [US4] CLI tests in `tests/integration/test_campaign_cli.py` for `review show`, `review finding`, `review validate`, `review accept` and `review reject`

### Implementation

- [X] T062 [US3] Review assembly in `src/hipstraw_mm/campaign/review.py` (research R9), called by the runner when a Line completes or stops (replace the Unit 4 stub in `runner.py`); trace `review/review_assembler/draft_review`
- [X] T063 [US4] Queue actions and acceptance in `src/hipstraw_mm/campaign/review.py`: `review_finding`, `validate`, `accept` (role check, then commit in the `campaign_manager` layer by `position_keeper` with right `commit_position`), `reject`; audit events for each
- [X] T064 [US4] `campaign review ...` subcommands in `src/hipstraw_mm/campaign/cli.py`

**Checkpoint**: Unit 6 reviewed before Unit 7.

---

### Added 2026-10-29 (spec Session 2026-10-29)

- [X] T056a [US3] Campaign rubric `config/campaign/rubric.yaml` and loader `src/hipstraw_mm/campaign/rubric.py`; M06 judges every question with quotes, downgrades unverifiable quotes to unknown, drops repeats of assumptions and unknowns already held
- [X] T056b [US4] Reviewer can correct a rubric verdict (`--verdict`); corrections record the old and new verdict
- [X] T056c Demo scenario `input/campaign/kozmo_invoice_alpha_us.yaml` and guide `docs/demo_g0_campaign_readiness.md`
- [ ] T057 (deferred) M02 summary step (`campaign_source_summary.v1`); M06 judges pages directly for now

## Phase 9: Unit 7 — Report [US5]

**Goal**: A report only from an accepted Position, with the scope statement and citations, no score (FR-046).

### Tests first

- [X] T065 [P] [US5] Report tests in `tests/unit/test_campaign_report.py`: refused when no snapshot is accepted; opens with the scope statement; sections in order (strategy findings, readiness findings, blockers and what clears them, open assumptions, unknowns, Line used and deviations, evidence index); every finding cites an evidence ID or is labelled assumption or unknown; the text contains none of `score`, `probability`, `forecast`, `likelihood`, `/10`
- [X] T066 [P] [US5] CLI test in `tests/integration/test_campaign_cli.py`: `campaign report --launch ... --out ... --json` returns `reportId`, `path`, `sha256` and stores a `ReportRecord`

### Implementation

- [X] T067 [US5] Markdown renderer in `src/hipstraw_mm/campaign/report.py`
- [X] T068 [US5] `campaign report` in `src/hipstraw_mm/campaign/cli.py`

**Checkpoint**: Unit 7 reviewed before Unit 8.

---

## Phase 10: Unit 8 — G0 → G1 measures [US6]

**Goal**: Measures from stored records alone, each traceable to the records it counted (FR-047).

### Tests first

- [ ] T069 [P] [US6] Measures tests in `tests/unit/test_campaign_measures.py`: with two launches (one L01 run skipping M05 in each, one Review corrected and accepted, one rejected): Reviews completed 2; correction rate and rejection rate as counted; deviations at L01 stage 2 = 2 `skipped` with reasons; blockers before versus after Day Zero; cost and elapsed time per Review from trace steps; every measure lists its record IDs; the period filter excludes records outside `[from, to)`

### Implementation

- [ ] T070 [US6] `compute_measures(store, from, to)` in `src/hipstraw_mm/campaign/measures.py`
- [ ] T071 [US6] `campaign measures` in `src/hipstraw_mm/campaign/cli.py`

---

## Phase 11: Polish & Cross-Cutting

- [ ] T072 [P] Quickstart end-to-end test in `tests/integration/test_campaign_quickstart.py` running quickstart.md steps 1–8 on `:memory:` with replayed model calls
- [ ] T073 [P] Tactic-record completeness check in `tests/integration/test_campaign_quickstart.py`: every `run_move` trace step maps to a `MoveExecution`, and every deviation command to a `Deviation` (SC-004)
- [ ] T074 [P] Docs: add a "Hipstraw G0 campaign testing" section to `docs/agent_design_patterns.md` (layers, roles, how a Line runs without a compiler) and a pointer in `docs/handoff_task_router.md`
- [ ] T075 Full checks: `python -m pytest tests -q`, `ruff check src tests`, `mypy src`; then run quickstart.md manually against a file database

### Added 2026-10-30 (demo request)

- [x] T076 Tests first: `tests/unit/test_campaign_viewer.py` (rubric with corrections, Position history and changes, tactic record, trace, no score field, database unchanged by reads, read-only connection refuses writes) and `tests/integration/test_campaign_viewer_server.py` (routes, 404s, GET/HEAD only, Host check, loopback only)
- [x] T077 Read-only campaign page: `SqliteCampaignStore.read_only`, `CampaignView` and `CampaignHandler` in `src/hipstraw_mm/campaign/viewer.py` on the market `ViewerServer` (new `handler` parameter), page `src/hipstraw_mm/viewer/static/campaign.html`, command `campaign view [--port 8766]`

### Added 2026-10-30 (spec Session 2026-10-30: channel by channel)

- [x] T078 Tests first: `tests/unit/test_campaign_channels.py` (standards file and sources, each check, levels raised past the bulk-sender size, US-only and India-only rules, both scenarios, channel-first intake, a vague channel as an unknown, M13 items and checklist, `should` misses as Review fixes); per-channel judgements in `tests/unit/test_campaign_rubric.py`, `test_campaign_moves_strategy.py`, `tests/integration/test_campaign_line_run.py`; per-channel report sections in `test_campaign_report.py`; channels, desk and earlier-rubric display in `test_campaign_viewer.py`
- [x] T079 Channel-first launch file: `channels` with audience, budget, success measure, setup and assets (structured `fields`); `ChannelPlan` on the mandate; channel on Position items and findings; intake unknowns for a vague channel or one with no audience (`src/hipstraw_mm/campaign/intake.py`, `models.py`)
- [x] T080 Channel standards `config/campaign/channels.yaml` (email, LinkedIn ads, Instagram ads, Reddit ads; reach, format, setup, checks with level and source) and their checks in `src/hipstraw_mm/campaign/channels.py`
- [x] T081 M13 Check channel standards (`readiness.channel_standards`), L01 v2 `[[M01], [M04, M05, M13], [M12]]`, repertoire v0.2, criteria v0.2 (asset per platform); Day Zero blockers carry their channel
- [x] T082 Rubric v0.2 (`scope: channel | campaign`), M06 v2 judging per channel (`campaign_synthesis.v2`, `Judgement.channel`, coverage per question and channel) with each channel's reach notes, the landing page, and what readers see before the channel cuts the text off
- [x] T083 Report channel by channel with a side-by-side table and each channel's rules with sources (`report.py`)
- [x] T084 Page: Report, Campaign and Reviewer desk views plus Audit (`viewer.py`, `campaign.html`); findings keep the question title they were judged under
- [x] T085 Scenarios `input/campaign/kozmo_email_us.yaml` and `kozmo_three_channels_us.yaml`; `docs/campaign_channel_scenarios.md` (practice, sources, open questions); demo guide updated

### Added 2026-10-30 (constitution v2.0.0: the governed console)

- [x] T086 Constitution XIII amended to v2.0.0 (read-only viewer and governed console) in `.specify/memory/constitution.md`
- [x] T087 Tests first: `tests/unit/test_campaign_console.py` (approved actions only, form submission equals file submission, gate refusals audited, reviewer and Sponsor decisions, request checks) and `tests/integration/test_campaign_console_server.py` (session, token, Origin, Host, content type, size, 403/404/409, PUT/PATCH/DELETE refused, standards and examples)
- [x] T088 `submit_launch_data` beside `submit_launch` in `src/hipstraw_mm/campaign/intake.py`; `CampaignConsole`, `CampaignConsoleHandler` and `ConsoleServer` in `src/hipstraw_mm/campaign/console.py`; command `campaign console [--port 8766]`; `/api/session` and `/api/standards` on the page
- [x] T089 Page: "Acting as" (name and role), the new-launch form, decision buttons on the Reviewer desk, the Sponsor's decision on the Campaign view; checked end to end in headless Chrome

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** → Units 1 to 8 in order (Phases 3–10) → **Polish (Phase 11)**.
- Each unit needs the one before it: intake needs the repertoire to stamp versions; recommendation needs
  a Position; the runner needs a chosen Line; E2 Moves need the runner; Review needs Move outputs;
  the report needs an accepted Position; measures need Reviews and tactic records.
- Within a unit: tests first (they must fail), then config, then code, then CLI.
- The user reviews each unit at its checkpoint before the next starts (constitution X).

## Parallel Opportunities

- Phase 2: T004–T009 (tests) together; then T012 and T015 beside T010–T011.
- Unit 1: T018, T019, T020 together; T021 beside T022.
- Unit 4: T038–T042 together; T045, T046, T047 together after T044.
- Unit 5: T050–T052 together; T054 beside T055.
- Unit 6: T058–T061 together.

## Implementation Strategy

- **MVP**: Setup, Foundational, Units 1–4 and Unit 6. That is L01 Readiness-first end to end, with no
  model, through the review queue to an accepted Position, and covers US1–US4 for readiness. Demo it
  with quickstart steps 1–4 and 6.
- **Then**: Unit 5 (strategy Lines with the model), Unit 7 (report, which is what the customer
  receives), Unit 8 (gate evidence).
- **Not in this feature**: viewer page, E3 approval and dispatch, scheduled checkpoints, the compiler.
