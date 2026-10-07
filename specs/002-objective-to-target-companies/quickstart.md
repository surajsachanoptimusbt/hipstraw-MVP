# Quickstart: Find and Review Target Companies for a Micro-Market

A run and validation guide for feature 002 on Windows (PowerShell). Commands and file formats are
defined in [contracts/cli.md](contracts/cli.md) and [contracts/config.md](contracts/config.md).

## Prerequisites

The prerequisites are the same as in the `hipstraw-faculty` project.

| Tool | Check | Notes |
|------|-------|-------|
| Python 3.10+ | `python --version` | |
| Node.js LTS | `node -v` | For the Firebase CLI |
| Java JDK 21 | `java -version` | The Firestore emulator needs it |
| Firebase CLI | `firebase --version` | `npm install -g firebase-tools`. No login is needed, because this is a `demo-` project. |

For live runs only, you also need `OPENAI_API_KEY`, `LLM_MODEL`, and `BRAVE_API_KEY`.

## 1. Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.lock
pip install -e .
```

## 2. Hermetic tests (no network, no keys, no emulator)

```powershell
pytest
```

**Expected**: everything passes with sockets blocked. The model, search, and fetch calls replay from
`tests/fixtures/recorded/`.

Key tests, each mapped to the spec:

| Test | Proves |
|------|--------|
| `test_review_rejects_company_without_verifiable_source` | A company whose identifier fails, or whose citations all fail, is never `include` (FR-013, FR-016; planning input) |
| `test_excerpt_must_match_exactly` | A paraphrased excerpt fails, and the claim becomes an unknown (FR-007) |
| `test_no_interest_signal_means_needs_verification` | FR-016, FR-020 |
| `test_size_conflict_is_preserved_and_not_included` | FR-010, FR-015, FR-016 |
| `test_only_review_writes_dispositions` | `discover` and `verify` cannot write `reviewDecisions` (FR-011) |
| `test_baseline_is_immutable` | A second write to `positionBaselines/{runId}` fails (FR-021) |
| `test_full_run_replay` | End to end from intake to the report, using recorded responses for fictional `.test` companies |
| `tests/contract/test_adapters_real.py` | The Brave, fetch (with `robots.txt`), and OpenAI adapters parse real recorded responses (Constitution IV) |

### Recording the real adapter responses (once, by a team member with keys)

```powershell
$env:OPENAI_API_KEY="..."; $env:LLM_MODEL="..."; $env:BRAVE_API_KEY="..."
$env:HIPSTRAW_REPLAY="record"
python tests\fixtures\record_real.py
```

**Expected**: files appear under `tests/fixtures/recorded/real/`, with secrets shown as
`[redacted]`. The script fails if any key value appears in a file. Commit the files. Every later
`pytest` run replays them with the network blocked.

## 3. Store contract tests against the emulator (optional)

Terminal 1:

```powershell
firebase emulators:start --only firestore --project demo-hipstraw-mvp
```

This uses ports 8085 and 4005 from `firebase.json`.

Terminal 2:

```powershell
$env:FIRESTORE_EMULATOR_HOST="127.0.0.1:8085"
pytest --emulator tests/contract
```

**Expected**: the same store contract tests pass against both the in-memory store and the emulator.

## 4. Live demo run

You need the emulator running, the keys set, and `$env:FIRESTORE_EMULATOR_HOST="127.0.0.1:8085"`.

```powershell
hipstraw-mm intake --program invoice_alpha
hipstraw-mm candidates --program invoice_alpha_genesis
copy positions\first_position.example.yaml positions\first_position.yaml   # then edit by hand
hipstraw-mm run --candidate invoice_alpha_genesis__saas_recurring_fees --file positions\first_position.yaml
hipstraw-mm show --run <runId>
```

**Expected**:
- `reports/<runId>.md` exists, with the sections listed in [contracts/demo-report.md](contracts/demo-report.md).
- In the Emulator UI (http://127.0.0.1:4005/firestore), you can see `runs`, `companyRecords`,
  `evidence`, `reviewDecisions`, `positionBaselines`, and `demoReports` for the run.
- `show` reports at most 10 returned companies, and every one has a disposition.

## 5. Validation scenarios after a live run

| Scenario | How to check | Pass when |
|----------|--------------|-----------|
| SC-001: no fabricated companies | Open every returned company's website, and every registry-only company's registry page, from the report | Every website loads and shows the company name; every registry page opens; no registry-only company is included |
| SC-002: no false citations | For every citation in the Included section, open the URL and find the quoted excerpt | 100% found |
| SC-003: core hypothesis | Fill in the report's spot-check table | At least 3 included, and at least 80% confirmed to meet the constraints with a genuine interest signal |
| SC-004: claims sourced | Scan the Included section | Every claim has a citation; everything else is listed under Unknowns |
| SC-005: bounds and dispositions | `hipstraw-mm show --run <runId> --json` | `returned` ≤ 10, and the disposition counts add up to `returned` |
| SC-006: outputs exist | Check the report file, the baseline, and the Emulator UI | All present; the baseline is unchanged after another `run` |
| Privacy | Search the report and the stored records for "@" and for phone-number patterns, and check that no record has a person field | No emails, phone numbers, or person fields. Person names inside quoted excerpts are allowed. |
