# Implementation Plan: Hipstraw G0 Campaign Strategy & Readiness Testing

**Branch**: `004-campaign-readiness-g0` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-campaign-readiness-g0/spec.md`

## Summary

Hipstraw's G0 product tests a launch's campaign strategy and execution readiness against Day Zero.
This plan builds it as a new, self-contained subpackage, `hipstraw_mm.campaign`, with its own
command-line group (`hipstraw-mm campaign ...`), its own SQL store (SQLite from the standard library)
and its own versioned configuration under `config/campaign/`. The repertoire (12 Moves, 5 Lines) is
data. A stage runner executes a human-chosen Line, records every Move and deviation in the tactic
record (C10), and ends in a deterministic Review run. A human reviewer validates the Review; only the
Sponsor's acceptance commits the successor Position. Model calls happen only inside the three E2
Moves, through the existing task router and tracer, reached through a store adapter and a type-only
protocol, so the market discovery pipeline does not change.

## Technical Context

**Language/Version**: Python 3.13 (project supports 3.10+)

**Primary Dependencies**: existing only: pydantic v2 (schemas and config), PyYAML (config), openai SDK
(through the existing `LLMClient`), httpx (through the existing `Fetcher`). New: none; `sqlite3` is in
the standard library.

**Storage**: SQLite file (default `.runs/campaign.db`, overridable with `HIPSTRAW_CAMPAIGN_DB`); tests
use `:memory:` through the same code. Firestore and the market store are untouched.

**Testing**: pytest (unit, integration, contract), ruff, mypy, all as configured in `pyproject.toml`;
model calls replayed or faked; network blocked by pytest-socket as today.

**Target Platform**: developer machines and CI (Windows and Linux); command line.

**Project Type**: library + CLI inside the existing single project.

**Performance Goals**: first proposed Position within 5 minutes of a complete submission (SC-001);
L01 end to end with no model call; L02 under $0.50 in model calls (SC-009).

**Constraints**: no external effects (M10 always fails closed); no score, probability or forecast fields
anywhere (FR-003); every model call traced without secrets (XII); accepted snapshots immutable; commit
only against the pinned base version.

**Scale/Scope**: G0 pilot volumes: tens of launches a month, under 50 evidence records and under 20
findings per Review.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Status |
|---|---|---|
| I Library-first | `hipstraw_mm.campaign` is self-contained: own models, store, config, CLI group and contract docs. It imports only shared adapters and, for E2 Moves, the router and tracer | Pass |
| II CLI | Every capability is a `hipstraw-mm campaign` subcommand with `--json` output and stderr errors (contracts/cli.md) | Pass |
| III Test-first | `tasks.md` puts each unit's tests before its code; user approval of this plan precedes code | Pass (approval pending) |
| IV Integration tests | Store contract, CLI end to end, router and tracer reuse, Line run to accepted Position | Pass |
| V Observability | The JSON event log is reused; every step writes a structured trace | Pass |
| VI Faculty loop | Move outputs are worker output; the Review is the only path to the Position; the commit runs in the `campaign_manager` layer and only after a recorded Sponsor acceptance; M11 Deltas feed the next Review | Pass |
| VII No agent SDK | The stage runner is plain code over a fixed Line; models are called only in E2 Moves with explicit inputs and structured output | Pass |
| VIII Provenance | Evidence records carry source, times, provenance, verification state, uncertainty and hash; contested claims kept side by side; unknowns explicit | Pass |
| IX Real-world integrity | Customer claims start at `reported`; model output is labelled a proposal and cannot raise a claim state | Pass |
| X Smallest units | Eight units, each specified, tested and reviewed before the next (tasks.md) | Pass |
| XI Jev deferred | Not used | Pass |
| XII Traceability | Every Move execution, gate decision, Review step and model call is a trace step with layer, actor, operation, inputs, outputs, decision, right, checks, cost and latency | Pass |
| XIII Read-only viewer and governed console (v2.0.0) | `campaign view` is read-only (read-only SQLite connection, GET and HEAD only). `campaign console` offers only the approved actions (FR-056), each through the CLI's governed operation, with Host, Origin, token and size checks (FR-057) | Pass |
| XIV Layer boundaries | New `config/campaign/layers.yaml`: campaign_manager, readiness_testing, review, authority_gate, workers; each step names its layer | Pass |
| XV Bounded search | No search. M02 reads only addresses named in the mandate | Pass (N/A) |

No violations. Two choices are recorded under Complexity Tracking because they add structure.

## Project Structure

### Documentation (this feature)

```text
specs/004-campaign-readiness-g0/
├── plan.md              # this file
├── research.md          # Phase 0 decisions
├── data-model.md        # Phase 1 records, states and rules
├── quickstart.md        # Phase 1 validation run
├── contracts/
│   ├── cli.md           # command-line contract
│   ├── config.md        # repertoire, criteria, layers, roles and launch file formats
│   └── llm-outputs.md   # structured outputs of the three E2 Moves
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/hipstraw_mm/campaign/
├── __init__.py
├── models.py          # pydantic records: Launch, Mandate, Evidence, Position, Review, Finding, ...
├── repertoire.py      # load Moves, Lines, criteria; Line lint
├── conditions.py      # typed facts from Position + mandate; use-when / exclude-when evaluation
├── store.py           # CampaignStore protocol + SQLite implementation + trace sink adapter
├── intake.py          # launch submission -> mandate, evidence, proposed Position
├── selection.py       # Line recommendation and choice (opens the tactic record)
├── gate.py            # policy and authority gate (C7), role rights
├── runner.py          # stage runner, deviations, end-of-Line Review drafting
├── moves/
│   ├── __init__.py    # handler registry
│   ├── evidence.py    # M01, M02 (read part), M03
│   ├── readiness.py   # M04, M05
│   ├── strategy.py    # M06, M07, M08
│   ├── testing.py     # M09, M10 (always blocked here), M11
│   └── escalation.py  # M12
├── review.py          # Review assembly, review queue actions, acceptance and commit
├── report.py          # markdown report with scope statement
├── measures.py        # G0 -> G1 measures
├── stamp.py           # mechanism stamp (C8)
└── cli.py             # `hipstraw-mm campaign ...` subcommands, wired from hipstraw_mm/cli.py

src/hipstraw_mm/prompts/
├── campaign_source_summary.v1.txt
├── campaign_synthesis.v1.txt
└── campaign_variants.v1.txt

config/campaign/
├── moves.yaml         # M01-M12 (repertoire version campaign-repertoire.v0.1)
├── lines.yaml         # L01-L05 with stages, use-when, exclude-when
├── criteria.yaml      # readiness criteria for M04 and dependency rules for M05
├── layers.yaml        # campaign trace layers, actors, rights
├── roles.yaml         # Sponsor, Campaign Manager, reviewer: which actions each may take
└── settings.yaml      # launch markets, thresholds, scope statement text

tests/
├── unit/test_campaign_*.py          # one file per unit
├── integration/test_campaign_*.py   # store contract, Line run to accepted Position, CLI
└── fixtures/campaign/               # example launch files, metrics CSV, recorded E2 responses

input/campaign/example_launch.yaml   # the quickstart's sample launch
```

**Structure Decision**: one new subpackage inside the existing project, mirroring how `market/` sits
beside the feature 002 steps. Shared code is reused, not copied: `adapters/` (LLM, replay, fetch),
`market/router.py` and `market/trace.py`. Three edits touch shared code: type hints in `model_call` and
`TaskRouter` (see Complexity Tracking); `hipstraw_mm/cli.py`, which registers the `campaign` group and
dispatches it before the market context is built; and an optional `data` field on `CommandResult` for the
extra JSON each campaign command returns (empty by default, so other commands print what they did
before). Without that, every campaign command would open
the market store and need its credentials.

## Post-Design Constitution Check

Re-checked against data-model.md and the contracts:
- **VI**: only `campaign review accept` (Sponsor) leads to a Position commit, performed in the
  `campaign_manager` layer by `position_keeper` with right `commit_position`; Move outputs, including E2
  proposals, reach the Position only through a validated Review. Pass.
- **VIII and IX**: every Position item and finding carries evidence references or is an explicit
  unknown or assumption; E2 outputs are validated against existing evidence IDs and cannot raise a
  claim above `reported`. Pass.
- **XII and XIV**: `config/campaign/layers.yaml` names the layer, actor and right for every step,
  including the authority gate's decisions. Pass.
- **III and X**: tasks.md orders eight units, tests first in each. Code starts after the user approves
  this plan. Pass.

No new violations.

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| A second store (SQLite) beside the Firestore market store | HA asks for one SQL database with conditional commits; Hipstraw G0 is a separate product from market discovery | Reusing the Firestore store would tie G0 records to the market run schema and lacks transactional compare-and-set across records |
| A `ModelContext` protocol in place of `Context` in the type hints of `model_call` and `TaskRouter` | Lets the campaign module call the router without building a market `Context` | Building a fake market `Context` would need a market store and search client the campaign module does not use. The change touches type hints only; behaviour and tests of the market pipeline are unchanged |
