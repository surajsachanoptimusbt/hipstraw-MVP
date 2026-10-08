# Quickstart: Traced Market Discovery Pipeline

A run and validation guide for [spec.md](spec.md). It assumes feature 002 is set up (virtual environment,
dependencies, Firestore emulator). Commands are PowerShell, from the repository root. Details are in
[contracts/cli.md](contracts/cli.md), [contracts/config.md](contracts/config.md), and
[contracts/viewer-api.md](contracts/viewer-api.md).

## 1. Prerequisites

```powershell
# Terminal 1: the emulator (as for feature 002)
firebase emulators:start --only firestore --project demo-hipstraw-mvp

# Terminal 2: environment
$env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8085"
.venv\Scripts\Activate.ps1
```

No new packages are needed: the viewer uses the Python standard library.

## 2. Hermetic tests (no network, no keys)

```powershell
pytest tests -q                      # unit, integration, viewer API, replayed scenarios
pytest tests -q --emulator           # also the store contract tests against the emulator
```

Expect all tests to pass. The two adversarial checks to look at first:
- `tests/integration/test_manager_never_traverses.py`: the Market Manager steps read no graph, node, edge,
  or beam document (FR-002).
- `tests/integration/test_trace_secrets.py`: a planted fake key never appears in any stored trace
  (FR-024, SC-006).

## 3. Open the viewer first (it works on an empty store)

```powershell
hipstraw-mm view            # http://127.0.0.1:8765
```

Open the address in a browser. Expect "No runs yet". Leave it open; it refreshes itself every 2 seconds.

## 4. Run the pipeline on the Invoice Alpha program (live; needs keys)

```powershell
$env:OPENAI_API_KEY = "..."; $env:LLM_MODEL = "..."; $env:BRAVE_API_KEY = "..."
hipstraw-mm intake --program invoice_alpha
hipstraw-mm market run --program invoice_alpha        # or run the stages one at a time:
# hipstraw-mm market start --program invoice_alpha    # prints the marketRunId
# hipstraw-mm market vichara --run <id>
# hipstraw-mm market meaning --run <id>
# hipstraw-mm market graph --run <id>
# hipstraw-mm market validate --run <id>
# hipstraw-mm market links --run <id>
# hipstraw-mm market beam --run <id>
# hipstraw-mm market assess --run <id>
# hipstraw-mm market companies --run <id>
# hipstraw-mm market buyers --run <id>
# hipstraw-mm market decide --run <id>
# hipstraw-mm market report --run <id>
```

A full run takes about 20 to 30 minutes and about 115 to 125 model calls (research R18). Do not run live
before the place lists and recordings of feature 002 are in place (they are, as of its T052 and T085).

## 5. Validation scenarios

Each scenario names the story and acceptance scenario it proves. Use the viewer for the "see" steps.

| # | Story | What to do | Expected |
|---|-------|-----------|----------|
| 1 | 1 | After `market vichara`, open **Timeline** | A step per dimension (19), each with its question, answer or unresolved reason, and its model prompt and response. Dimensions with no information show "no information in the objective". |
| 2 | 1 | Open **Step** for the coverage check | A deterministic presence check and a model relevance check, each pass or fail with a reason; repair attempts (at most 3) listed. |
| 3 | 1 | After `market meaning`, open the step | The six levels, relationships, mandatory filters, and "what a promising path is", recorded before `graph` ran. |
| 4 | 1, 2 | After `market graph` and `market validate`, open **Graph** | Nodes at six levels; validation results (structural and coverage); a repaired version if any; any unresolved item with its reason; no enterprise archetype and no segment outside the three metros. |
| 5 | 3 | After `market links`, open **Graph** → links | Every link with a rationale and a link confidence; low ones flagged. |
| 6 | 4 | After `market beam`, open **Beam** | Per level: kept and pruned paths with reasons, per-factor scores and the weights, "Search score (not evidence)" shown apart from "Link confidence"; at most 5 kept per level; no two kept paths sharing segment and problem. |
| 7 | 4 | After `market companies`, open **Companies** | For each of 3 final paths up to 5 companies, with evidence and Review decision; a path with no verified company marked "no real-world evidence found". |
| 8 | 4 | After `market buyers`, open **Companies** | Buyer roles as function and authority with cited evidence, or an explicit unknown; no person's name anywhere. |
| 9 | 4 | After `market decide`, open **Status** | One decision per final path with reason and right; one Market Status; Trajectory and Transition shown as unassessed with their reason. |
| 10 | 5 | Start `market run` while the viewer is open | Each new step appears within a few seconds without reloading; a running step turns into its final state. |
| 11 | 5 | Try to change anything in the viewer; send a non-GET request | There is no control that writes; `curl -X POST http://127.0.0.1:8765/api/runs` returns 405. |

## 6. Checks on the stored data

```powershell
hipstraw-mm market show --run <id>      # stage, counts, final paths with decisions, Market Status
```

Spot checks (details in [data-model.md](data-model.md)):
- every `traceSteps` document is `ok` or `failed` after the run ends (none left `running`);
- no stored trace or blob contains a value of `OPENAI_API_KEY` or `BRAVE_API_KEY`;
- every `paths` document of status `no_evidence_found` has no `include`d company in its child run;
- `marketRuns.counts.modelCalls` is at most `budgets.modelCallsPerRun` (150).

## 7. Recording the real model responses (team member with keys)

The nine new schemas each need one real recording for the adapter contract tests (Constitution IV), made
the same way as feature 002's (`tests/fixtures/record_real.py`, extended in the tasks). Until they exist,
the contract tests for the new schemas are skipped with a stated reason, not silently passed.
