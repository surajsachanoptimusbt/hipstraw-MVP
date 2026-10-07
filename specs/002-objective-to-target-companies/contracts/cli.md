# Contract: `hipstraw-mm` command line

The library `hipstraw_mm` exposes every step through one console script (Constitution II). Each step
is a separate command, so Review can only run as its own step.

## Global behavior

| Item | Contract |
|------|----------|
| Preconditions | `FIRESTORE_EMULATOR_HOST` must be set, and the project ID (from `HIPSTRAW_PROJECT_ID`, default `demo-hipstraw-mvp`) must start with `demo-`. Otherwise the command exits with code 2 before doing anything. |
| Config | `--config-dir PATH` (default `./config`). All files are validated before the step runs (contracts/config.md). |
| Output | A human-readable summary on stdout. `--json` prints one JSON object on stdout instead. |
| Logs | JSON lines on stderr and in `.runs/<runId>/run.log` (research R14). |
| Errors | Error messages always go to stderr, in both human and `--json` mode, with a non-zero exit code (Constitution II). In `--json` mode the stdout object also carries the `error` field described below. |
| Secrets | Read only from the environment (`OPENAI_API_KEY`, `BRAVE_API_KEY`, `LLM_MODEL`). Never printed or logged. |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Usage or config validation error |
| 2 | Precondition failed: emulator not set, non-demo project, or the run is not at the required status |
| 3 | External service error after the configured retries (search, fetch, model) |
| 4 | Budget exhausted: the `verify` step ran out of its run-level fetch or model-call budget (`verifyFetchesPerRun`, `verifyModelCallsPerRun`) while companies were still unverified. The run is marked `failed`, with the partial counts recorded. Reaching any discovery limit (queries, results, listing pages, hops, companies kept) is normal completion, not an error. |

## Commands

| Command | Requires | Does | Writes |
|---------|----------|------|--------|
| `intake [--program invoice_alpha]` | none | Loads `config/programs/<id>.yaml` | `programs/{programId}` (upsert) |
| `candidates --program ID` | program exists | Copies the six experiment contexts. No generation. | `marketCandidates/*` (upsert) |
| `position --candidate ID --file PATH` | candidate exists | Validates the first-position YAML and freezes constraints and budgets from config | `runs/{runId}` with status `created`. Prints the `runId`. |
| `discover --run ID` | status `created` | Runs bounded searches and applies the discovery rules (direct homepages, listing pages, one profile hop, registry-only), keeping at most 10 companies (contracts/llm-outputs.md) | origin `evidence`, partial `companyRecords`, status `discovered` |
| `verify --run ID` | status `discovered` | Checks that each company's own website loads (FR-008), builds the existence evidence, extracts claims with excerpts, runs the citation checks (FR-007), computes confidence | `evidence`, completed `companyRecords`, status `verified` |
| `review --run ID` | status `verified` | Market Manager: rule gate, then the bounded judgement call | `reviewDecisions/*`, `positionBaselines/{runId}`, status `reviewed` |
| `report --run ID [--out DIR]` | status `reviewed` | Renders the markdown demo report (contracts/demo-report.md) | `reports/<runId>.md` (default), `demoReports/{runId}`, status `reported` |
| `run --candidate ID --file PATH` | program and candidates exist | Runs `position`, `discover`, `verify`, `review`, `report` in order, stopping at the first failure | Everything above |
| `show --run ID` | run exists | Prints run status, counts, and dispositions | Nothing |

Notes:
- `discover` and `verify` never write `reviewDecisions`, and they never set any field that means
  "included". Only `review` writes dispositions (FR-011, FR-012).
- `review` refuses to run twice on the same run (exit code 2), because decisions and the baseline are
  immutable.

## `--json` output shape (every command)

```json
{
  "command": "review",
  "runId": "run_20261007T101500",
  "status": "reviewed",
  "counts": {"returned": 9, "included": 4, "excluded": 2, "needsVerification": 3, "shortfall": 1},
  "warnings": ["shortfall: 9 of 10 companies found"]
}
```

Fields that don't apply to a command are omitted. On failure, the object includes `"error": {"code":
<exit code>, "message": "..."}`.
