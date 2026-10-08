# Contract: `hipstraw-mm market` and `hipstraw-mm view`

Feature 003 adds one command group and one viewer command to the console script of feature 002
(Constitution II). Global behavior, `--config-dir`, `--json`, logs, secrets, and exit codes 0 to 4 are
as in [feature 002's CLI contract](../../002-objective-to-target-companies/contracts/cli.md), with these
differences:

| Code | Meaning in feature 003 |
|------|------------------------|
| 2 | Also: the run is not at the stage the command needs, or the viewer port is in use |
| 4 | Budget exhausted: the run's `modelCallsPerRun` ceiling was reached, or a child run's verify budget ran out while companies were unverified. The stage is marked `failed`; partial counts and traces are kept. |

Every `market` command writes its trace steps (data-model.md). Each command is one stage; a stage cannot
run twice on the same run (exit code 2), because the records it writes are create-only.

## Commands

| Command | Requires status | Does | Writes | Layer of the main step |
|---------|-----------------|------|--------|------------------------|
| `market start --program ID` | program loaded (`intake`) | Opens a run over the whole program: the objective bundle (objective, six experiment contexts, constraints), frozen pipeline settings. Prints `marketRunId`. | `marketRuns` (`opened`) | Market Manager |
| `market vichara --run ID` | `opened` | Asks and answers the questions for all 19 dimensions, runs the coverage check with bounded repair (max 3) | `deliberations`, unresolved items → `deliberated` | Search & Research |
| `market meaning --run ID` | `deliberated` | Records the graph's meaning from `config/graph_meaning.yaml` | `graphMeanings` → `defined` | Market Development Controller |
| `market graph --run ID` | `defined` | Generates the seed graph level by level, applying mandatory filters and caps | `seedGraphs` v1 → `graphed` | Search & Research |
| `market validate --run ID` | `graphed` | Structural and coverage validation with bounded repair (max 3) | `seedGraphs` v2+, unresolved items → `validated` | Search & Research |
| `market links --run ID` | `validated` | Gives every link a rationale and a link confidence; flags low ones | `linkChecks` → `linked` | Search & Research |
| `market beam --run ID` | `linked` | Level-by-level beam search: filter, score, diversity, keep top N; picks the final paths | `paths`, `beamLevels` → `searched` | Search & Research |
| `market assess --run ID` | `searched` | Assesses the seven per-path dimensions for the paths that finished the beam | `paths.assessments` → `assessed` | Position & Evaluation |
| `market companies --run ID` | `assessed` | For each final path, runs feature 002's `discover`, `verify`, `review` as a child run; links companies; records evidence results | child `runs` and their records, `marketCompanies`, `paths.verification` → `verified` | Search & Research (Review: Market Manager) |
| `market buyers --run ID` | `verified` | Identifies buyer roles for each kept company from stored evidence | `buyerRoles` → `roled` | Position & Evaluation |
| `market decide --run ID` | `roled` | Market Manager: one decision per final path, then the run's Market Status | `pathDecisions`, `marketRuns.marketStatus` → `decided` | Market Manager |
| `market report --run ID [--out DIR]` | `decided` | Renders a markdown summary of the run (paths, decisions, status, links to each child run's 002 report) | `reports/<marketRunId>.md` → `reported` | Market Manager |
| `market run --program ID` | program loaded | Runs `start` through `report` in order, stopping at the first failure | everything above | n/a |
| `market show --run ID` | run exists | Prints stage, counts, final paths with decisions, and Market Status | nothing | n/a |
| `view [--port 8765]` | emulator set | Starts the read-only viewer on `127.0.0.1` (contracts/viewer-api.md). Runs until interrupted. | **nothing** | n/a |

Notes:
- `buyers` writes only buyer roles; `decide` is the only command that writes path decisions or the
  Market Status (Constitution VI). Company dispositions are still written only by feature 002's `review`.
- `market companies` is the only command that calls feature 002's steps; each child run keeps 002's own
  status machine. Child reports are not written unless `--child-reports` is given.
- `view` never writes. It refuses to start if the store object it receives has any write method
  (research R17).

## `--json` output shape

```json
{
  "command": "market beam",
  "runId": "mrun_20261008T101500",
  "status": "searched",
  "counts": {"levels": 6, "kept": 5, "pruned": 41, "deferred": 12, "final": 3},
  "warnings": []
}
```

As in feature 002: fields that do not apply are omitted; on failure the object also carries
`"error": {"code": N, "message": "..."}`, and the message goes to stderr.
