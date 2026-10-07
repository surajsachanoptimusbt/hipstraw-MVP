# Implementation Plan: Find and Review Target Companies for a Micro-Market

**Branch**: `002-objective-to-target-companies` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-objective-to-target-companies/spec.md`

## Summary

Build a Python library and command-line tool, `hipstraw-mm`, that runs one thin slice for the Kozmo
Invoice Alpha Genesis Cohort:

intake → candidate micro-markets → first position → company discovery → verification → Market
Manager Review → markdown demo report.

- **Candidates**: the program's six experiment contexts, copied, not generated.
- **First position**: written by hand.
- **Discovery**: bounded Brave searches whose results the system controls (research R18):
  - a result that is itself a company homepage becomes a candidate directly;
  - on listing pages, only links to other domains count as company websites, with one budgeted hop
    from a directory profile page to the company's site;
  - companies on official registry pages with no website are kept as registry-only records.
- **Verification**:
  - checks that each company's own website loads, and cites its homepage for the company name;
  - sends registry-only companies to needs verification;
  - extracts claims with verbatim excerpts through strict-schema OpenAI calls;
  - keeps a claim only if its excerpt matches the fetched text exactly; otherwise the claim becomes an
    unknown.
- **Review**: its own step. A deterministic rule gate runs first; a bounded judgement call can then
  only keep or downgrade a disposition. Only Review writes dispositions, and it freezes an immutable
  baseline of the first position.
- **State**: kept in the local Firestore emulator (`demo-hipstraw-mvp`).
- **Tests**: hermetic, replaying recorded responses. Synthetic `.test` scenarios cover behavior, and
  one real recording per adapter (Brave, page fetch with `robots.txt`, OpenAI per schema) backs the
  adapter contract tests.
- **Documentation**: a package README and an `__init__` docstring state the library's purpose and the
  Market Manager's bounded responsibility.

## Technical Context

**Language/Version**: Python 3.10+ (type-hinted, checked with `mypy`)

**Primary Dependencies**:

| Package | Use |
|---------|-----|
| `openai` | Structured Outputs only; no agents |
| `google-cloud-firestore` | State storage |
| `httpx` | Search API calls and page fetches |
| `beautifulsoup4` | HTML to text, with the built-in `html.parser` |
| `pydantic` v2 | Model schemas and config validation |
| `PyYAML` | Config files |

Dev only: `pytest`, `pytest-socket`, `ruff`, `mypy`. See [research.md](research.md) R1–R3, R12, and
R17.

**Storage**: Firestore emulator on port 8085, project `demo-hipstraw-mvp`. Collections: `programs`,
`marketCandidates`, `runs`, `companyRecords`, `evidence`, `reviewDecisions`, `positionBaselines`,
`demoReports` ([data-model.md](data-model.md)).

**Testing**: `pytest` in replay mode with the network blocked. The default suite uses an in-memory
store. Store contract tests also run against the emulator with `--emulator` (research R11).

**Target Platform**: Windows developer machines (PowerShell), running locally.

**Project Type**: Single Python library plus command-line tool.

**Performance Goals**: One run completes in under 20 minutes, using about 45 model calls and at most
about 110 page fetches (research R13).

**Constraints**:
- Every limit is a configuration value: the cap of 10 companies, the search and fetch budgets, the
  size thresholds, and the metros.
- Robots rules and the terms denylist are enforced on every fetch.
- No agent frameworks.
- No people or contact data.
- The CLI refuses to run outside a `demo-` emulator project.

**Scale/Scope**: One program, six candidates, one first position, at most 10 companies per run.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Checked against Constitution v1.1.0.

| Principle | Pre-research | Post-design | How the design satisfies it |
|-----------|--------------|-------------|-----------------------------|
| I. Library-First | PASS | PASS | All logic lives in the `hipstraw_mm` package. The CLI is a thin layer over it. A package README and `__init__` docstring document the purpose. |
| II. CLI Interface | PASS | PASS | Every step is a CLI command with args in and a human or `--json` summary out. Error messages always go to stderr with non-zero exit codes ([contracts/cli.md](contracts/cli.md)). |
| III. Test-First | PASS* | PASS* | Recorded-response tests are written before each step's code. *The constitution also requires user approval before code, so tasks.md must include an approval checkpoint before implementation. |
| IV. Integration Testing | PASS | PASS | Store contract tests run on both stores. Adapter contract tests replay one real recording per external service (Brave, page fetch with `robots.txt`, OpenAI per schema). Full-run replay tests cover the step boundaries. |
| V. Observability | PASS | PASS | JSON-lines logs per run and step (research R14). |
| VI. Faculty Systems | PASS | PASS | The README and `__init__` docstring declare the Market Manager's bounded responsibility. Discovery and verification write findings only (`companyRecords.status = finding`). Only Review writes `reviewDecisions` and the baseline, the first Position. |
| VII. No agent SDK | **FLAG** | PASS | Two risks were found and avoided: the provider's built-in web search (R2) and V0's Agents-SDK code (R1). Each model call is a single strict-schema request. |
| VIII. Evidence Provenance | PASS | PASS | Each evidence document records the URL, fetch time, publish date (or null), reliability, excerpt, and content hash. Conflicts are kept, and unknowns are explicit. |
| IX. Real-World Data Integrity | PASS | PASS | Company origin must be a retrieved page, the website must load, and existence needs a homepage citation containing the name. Test fixtures use `.test` domains. The program YAML must be checked against its source page (R15). |
| X. Smallest-Unit Increments | **FLAG** | PASS | The requested slice includes a "candidate micro-markets" step. It is reduced to copying the six contexts, with no generation (R16). See Conflicts. |
| XI. Jev deferred | PASS | PASS | Not used. |

There are no unjustified violations, so the gate passes.

## Conflicts and flags

Raised as requested; each comes with the resolution taken in this plan.

1. **Candidate step and the slice (spec FR-019, Constitution X)**.
   - **Conflict**: The planning input's slice includes "candidate micro-markets", but the spec moves
     generating and selecting candidates to feature 003.
   - **Resolution**: The `candidates` step only copies the program's six experiment contexts into
     `marketCandidates`. There is no model call and no seed graph. If you meant generated candidates,
     that is feature 003 and would break FR-019 and Principle X.
2. **Built-in web search (Constitution VII; spec FR-006, FR-003)**.
   - **Conflict**: The planning input allows the model provider's built-in web search. With it, the
     model would choose the queries and the number of searches, and could mix companies from its own
     memory with real search results.
   - **Resolution**: Use the Brave Search API, which the team already has a key for, called by the
     system (R2).
3. **V0 code uses the OpenAI Agents SDK (Constitution VII)**.
   - **Conflict**: `Hipstraw Market Discovery Sub Agent V0/backend/app/agents/` imports `agents`.
   - **Resolution**: Reuse only V0's plain OpenAI client and Brave search patterns, never its agents
     module.
4. **Existence check: website only (spec FR-008)**. *Resolved 2026-10-07.*
   - **Conflict**: The spec allowed "website loads, or registry entry found". The planning input
     requires a website fetch for every company.
   - **Resolution**: FR-008 was amended. The company's own website must load, and a registry-only
     company is dispositioned needs verification. The spec, contracts, and data model now agree.
5. **Added `runs` collection (planning input)**.
   - **Conflict**: The planning input listed seven purposes and no `runs` collection.
   - **Resolution**: `runs` was added to hold per-run state (constraints in force, step status,
     counts) shared between the separate steps.
6. **Test-first approval (Constitution III)**.
   - **Conflict**: The constitution requires user approval before code.
   - **Resolution**: `/speckit-tasks` must include an approval checkpoint after the test tasks and
     before the implementation tasks.

## Project Structure

### Documentation (this feature)

```text
specs/002-objective-to-target-companies/
├── plan.md              # This file
├── research.md          # Phase 0 decisions R1–R18
├── data-model.md        # Firestore collections, validation, state transitions
├── quickstart.md        # Setup, hermetic tests, live run, validation scenarios
├── contracts/
│   ├── cli.md           # hipstraw-mm commands, exit codes, --json shape
│   ├── llm-outputs.md   # The five structured model calls, discovery rules, identifier check
│   ├── config.md        # Program, run, metros, source policy, first-position files
│   └── demo-report.md   # Markdown report sections
├── checklists/requirements.md
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root)

```text
README.md                       # Purpose, Market Manager's bounded responsibility, how to run
pyproject.toml                  # hatchling build; console script hipstraw-mm
requirements.lock               # uv pip compile output
requirements-dev.lock
firebase.json                   # Firestore emulator 8085, UI 4005
config/
├── programs/invoice_alpha.yaml
├── run.yaml
├── metros.yaml
└── source_policy.yaml
positions/
└── first_position.example.yaml
src/hipstraw_mm/
├── __init__.py                 # Docstring: purpose and bounded responsibility
├── cli.py                      # Argument parsing, exit codes, --json output
├── config.py                   # Pydantic config models and loading
├── models.py                   # Domain models (records, evidence, decisions)
├── llm_schemas.py              # The five structured-output schemas
├── prompts/                    # Versioned prompt templates
├── logging_setup.py            # JSON-lines logging
├── store/
│   ├── base.py                 # Store protocol (no update method for baselines and decisions)
│   ├── memory.py               # In-memory store for tests
│   └── firestore.py            # Emulator-only store with the demo- guard
├── adapters/
│   ├── llm.py                  # OpenAI Structured Outputs client
│   ├── search.py               # Brave Search client
│   ├── fetch.py                # Robots- and denylist-aware fetcher, HTML to text
│   └── replay.py               # Record and replay wrapper for all three
├── evidence/
│   ├── excerpt_check.py        # Exact normalized match and value-in-excerpt check
│   ├── location.py             # Headquarters to CSA matching
│   ├── size.py                 # Thresholds, ranges, conflicts, parent
│   └── confidence.py           # Reliability and confidence bands
└── steps/
    ├── intake.py
    ├── candidates.py
    ├── position.py
    ├── discover.py
    ├── verify.py
    ├── review.py               # Rule gate and judgement; writes decisions and the baseline
    └── report.py
reports/                        # Generated demo reports (git-ignored)
tests/
├── unit/                       # Excerpt check, location, size, confidence, rule gate
├── contract/                   # Store contract (memory and --emulator), adapter contracts (real recordings)
├── integration/                # Full-run replay, only-Review-writes-decisions, no-source-not-included
└── fixtures/
    ├── record_real.py          # One-off script: records one real response per adapter (needs keys)
    ├── build_fixtures.py       # Builds synthetic scenarios into recorded files
    ├── scenarios/              # Synthetic .test scenario definitions
    └── recorded/
        ├── real/               # Real adapter recordings, secrets redacted (committed)
        └── <scenario>/         # Synthetic replay files for fictional .test companies
```

**Structure Decision**: A single Python project with one library package and one console script.
This is a single-team MVP, and there is no UI or web service (spec FR-019). Steps are modules inside
the library, so each one can be tested alone with the in-memory store and recorded responses.

## Complexity Tracking

No constitution violations need justifying. Two pieces of structure exist only to meet stated
requirements:

| Structure | Needed for | Simpler alternative rejected because |
|-----------|------------|--------------------------------------|
| Store protocol with memory and Firestore versions | Hermetic tests with no emulator by default (planning input) | Testing only against the emulator would need Java and Node running for every test |
| Adapter-level record and replay | Hermetic tests with recorded responses (planning input) | HTTP-level cassettes are tied to SDK internals and break when the SDK changes |
