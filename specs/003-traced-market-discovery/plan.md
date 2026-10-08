# Implementation Plan: Traced Market Discovery Pipeline

**Branch**: `003-traced-market-discovery` | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-traced-market-discovery/spec.md`

## Summary

Add a second pipeline to `hipstraw-mm` that starts from the program objective instead of a hand-written
first position, and records every step as a stored trace:

objective → vichara (19 dimensions) → graph meaning → seed graph → validation and repair → link
verification → beam search → path assessment → companies (feature 002, once per final path) → buyer roles
→ path decisions and Market Status → report, with a read-only viewer.

- **Traces** (Constitution XII): one `Tracer` is the only writer of trace records. Each step opens a record
  when it starts, so a running step is visible, and seals it once. Adapters report their tool calls
  through an observer hook. Secrets are scrubbed at that one write point (research R2 to R4).
- **Layers** (XIV): `config/layers.yaml` declares the five layers, their actors, and the rights each may
  use; the Tracer rejects an undeclared combination. The Market Manager steps receive a `ManagerView`
  and cannot read the graph (R15).
- **Graph** (R5 to R10): the grammar's 19 dimensions are copied into the project. Vichara asks one call per
  dimension, grounded by an exact-excerpt check against the objective. The Market Development Controller
  step is deterministic, from `config/graph_meaning.yaml`. The graph is built level by level, filtered
  by structured attributes, validated by pure functions plus one judgement, and repaired at most 3 times.
- **Search** (R11, R12): no step lists all paths (Constitution XV). Links are verified first (bounded by
  caps), the beam keeps at most 5 partial paths per level (filter, score, diversity, keep), and the final
  3 go to company discovery. Search scores, link confidence, and evidence confidence are three separate
  fields everywhere.
- **Companies** (R1, R13): feature 002's `discover`, `verify`, and `review` run unchanged as a child run per
  final path, at most 5 companies each. Buyer roles come from the evidence 002 already stored (R14).
- **Viewer** (R17): a standard-library web server on `127.0.0.1`, built on a read-only store, polling
  every 2 seconds, with GET and HEAD only.
- **State**: the local Firestore emulator (`demo-hipstraw-mvp`), twelve new collections ([data-model.md](data-model.md)).
- **Tests**: hermetic, replaying recorded responses on fictional `.test` companies, as in feature 002.

## Technical Context

**Language/Version**: Python 3.10+ (type-hinted, checked with `mypy`), as feature 002.

**Primary Dependencies**: unchanged: `openai`, `google-cloud-firestore`, `httpx`, `beautifulsoup4`,
`pydantic` v2, `PyYAML`. **No new runtime dependency**: the viewer uses `http.server`, `json`, `threading`
and a static HTML file with plain JavaScript (R17). Dev only: `pytest`, `pytest-socket`, `ruff`, `mypy`,
as before.

**Storage**: Firestore emulator on port 8085, project `demo-hipstraw-mvp`. New collections: `marketRuns`,
`traceSteps`, `traceBlobs`, `deliberations`, `graphMeanings`, `seedGraphs`, `linkChecks`, `paths`,
`beamLevels`, `buyerRoles`, `marketCompanies`, `pathDecisions`. Feature 002's collections are reused.

**Testing**: `pytest` in replay mode with the network blocked; the default suite uses the in-memory store.
Store contract tests for the new collections run on both stores (`--emulator`). Viewer API tests start the
server on an ephemeral localhost port, so the test marker allows `127.0.0.1` sockets only for those tests.
The viewer page is checked in a real browser during implementation (quickstart section 5).

**Target Platform**: Windows developer machines (PowerShell), local only; the viewer is reachable only from
the same machine.

**Project Type**: Single Python library plus command-line tool (Constitution I, II), with a small
embedded viewer.

**Performance Goals**: a full run in about 20 to 30 minutes with about 115 to 125 model calls (R18, ceiling
150); a stored step visible in the viewer within 5 seconds (FR-027, target about 2); the viewer API
answers a typical run's lists (a few hundred steps) in under 500 ms.

**Constraints**:
- Every limit is configuration: beam width, final paths, companies per path, repair limit, caps, factor
  weights, thresholds, call ceiling (`config/pipeline.yaml`).
- Layers, rights, and the graph's meaning are configuration (`layers.yaml`, `graph_meaning.yaml`), not code.
- No agent frameworks; each model call is one strict-schema request with explicit inputs.
- No people or contact data anywhere, including buyer roles.
- Traces hold only what was stored, sent, and received: no model reasoning, no secrets.
- The CLI refuses to run outside a `demo-` emulator project (as 002).

**Scale/Scope**: one program, one run covering all six experiment contexts, one seed graph of at most
6 levels × 5 nodes, 3 final paths, at most 15 companies; a few hundred trace steps per run.

## Constitution Check

*GATE: must pass before Phase 0 research. Re-checked after Phase 1 design.* Checked against Constitution
v1.2.0.

| Principle | Pre-research | Post-design | How the design satisfies it |
|-----------|--------------|-------------|-----------------------------|
| I. Library-First | PASS | PASS | New code is a subpackage of `hipstraw_mm` (`market/`, `viewer/`); the CLI is a thin layer over it. |
| II. CLI Interface | PASS | PASS | Every stage is a `market` subcommand and the viewer is `view`; args in, text or `--json` out, errors on stderr with non-zero codes ([contracts/cli.md](contracts/cli.md)). |
| III. Test-First | PASS* | PASS* | Tests precede code in each increment. *User approval before code: tasks.md must include an approval checkpoint after each increment's tests (as 002's T051). |
| IV. Integration Testing | PASS | PASS | Store contract tests on both stores; one real recording per new schema; replayed full-run and viewer API tests per story (R19). |
| V. Observability | PASS | PASS | The JSON-lines log stays; traces add stored, queryable step records. |
| VI. Faculty Systems | PASS | PASS | Only the Market Manager writes decisions, Market Status, and (through 002's Review) dispositions. Worker and controller output is input to Review (R15). |
| VII. No agent SDK | PASS | PASS | Nine strict-schema single calls ([contracts/llm-outputs.md](contracts/llm-outputs.md)); the control flow is the system's own. "Vichara" is bounded self-questioning, not Jev (spec clarification). |
| VIII. Evidence Provenance | PASS | PASS | Vichara answers carry checked basis excerpts; assessments and scores are labelled hypotheses; three confidence-like measures never merge; conflicting dispositions across paths are kept (R1, R17). |
| IX. Real-World Data Integrity | PASS | PASS | A path counts as real only with a verified company (FR-014); buyer roles cite stored passing evidence; graph content is labelled hypothesis. |
| X. Smallest-Unit Increments | **FLAG** | PASS with plan | The feature is larger than 002. It is delivered in five increments, each with approved tests and a runnable result (R20, Delivery order below). |
| XI. Jev deferred | PASS | PASS | Not used. |
| XII. Traceability | PASS | PASS | Every step records every FR-023 field through one Tracer; prompts and responses are stored blobs; secrets scrubbed at the write point; a planted-secret test (R2 to R4). |
| XIII. Read-Only Viewer | PASS | PASS | The viewer holds a `ReadStore` with no write method and answers GET and HEAD only; a test checks every route and method (R17). |
| XIV. Layer Boundaries | PASS | PASS | `layers.yaml` declares layers, actors, and rights and the Tracer enforces them; the manager gets a `ManagerView`; a spy test proves it reads no graph (R3, R15). |
| XV. Bounded Search | **FLAG** | PASS with plan | The spec says to verify "each full path" before the beam; enumerating them is exhaustive traversal. Resolved in R11: links are verified (bounded), the beam checks only the paths it reaches, and `pathsBelow` is counted over edges. |

There are no unjustified violations, so the gate passes.

## Conflicts and flags

Raised as found; each has the resolution taken in this plan.

1. **Path verification versus bounded search (spec FR-012, FR-013; Constitution XV)**.
   - **Conflict**: the spec verifies every full path before the beam search, but listing every path of a
     seed graph is exhaustive traversal.
   - **Resolution**: verify links, not paths, before the beam; check constraints on each path the beam
     reaches; assess only the paths that finish it (R11). The order of work therefore differs from the
     order of the stories (links first), but every acceptance scenario still holds for the paths that
     matter. Unreached paths are counted (`pathsBelow`), not stored one by one.
2. **Feature size (Constitution X)**.
   - **Conflict**: the request bundles generation, validation, verification, search, buyer roles, and a
     viewer.
   - **Resolution**: five increments (Delivery order), each testable and demoable alone, as the spec's
     stories already require. The user approves each increment's tests before code.
3. **Changes to feature 002**.
   - **Conflict**: spec FR-003 says 002's rules apply unchanged.
   - **Resolution**: its rules are unchanged. Three small code changes only: (a) `position` can create a
     run from a path in code, with an explicit ID (child run IDs would otherwise collide); (b) adapters
     accept an optional observer and the LLM adapter records token `usage` on new recordings; (c) a child
     run gets two optional fields (`parentMarketRunId`, `pathId`). 002's tests must keep passing
     untouched.
4. **Viewer technology**.
   - **Conflict**: "a UI" invites a framework.
   - **Resolution**: standard library plus plain JavaScript, so no dependency is added and read-only is
     provable (R17). The cost is a hand-written page; it stays small because the API does the shaping.
5. **Grammar source**.
   - **Conflict**: the 19 dimensions live in a sibling project, and four entries have a lost dash.
   - **Resolution**: copy into `config/grammar.yaml` with provenance and a list of the four fixes (R5).
6. **Missing reference**.
   - **Conflict**: the spec named `docs/reference/001-seed-graph-spec.md`, which does not exist here.
   - **Resolution**: feature 001's spec was read from the sibling project; the decisions the request
     listed are carried into R6, R7, R9, and R11. A copy under `docs/reference/` is optional and offered
     in the completion report.
7. **Model prices**.
   - **Flag**: `modelPricing` values are placeholders. Cost is recorded as unknown for an unlisted model;
     check the provider's price list before quoting any cost.
8. **Open work outside this plan**.
   - Feature 002's T057 (per-event log lines) is not required by this feature: traces replace what it
     would add for feature 003 runs. Feature 002's own commands run alone are still not traced
     (Constitution XII applies to "every pipeline step"); a follow-up should trace them with the same
     Tracer. At planning time, constitution v1.2.0, feature 002's remade real recordings, and this
     feature's spec folder are uncommitted.
9. **Test-first approval (Constitution III)**: as for 002, `/speckit-tasks` must include an approval
   checkpoint after each increment's tests and before its code.

## Delivery order

| Increment | Stories | Delivers | Runnable result |
|-----------|---------|----------|-----------------|
| 1. Foundation | all (shared) | `layers.yaml`, Tracer, trace collections and store rules, adapter observers, `ReadStore`, viewer shell with Runs and Timeline, `market start` | Open the viewer, start a run, see the `open_run` step |
| 2. Vichara and graph | 1, 2 | grammar copy, vichara and repair, graph meaning, graph generation, validation and repair, Graph view | Scenarios 1 to 4 of the quickstart |
| 3. Links | 3 (part) | link verification and flags, links in the Graph view | Scenario 5 |
| 4. Beam and companies | 3, 4 | beam, path assessment, child-run company discovery, evidence results, buyer roles, decisions, Market Status, Beam, Companies, and Status views | Scenarios 6 to 9 |
| 5. Live views | 5 | live refresh for every view, route and method checks, remaining viewer polish | Scenarios 10 and 11 |

## Project Structure

### Documentation (this feature)

```text
specs/003-traced-market-discovery/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1-R20
├── data-model.md        # Phase 1: collections and records
├── quickstart.md        # Phase 1: run and validation guide
├── contracts/
│   ├── cli.md           # market and view commands, exit codes
│   ├── config.md        # grammar.yaml, layers.yaml, graph_meaning.yaml, pipeline.yaml
│   ├── llm-outputs.md   # the nine model-call schemas
│   └── viewer-api.md    # read-only API, guarantees, separate measures
├── checklists/
│   └── requirements.md  # spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 (/speckit-tasks) - not created here
```

### Source Code (repository root)

```text
config/
├── grammar.yaml                 # NEW: the 19 dimensions (copied, with provenance)
├── layers.yaml                  # NEW: layers, actors, rights
├── graph_meaning.yaml           # NEW: Market Development Controller's definition
├── pipeline.yaml                # NEW: beam, repair, caps, weights, thresholds, budgets, pricing
└── (run.yaml, metros.yaml, source_policy.yaml, programs/)   # unchanged (feature 002)

src/hipstraw_mm/
├── market/                      # NEW: the traced pipeline
│   ├── trace.py                 # Tracer, step context, scrub at write, observers' sink
│   ├── layers.py                # loads layers.yaml, validates (layer, actor, right)
│   ├── grammar.py               # loads and validates grammar.yaml
│   ├── models.py                # Pydantic records for the new collections
│   ├── schemas.py               # the nine model-call schemas
│   ├── repair.py                # bounded_repair(check, repair, limit)
│   ├── start.py                 # market start (Market Manager)
│   ├── vichara.py               # vichara, grounding check, coverage
│   ├── meaning.py               # Market Development Controller
│   ├── graph.py                 # generation, filters, caps
│   ├── validate.py              # structural rules (pure), coverage, repair loop
│   ├── links.py                 # link verification
│   ├── beam.py                  # filter, score, diversity, keep; pathsBelow
│   ├── assess.py                # per-path dimensions (Position & Evaluation)
│   ├── companies.py             # child runs over feature 002; marketCompanies; evidence results
│   ├── buyers.py                # buyer roles from stored evidence
│   ├── decide.py                # ManagerView; path decisions; Market Status
│   └── report.py                # market report
├── viewer/                      # NEW: read-only viewer
│   ├── server.py                # GET/HEAD-only http.server, routes from viewer-api.md
│   ├── api.py                   # shaping functions over ReadStore (renames confidence fields)
│   └── static/index.html        # the page, plain JavaScript
├── prompts/                     # NEW prompt files: vichara, vichara_coverage, vichara_repair, graph_level, graph_coverage, graph_repair, link_verification, beam_scoring, path_assessment, buyer_roles (all .v1.txt)
├── store/
│   ├── base.py                  # CHANGED: ReadStore protocol; new collection methods; seal-once rule
│   ├── memory.py, firestore.py  # CHANGED: implement the new methods
├── adapters/                    # CHANGED (small): optional observer on llm, search, fetch; llm records usage
├── steps/position.py            # CHANGED (small): create a run from a path, explicit run ID
├── cli.py                       # CHANGED: `market` group and `view`
└── models.py                    # CHANGED (small): two optional fields on child runs

scripts/
└── copy_grammar.py              # NEW: one-off copy with provenance and the four dash fixes

tests/
├── unit/                        # NEW: test_layers, test_grammar, test_trace, test_scrub, test_vichara_grounding,
│                                #      test_repair, test_graph_filters, test_graph_validate, test_paths_below,
│                                #      test_beam_filter_diversity, test_beam_score, test_evidence_states,
│                                #      test_decide_rules, test_market_status, test_viewer_api
├── contract/                    # NEW: test_trace_store_contract (both stores), test_read_store, test_new_schemas_real
├── integration/                 # NEW: test_manager_never_traverses, test_trace_secrets, test_story1_vichara,
│                                #      test_story2_graph, test_story3_links, test_story4_beam_companies,
│                                #      test_story5_viewer (routes, methods, live updates)
└── fixtures/
    ├── scenarios/               # NEW: traced_basic.yaml (and variants for failures, filters, ties)
    └── build_fixtures.py        # CHANGED: new response kinds for the nine schemas
```

**Structure Decision**: Single project, as feature 002. New code is in two subpackages so the traced
pipeline and the viewer stay separate from the feature 002 steps, which are reused and not rewritten.
The viewer imports only `ReadStore`, never `Store`, so it cannot write by type as well as by test.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|------|-----------|--------------------------------------|
| Twelve new collections | Records are written by different stages with different rules (create-only, upsert, seal-once); traces and blobs must be separate to stay light to list | One large run document would exceed Firestore's 1 MB limit and could not enforce immutability per record |
| Child runs over feature 002 | Reuses 002's steps and tests unchanged (FR-003) | Threading a path ID through every 002 step and query |
| A hand-written viewer page | Read-only that can be proved, with no new dependency | A framework adds a toolchain and a second runtime; the emulator UI is neither read-only nor layer-grouped |
| Increment-by-increment delivery | Constitution X for a large feature | One undivided build with a single approval point |
