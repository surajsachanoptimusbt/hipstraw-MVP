---

description: "Task list for feature 002: find and review target companies for a micro-market"
---

# Tasks: Find and Review Target Companies for a Micro-Market

**Input**: Design documents from `specs/002-objective-to-target-companies/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R19), data-model.md, contracts/ (cli,
llm-outputs, config, demo-report), quickstart.md

**Tests**: Included. Constitution Principle III makes test-first development mandatory, and the
planning input requires hermetic tests with recorded responses. Each phase writes its tests first,
confirms they fail, and gets **user approval** before implementation starts. Tasks marked
*(after demo)* that add new behavior write their own test first inside the task.

**Organization**: The order follows the slice, so a runnable end-to-end path exists as early as
possible:

intake → candidates → first position → discovery → verification → Review → report.

- Phase 3 builds a thin version of every step.
- Phases 4–6 then complete User Stories 1–3.
- Tasks marked ***(after demo)*** are not needed for the first live run on Invoice Alpha (see "Live
  demo path" below).
- Anything beyond the slice is listed under **Later**.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1 = find companies (P1), US2 = Review (P2), US3 = report, records, and baseline (P3)
- ***(after demo)***: Not on the minimal live demo path
- Paths are relative to the repository root (`D:\OptimusBT\hipstraw MVP`)

---

## Live demo path (minimal subset for one live end-to-end run on Invoice Alpha)

**73 of 85 tasks.** A live run that is correct and follows the constitution needs:
- the whole foundation, including the real adapter recordings (Constitution IV);
- the thin end-to-end path, with start and end log events per step;
- the parts of US1 and US2 that keep a wrong company from being included: the headquarters and size
  checks, signal searches, the full rule gate, and judgement validation;
- the four fixes from the first live run (2026-10-07): discovery targeting, blocked websites,
  headquarters outside the metros, and name–domain mismatches, plus the real recordings made again;
- confidence, so every record has the fields FR-005 requires;
- the emulator store check, the team confirmations, and the live run itself.

Tests stay in, because Constitution III does not allow code without them.

| Phase | Demo path tasks |
|-------|-----------------|
| 1. Setup | T001–T007 |
| 2. Foundational | T009–T031 (all) |
| 3. End-to-end path | T032–T045 (all) |
| 4. US1 | T046–T054, T056, T058, T065, T077–T085 |
| 5. US2 | T059, T060, T062, T064, T066 |
| 6. US3 | none (the thin report from T043 is enough for the demo) |
| 7. Polish | T074, T075, T076 |

**After demo (12 tasks)**: T008, T055, T057, T061, T063, T067–T073.

**What the demo run lacks until then**:
- the README;
- exit code 4 when a verify ceiling runs out with companies still unverified (until then the run
  stops at the ceiling);
- per-event logs beyond the start and end event of each step;
- the US2 integration suite and the split store views;
- report sections 9–11 and the `show` command;
- lint and type cleanup.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Version control, project skeleton, dependencies, emulator config, and config files.

- [x] T001 Initialize a git repository at the repository root with `git init`, so every change can be committed and reviewed (Constitution Development Workflow and Governance). Make the first commit only after T005 adds `.gitignore`.
- [x] T002 Create the folders from plan.md: `src/hipstraw_mm/` (with `__init__.py`), `src/hipstraw_mm/prompts/`, `src/hipstraw_mm/store/`, `src/hipstraw_mm/adapters/`, `src/hipstraw_mm/evidence/`, `src/hipstraw_mm/steps/` (each package with `__init__.py`), `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/fixtures/scenarios/`, `tests/fixtures/config/`, `tests/fixtures/recorded/real/`, `config/programs/`, `positions/`, `reports/` (with `.gitkeep`)
- [x] T003 Create `pyproject.toml`:
  - hatchling build, project name `hipstraw-mm`, `requires-python = ">=3.10"`;
  - dependencies `openai`, `google-cloud-firestore`, `httpx`, `beautifulsoup4`, `pydantic>=2`, `PyYAML`;
  - `dev` extra with `pytest`, `pytest-socket`, `ruff`, `mypy`;
  - console script `hipstraw-mm = "hipstraw_mm.cli:main"`;
  - `[tool.pytest.ini_options]` with `addopts = "--disable-socket"`, `testpaths = ["tests"]`, and marker `emulator`;
  - ruff and mypy sections targeting py310;
  - no `readme` field yet (T008 adds it with the README).
- [x] T004 Generate `requirements.lock` and `requirements-dev.lock` from `pyproject.toml` with `python -m uv pip compile` (with `--extra dev` for the dev lock) at the repository root, then confirm `pip install -r requirements-dev.lock && pip install -e .` works on Windows
- [x] T005 [P] Create `firebase.json` with the Firestore emulator on host `127.0.0.1` port `8085`, the UI on port `4005`, and `"singleProjectMode": true`. Create `.gitignore` covering `.venv/`, `.runs/`, `reports/*.md`, `emulator-data/`, `.env`, `__pycache__/`
- [x] T006 [P] Create `config/programs/invoice_alpha.yaml`, `config/run.yaml` (including `profileHopsPerRun: 10`), `config/source_policy.yaml` (including `reliabilityWeights` high 1.0, medium 0.7, low 0.4, and `sourceTypeDomains`), and `positions/first_position.example.yaml` with exactly the content shown in `specs/002-objective-to-target-companies/contracts/config.md`
- [x] T007 [P] Create `config/metros.yaml` with metros `atlanta`, `san_francisco`, and `new_york`, each with `name`, `csaCode`, `states`, and `places`:
  - Check the CSA names, codes, and states against the current US Census CSA delineation file, and note the file name and date in a top comment.
  - `places` must include at least the principal cities, and for `san_francisco` the Silicon Valley cities (San Jose, Palo Alto, Mountain View, Sunnyvale, Santa Clara, Menlo Park, Redwood City).
- [ ] T008 *(after demo)* Write `README.md` at the repository root and the module docstring in `src/hipstraw_mm/__init__.py` (Constitution I and VI). Then add `readme = "README.md"` to `pyproject.toml`. The README states:
  - **Purpose**: finds and reviews real target companies for one micro-market of the Kozmo Invoice Alpha Genesis Cohort.
  - **Bounded responsibility of the Market Manager**:
    - input: one hand-written micro-market plus the cohort constraints;
    - output: Review dispositions, the first-position baseline, and a demo report;
    - findings are input to Review and never canonical;
    - only Review includes companies.
  - **Out of scope**: the list from spec FR-019.
  - **How to run**: a link to `specs/002-objective-to-target-companies/quickstart.md`.
  - **Anti-hallucination safeguards**: FR-006 to FR-008.

  The docstring states the purpose and bounded responsibility in at most 10 lines.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, domain models, stores, adapters (with real recordings), the excerpt check,
logging, schemas, and the CLI shell. Every later phase depends on these.

**⚠️ CRITICAL**: No step or story work can begin until this phase is complete.

### Tests for Phase 2 (write first; they must fail)

- [x] T009 [P] Unit tests for the excerpt check in `tests/unit/test_excerpt_check.py`:
  - Normalization maps curly quotes to straight quotes, en and em dashes to hyphens, and non-breaking spaces to normal spaces, then applies `casefold()` and collapses every run of whitespace to a single space, on both sides. Nothing else is normalized.
  - An exact substring passes, and so do differences only in case or line breaks.
  - A paraphrase fails with `excerpt_not_found`.
  - An excerpt with straight quotes matches a page with curly quotes; the same holds for dashes and non-breaking spaces.
  - A structured claim whose value is not inside the excerpt fails with `value_not_in_excerpt`.
  - An excerpt over 300 characters fails with `excerpt_too_long`.
  - An excerpt containing an email address or phone number fails with `contains_contact_data`.
  - An excerpt naming a person (for example, "CEO Jane Roe said") passes (FR-018).
- [x] T010 [P] Unit tests for config loading in `tests/unit/test_config.py`:
  - The shipped config files load.
  - `experimentContexts` must have exactly 6 entries, and so must `primaryInterests`.
  - `projectId` must start with `demo-`.
  - `budgets.companiesKept` must be `<= 10`.
  - `budgets.profileHopsPerRun` must be present.
  - `reliabilityWeights` must have exactly the keys `high`, `medium`, and `low`, each in (0, 1].
  - `sourceTypeDomains` accepts only the categories `registry`, `job_board`, `directory`, and `news`.
  - The first-position file requires `candidateId`, `segment`, `companyArchetype`, `buyer`, `problem`, `trigger`, and `primaryInterestIds` (at least 1, known IDs only). `searchHints` is optional.
  - `${LLM_MODEL}` resolves from the environment.
- [x] T011 [P] Store contract tests in `tests/contract/test_store_contract.py`, parametrized over `MemoryStore` and `FirestoreStore` (the Firestore variant is marked `emulator` and runs only with `--emulator`):
  - Every collection in data-model.md can be created and read back.
  - Creating `positionBaselines/{runId}`, `reviewDecisions/{id}`, or `evidence/{id}` twice raises an error.
  - The store protocol has no update method for those three collections.
  - Run status transitions follow "created → discovered → verified → reviewed → reported", plus `failed` from any step. An out-of-order transition raises an error.
- [x] T012 [P] Replay tests in `tests/unit/test_replay.py`:
  - Replay returns the recorded response for a match key (fetch: URL; search: query; model: schema name + stable ID).
  - A missing recording raises `ReplayMissingError` and never touches the network.
  - Record mode writes `{matchKey, request, response}` JSON to `tests/fixtures/recorded/<scenario>/<kind>/<sha256(matchKey)>.json`.
  - Record mode replaces the `Authorization` and `X-Subscription-Token` headers, and any `api_key` value, with `[redacted]` before writing.
- [x] T013 [P] Fetch adapter tests in `tests/unit/test_fetch.py`, using replayed responses:
  - A `robots.txt` disallow gives `robots_disallowed`.
  - A domain on `denylistDomains` gives `denylisted` without any request being made.
  - Non-`text/html` responses are skipped, and responses over `maxBytes` are rejected.
  - HTML to text drops `script` and `style` content.
  - Outbound links are returned as `[{linkId, href, anchorText}]`.
  - HTML to text breaks lines only at block elements (and `<br>`), so inline tags never split a sentence: `<strong>Acme</strong>: x` reads `Acme: x` (added 2026-10-07, before Phase 3).
  - **Redirect rule** (FR-008): with `same_company_only`, redirects to `www.` or another subdomain of the same company key are followed; a redirect to another company key, or to a look-alike host such as `notacme.test`, stops with `redirect_off_site` and the 3xx status. Every hop is checked against the denylist and `robots.txt`.
- [x] T014 Test harness in `tests/conftest.py`:
  - a `--emulator` CLI option that skips `emulator`-marked tests unless it is given and `FIRESTORE_EMULATOR_HOST` is set, and allows sockets to localhost only in that case;
  - a `memory_store` fixture;
  - a `replay_adapters(scenario)` fixture that builds the model, search, and fetch adapters in replay mode for `tests/fixtures/recorded/<scenario>/`;
  - a `test_config` fixture that loads `config/` overrides from `tests/fixtures/config/`, where `sourceTypeDomains` and the denylist use `.test` domains.
- [x] T015 [P] Adapter contract tests in `tests/contract/test_adapters_real.py`, replaying the real recordings in `tests/fixtures/recorded/real/` (Constitution IV):
  - The Brave adapter returns at least 1 `{url, title, snippet}`.
  - The fetch adapter returns status 200, non-empty `text`, a `links` list, and a `robots.txt` decision.
  - Each of the five schemas (`QueryPlan`, `ListingExtraction`, `HomepageIdentity`, `CompanyEvidence`, `ReviewJudgement`) parses from its recorded OpenAI response.
  - No recorded file contains a value from the `OPENAI_API_KEY` or `BRAVE_API_KEY` environment variables, or any `sk-` key-like string.

  These tests fail until T030 records the responses.
- [x] T016 Run `pytest tests/unit tests/contract` to confirm the Phase 2 tests fail, then present them for **user approval** before writing code in `src/hipstraw_mm/` (Constitution III)

### Implementation for Phase 2

- [x] T017 [P] Implement Pydantic config models and loaders for all four config files and the first-position file in `src/hipstraw_mm/config.py`, enforcing every rule tested in T010
- [x] T018 [P] Implement domain models in `src/hipstraw_mm/models.py` exactly as in data-model.md:
  - **Enums**:
    - run `status`: `created`, `discovered`, `verified`, `reviewed`, `reported`, `failed`;
    - `claimField`: `origin`, `existence`, `hq`, `employees`, `revenue`, `parent`, `fit_buyer`, `fit_problem`, `fit_trigger`, `signal_pain`, `signal_exploration`;
    - `sourceType`: `registry`, `news`, `company_site`, `job_board`, `directory`;
    - `reliability`: `high`, `medium`, `low`;
    - check `reason`: `not_retrievable`, `robots_disallowed`, `denylisted`, `excerpt_not_found`, `value_not_in_excerpt`, `excerpt_too_long`, `contains_contact_data`;
    - `identifierCheck.status`: `resolves`, `fails`, `no_website`;
    - `origin.kind`: `listing_link`, `profile_hop`, `direct_homepage`, `registry_only`;
    - `disposition`: `include`, `exclude`, `needs_verification`.
  - `CompanyRecord.status` is `Literal["finding"]`. There is no included state.
  - `domain_key(url)`: "the website's host in lowercase, with a leading `www.` removed and dots replaced by `-`".
  - `registry_key(name)`: "`registry-` plus its name in lowercase with every run of non-alphanumeric characters replaced by `-`".
  - `runId` format: `run_<UTC yyyymmddThhmmss>`.
- [x] T019 Implement the excerpt check in `src/hipstraw_mm/evidence/excerpt_check.py` (depends on T018), making T009 pass
- [x] T020 [P] Implement JSON-lines logging in `src/hipstraw_mm/logging_setup.py`:
  - output to stderr and to `.runs/<runId>/run.log`;
  - each event carries `runId`, `step`, and optional `companyRecordId`;
  - values of `OPENAI_API_KEY` and `BRAVE_API_KEY` are never logged.
- [x] T021 Define the `Store` protocol in `src/hipstraw_mm/store/base.py` (depends on T018):
  - create and get methods for each collection;
  - upsert only for `programs`, `marketCandidates`, `runs`, and `companyRecords`;
  - create-only for `evidence`, `reviewDecisions`, and `positionBaselines`;
  - `transition_run(runId, from_status, to_status)` enforcing the state machine.
- [x] T022 [P] Implement `MemoryStore` in `src/hipstraw_mm/store/memory.py` (depends on T021)
- [x] T023 [P] Implement `FirestoreStore` in `src/hipstraw_mm/store/firestore.py` (depends on T021):
  - Use `google-cloud-firestore`.
  - Refuse to start unless `FIRESTORE_EMULATOR_HOST` is set and the project ID starts with `demo-`.
  - Use `document.create()` for create-only collections.
  - Use the collection names `programs`, `marketCandidates`, `runs`, `companyRecords`, `evidence`, `reviewDecisions`, `positionBaselines`, `demoReports`.
- [x] T024 Implement record and replay in `src/hipstraw_mm/adapters/replay.py` (depends on T018), making T012 pass, including the secret redaction. The mode comes from `HIPSTRAW_REPLAY` (`replay` or `record`, defaulting to off outside tests).
- [x] T025 [P] Implement the OpenAI client in `src/hipstraw_mm/adapters/llm.py`:
  - `parse(schema, messages, match_key, prompt_version)` via `client.chat.completions.parse` with strict structured output;
  - no `tools` parameter;
  - one retry on a schema validation failure, then raise `LLMSchemaError`;
  - logs the schema name, prompt version, and model;
  - wrapped by replay.
- [x] T026 [P] Implement the Brave Search client in `src/hipstraw_mm/adapters/search.py`:
  - `GET https://api.search.brave.com/res/v1/web/search` with the `X-Subscription-Token` header and `q` and `count` parameters;
  - returns `[{url, title, snippet}]`;
  - drops results on denylisted domains;
  - wrapped by replay.
- [x] T027 [P] Implement the fetcher in `src/hipstraw_mm/adapters/fetch.py`, making T013 pass:
  - `httpx` with the `userAgent` from the source policy, `timeoutSeconds`, `maxBytes`, and `perHostDelaySeconds`;
  - `urllib.robotparser`, cached per host per run, and the denylist check;
  - BeautifulSoup `html.parser` for text, plus links with `linkId`s;
  - returns `{url, finalUrl, redirectChain, status, text, links, contentSha256, fetchedAt, failReason}`;
  - wrapped by replay.
- [x] T028 [P] Define the five Pydantic schemas `QueryPlan`, `ListingExtraction`, `HomepageIdentity`, `CompanyEvidence`, and `ReviewJudgement` in `src/hipstraw_mm/llm_schemas.py`, exactly as in contracts/llm-outputs.md. No person, email, or phone fields.
- [x] T029 Implement the CLI shell in `src/hipstraw_mm/cli.py` per contracts/cli.md:
  - argparse subcommands `intake`, `candidates`, `position`, `discover`, `verify`, `review`, `report`, `run`, `show`;
  - global `--config-dir` and `--json`;
  - exit codes 0–4;
  - the emulator and `demo-` precondition (exit code 2);
  - the `--json` output shape;
  - error messages always written to stderr, in both modes;
  - a `build_context()` factory (store and adapters) that tests can override.
- [x] T030 Write `tests/fixtures/record_real.py` and have a team member with keys run it with `HIPSTRAW_REPLAY=record` (quickstart.md, "Recording the real adapter responses"). The script makes exactly:
  - one Brave query (`SaaS companies Atlanta`);
  - one page fetch, plus its `robots.txt`, of the first result whose `robots.txt` allows fetching;
  - one OpenAI parse per schema, using minimal fixed prompts and that page's text as input. `ReviewJudgement` uses a two-item synthetic evidence list.

  It writes to `tests/fixtures/recorded/real/`, fails if any key value appears in a written file, and the files are then committed.
- [x] T031 Run `pytest tests/unit tests/contract` and confirm all Phase 2 tests pass, including T015 against the real recordings

**Checkpoint**: The foundation is ready, the adapters are proven against real response shapes, and
the default suite runs with the network blocked.

---

## Phase 3: End-to-End Path (thin version of every step) 🎯 First runnable slice

**Goal**: `hipstraw-mm run` completes on recorded responses and writes a report, with the rules that
matter most already enforced:
- discovery link rules;
- the website must load;
- existence needs a homepage citation;
- excerpts must match exactly;
- registry-only companies go to needs verification;
- a company with no verifiable source is never included.

**Independent Test**: `pytest tests/integration/test_end_to_end_path.py
tests/integration/test_no_verifiable_source_not_included.py` passes with sockets blocked.

### Tests for Phase 3 (write first; they must fail)

- [x] T032 [US1] Create the replay scenario `tests/fixtures/scenarios/basic.yaml` and a builder script `tests/fixtures/build_fixtures.py` that writes `tests/fixtures/recorded/basic/`. Use only `.test` domains and plainly fictional names (Constitution IX). The scenario contains:
  - a `QueryPlan` with 3 queries;
  - search results for:
    - listing page `https://list.example.test/atlanta-saas`;
    - registry page `https://registry.example.test/ga/search` (listed under `registry` in `tests/fixtures/config/source_policy.yaml`);
    - a direct homepage `https://epsilon-pay.test/`;
  - listing HTML naming these companies:
    - `alpha-ledger.test`, with an external link;
    - `beta-billing.test`, with only an internal link to `https://list.example.test/companies/beta`, whose profile page links externally to `beta-billing.test`;
    - `gamma-ops.test` and `delta-none.test`, with external links;
    - `sigma-scale.test` (about page: "5,000+ employees") and `theta-works.test` (about page: headquartered in "Chicago, IL"), with external links and otherwise fully cited, so only the rule checks can exclude them;
    - Alpha Ledger's name wrapped in `<strong>`, so its excerpt matches only if inline tags don't break lines;
  - registry HTML naming "Zeta Holdings LLC" and "Alpha Ledger, Inc.", neither with a website link. Alpha Ledger is also found through its website, so it tests the merge rule.
  - an allow-all `robots.txt` for every host;
  - homepages for `alpha`, `beta`, `epsilon`, and `gamma` containing their names, while `delta-none.test` returns 404;
  - about and careers pages with headquarters "Atlanta, GA", employee counts under 500, and AP job-posting text;
  - `HomepageIdentity` for `epsilon-pay.test`;
  - `CompanyEvidence` responses. `alpha`, `beta`, and `epsilon` quote their pages verbatim; every `gamma` excerpt is a paraphrase.
  - `ReviewJudgement` responses with `falsifierMet: false` and `fitHolds: true`, only for `alpha`, `beta`, and `epsilon`. Gamma, delta, sigma, theta, and zeta have none, so a judgement call for any of them fails the run.
- [x] T033 [P] [US1] Integration test `tests/integration/test_end_to_end_path.py`:
  - With `MemoryStore` and the `basic` replay, run `intake`, `candidates`, `position`, `discover`, `verify`, `review`, `report` through `cli.main([...])` with `build_context()` overridden.
  - Assert the run status reaches `reported`.
  - Assert the origin kinds `listing_link` (alpha), `profile_hop` (beta), `direct_homepage` (epsilon), and `registry_only` (zeta) all appear.
  - Assert `zeta` has `domain == null`, `identifierCheck.status == "no_website"`, `falsifier == null`, empty `fitClaims` and `interestSignals`, and `unknowns` including `fit`, `interestSignal`, and `falsifier` (FR-005).
  - Assert exactly one record exists for Alpha Ledger, the website record. The registry-only "Alpha Ledger, Inc." was dropped by the merge rule, and no origin evidence was written for it.
  - Assert `.runs/<runId>/run.log` has a `step_start` and a `step_end` event for each of `discover`, `verify`, `review`, and `report`, with each `step_end` carrying that step's counts.
  - Assert every company with a loading website has an `existence` evidence document whose excerpt contains its name.
  - Assert at most 10 records exist, each with `status == "finding"`, and each with exactly one `reviewDecisions` document.
  - Assert `reports/<runId>.md` exists with the headings of sections 1–8 from contracts/demo-report.md.
  - Also assert (approved 2026-10-07): alpha, beta, and epsilon are the only `include`s; every record's origin citation passes and names the company; the baseline matches the decisions; `demoReports.sha256` matches the file and each company is under the right report section; `hipstraw-mm run` completes; a second `review` exits with code 2. `tests/unit/test_build_fixtures.py` fails when the committed recordings are stale.
- [x] T034 [P] [US2] Integration test `tests/integration/test_no_verifiable_source_not_included.py` (required by the planning input). After the `basic` run, none of these is `include`:
  - `delta-none.test` (website 404) → `exclude`, with `ruleResults` entry `{rule: existence, outcome: fail}`;
  - `gamma-ops.test` (all citations fail) → every claim is in `unknowns`, with no `fitClaims` or `interestSignals`;
  - "Zeta Holdings LLC" (registry-only) → `needs_verification`, with `{rule: existence, outcome: unknown}` (FR-008).
  - `sigma-scale.test` ("5,000+ employees") → `exclude`, with `{rule: size, outcome: fail}` and no judgement;
  - `theta-works.test` (Chicago, IL) → `exclude`, with `{rule: hq, outcome: fail}` and no judgement;
  - every `include` carries a non-empty `evidenceIds` list of the record's passing evidence documents.
- [x] T035 [US1] Run `pytest tests/integration` to confirm the Phase 3 tests fail, then present them for **user approval** before implementing Phase 3 (Constitution III)

### Implementation for Phase 3

- [x] T036 [US1] Implement `src/hipstraw_mm/steps/intake.py`: load `config/programs/<id>.yaml` and upsert `programs/{programId}` with `objective`, `sourceUrl`, `experimentContexts`, `primaryInterests`, and `defaultConstraints` (`{maxEmployees, maxRevenueUsd, metroIds[]}` from `config/run.yaml`)
- [x] T037 [P] [US1] Implement `src/hipstraw_mm/steps/candidates.py`: for each of the six experiment contexts, upsert `marketCandidates/{candidateId}` with `candidateId = "<programId>__<experimentContextId>"` and `origin = "program_experiment_context"`. No model call and no generation (FR-019).
- [x] T038 [US1] Implement `src/hipstraw_mm/steps/position.py`:
  - Validate the first-position file and check that the candidate exists.
  - Create `runs/{runId}` with status `created`.
  - Copy `constraintsInForce` (`{maxEmployees, maxRevenueUsd, metros[{id, csaCode, name}]}`), `budgets`, and `model` from config.
  - Print the `runId`.
- [x] T039 [P] [US1] Write prompt templates `src/hipstraw_mm/prompts/query_plan.v1.txt`, `listing_extraction.v1.txt`, `homepage_identity.v1.txt`, `company_evidence.v1.txt`, and `review_judgement.v1.txt`. Each says:
  - use only the provided text;
  - copy excerpts verbatim, at most 300 characters;
  - never output person fields, emails, or phone numbers;
  - return only the schema.

  `company_evidence.v1.txt` adds: spend phrases such as "heavy recurring spend" are examples only, and every interest signal needs a quoted excerpt (FR-020).
- [x] T040 [US1] Implement `src/hipstraw_mm/steps/discover.py` (thin), following the discovery rules in contracts/llm-outputs.md:
  - Make the `QueryPlan` call (match key: `candidateId`), then search.
  - **Direct homepage**: a root-path result on an unclassified domain gets a `HomepageIdentity` call (match key: URL).
  - **Listing page**: any other result gets a `ListingExtraction` call (match key: URL).
  - **Links**: only external links count. One hop is allowed per company via an internal profile link (match key: profile URL), within `profileHopsPerRun`.
  - **Registry-only**: a registry-page company with no website is kept with `domain: null` and the `registry_key`.
  - Keep a company only if its excerpt passes and contains the name. Dedupe by company key.
  - **Merge rule** (data-model.md): if a website record with the same normalized name exists in the run, drop the registry-only record. The normalization is `casefold`, punctuation removed, whitespace collapsed, and one trailing legal suffix removed. Apply dedupe and merge before the cap and before writing anything.
  - Stop at every discovery limit; reaching one is normal completion. Keep at most `companiesKept`, and set `shortfallReason` when fewer than 10 are kept.
  - Write origin `evidence` and `companyRecords` with `status: finding` and `origin {kind, searchQuery, resultUrl, listingEvidenceId, profileUrl}`.
  - Emit a `step_start` log event at the start, and a `step_end` event with counts (searches, fetches, model calls, candidates found, kept, dropped by merge) at the end.
  - Record `runs.counts`, then transition the run to `discovered`.
- [x] T041 [US1] Implement `src/hipstraw_mm/steps/verify.py` (thin):
  - **Website load** (FR-008): fetch `https://<domain>/`, accepting redirects only within the same company key or its subdomains. Record `resolves` on 2xx, otherwise `fails` with `httpStatus`. Record `no_website` for registry-only companies, which are never fetched.
  - **Existence evidence** (FR-016): for each website that resolves, build it from the homepage as defined in data-model.md, with the sentence (or 100 characters on each side) around the first occurrence of the name, at most 300 characters. Set `existenceEvidenceId`.
  - Fetch own-site pages linked from the homepage whose path contains `about`, `company`, `careers`, `jobs`, `contact`, `locations`, `press`, or `news`, up to `ownSitePagesPerCompany`.
  - Make the `CompanyEvidence` call (match key: domain). Create one `evidence` document per claim and run its check.
  - **Registry-only companies get no evidence-extraction call** (no `CompanyEvidence`, and no page fetches). Set `fitClaims: []`, `interestSignals: []`, and `falsifier: null`, and add `fit`, `interestSignal`, and `falsifier` to `unknowns` (FR-005).
  - Keep fit claims and interest signals only if they have at least one passing claim; put everything else in `unknowns`.
  - Fill `hq` with `src/hipstraw_mm/evidence/location.py` (research R5) and `size` with `src/hipstraw_mm/evidence/size.py` (research R6, without parent handling), so the rule checks can exclude `theta` and `sigma`. T052 and T053 complete these modules against their unit tests.
  - Set `confidence: null` here; T054 computes it before the demo.
  - Track `verifyFetchesPerRun` and `verifyModelCallsPerRun`, and stop at either ceiling. Exit code 4 for that case is added in T055.
  - Emit a `step_start` log event, and a `step_end` event with counts (fetches, model calls, companies verified, registry-only, websites failed, citations passed and failed).
  - Record `runs.counts`, then transition the run to `verified`.
- [x] T042 [US2] Implement `src/hipstraw_mm/steps/review.py` (thin):
  - **Rule gate**: website `fails` → `exclude`. `no_website`, or an existence evidence that failed → `needs_verification`. Headquarters `not_met` or size `over` → `exclude`. Headquarters `unknown`, size `unknown` or `conflict`, or no interest signal → `needs_verification`.
  - **Judgement call**: only for records that pass every rule, with only passing evidence as input (match key: `companyRecordId`). Apply `falsifierMet → exclude`, `!fitHolds → needs_verification`, no passing evidence document → `needs_verification`, otherwise `include`.
  - Attach the IDs of the record's passing evidence documents to every decision as `evidenceIds` (approved 2026-10-07). Unit tests: `tests/unit/test_judgement_validation.py` (started here; T060 adds the remaining cases).
  - Create `reviewDecisions/{runId}__{domainKey}` with reviewer `market-manager/rules-v1+<model>`.
  - Create `positionBaselines/{runId}` with `create()`.
  - Emit a `step_start` log event, and a `step_end` event with counts (reviewed, include, exclude, needs verification, judgement calls).
  - Transition the run to `reviewed`.
- [x] T043 [US3] Implement `src/hipstraw_mm/steps/report.py` (thin):
  - Write `reports/<runId>.md` with sections 1–8 from contracts/demo-report.md: title, run summary, first position, constraints in force, hypothesis check with a blank spot-check table, included, needs verification, and excluded. Show confidence as "not computed" while it is null.
  - Create `demoReports/{runId}` with `path`, `sha256`, `counts`, and `generatedAt`.
  - Emit a `step_start` log event, and a `step_end` event with counts (companies per section, report bytes).
  - Transition the run to `reported`.
- [x] T044 [US1] Wire every subcommand in `src/hipstraw_mm/cli.py` to its step:
  - `run` executes `position`, `discover`, `verify`, `review`, `report` in order and stops at the first failure, marking the run `failed` with `errorStep` and `errorMessage`.
  - `review` exits with code 2 if decisions already exist for the run.
- [x] T045 [US1] Run `pytest tests/` and confirm `tests/integration/test_end_to_end_path.py` (T033) and `tests/integration/test_no_verifiable_source_not_included.py` (T034) pass with sockets blocked

**Checkpoint**: A runnable end-to-end slice exists.

---

## Phase 4: User Story 1 - Find real, evidenced companies for one micro-market (Priority: P1)

**Goal**: Complete company records:
- discovery that targets the first position (ranking before the cap);
- websites that exist but cannot be read kept apart from websites that do not exist;
- headquarters checked against the complete CSA place lists;
- name–domain mismatches made explicit;
- size, parent, and large-enterprise evidence;
- signal searches, labeled interest signals, and primary interests;
- preserved conflicts and explicit unknowns;
- computed confidence, and validated judgement citations.

Exit code 4 when a verify ceiling runs out, and per-event logs, come after the demo.

**Reordered on 2026-10-07 after the first live run** (`run_20261007T140925`; spec Clarifications,
Session 2026-10-07 after the live run). Implementation runs in the order listed below, not in ID
order:
1. the four live-run findings: T082 (discovery targeting), T083 (blocked websites), T052
   (headquarters outside the metros), T084 (name–domain mismatch);
2. then T053 (parent-company check), T056 (signal searches), T054 (confidence), and T065 (cited-ID
   validation, moved here from Phase 5);
3. then T085 (the real recordings, made again).

Task IDs T077–T085 were added on that date.

**Independent Test**: `pytest tests/unit/test_targeting.py tests/unit/test_website_checks.py
tests/unit/test_location.py tests/unit/test_size.py tests/unit/test_confidence.py
tests/unit/test_rule_gate.py tests/unit/test_judgement_validation.py
tests/integration/test_discovery_targeting.py tests/integration/test_us1_finding.py` covers US1
acceptance scenarios 1–9 and US2 scenarios 9–10, using recorded responses.

### Tests for User Story 1 (write first; they must fail)

- [x] T077 [P] [US1] Unit tests in `tests/unit/test_targeting.py` (discovery targeting, FR-022, research R19), against `src/hipstraw_mm/steps/targeting.py`:
  - `order_queries` puts queries round-robin by metro in the configured order, with queries that name no metro last; nothing is dropped.
  - `reading_order` interleaves results across queries (first of each, then second of each) and skips repeated URLs.
  - `classify_metro`: a location missing from the entry's excerpt → `unknown` whatever the model says; `"Atlanta, GA"` → `in`; `"Buffalo, NY"` and `"Dallas, TX"` → `out`, overriding a model `in`; `"Austin, Texas"` → `out`; an unparseable location keeps the model's value; no location → `unknown`.
  - `rank_candidates`: `in` before `unknown` before `out`, then `strong` before `partial` before `weak`, then website before registry-only. An alphabetical page's entries are not returned in page order. Ties alternate between source pages. The result is the same for any input order.
- [x] T078 [P] [US1] Unit tests in `tests/unit/test_website_checks.py` (FR-008, FR-016, research R4) against `src/hipstraw_mm/evidence/existence.py`:
  - `website_status`: 2xx → `resolves`; HTTP 404 and 410, and `dns_error` → `fails`; `robots_disallowed`, HTTP 401, 403, 429, 500, and 503, `network_error`, `redirect_off_site`, `too_many_redirects`, `not_html`, and `too_large` → `unreadable`.
  - `name_matches_domain`: Addison Health Systems / writepad.com → false; Alpha Ledger / alpha-ledger.test, Accountable HQ / www.accountablehq.com, ADEO Healthcare Software / adeohs.com, 6DOS / 6dos.co, and The Home Depot / homedepot.com → true.

  Add to `tests/unit/test_fetch.py`: a host whose name does not resolve gives `dns_error` for a page and for its `robots.txt` (never `robots_disallowed`); any other connection error stays `network_error`.
- [x] T046 [P] [US1] Unit tests in `tests/unit/test_location.py` (research R5 as revised on 2026-10-07; place lists keyed by state):
  - A listed city with a matching state → `met`.
  - A state outside every metro's `states` → `not_met`.
  - **A matching state with an unlisted city → `not_met`** (Buffalo, NY; changed from `unknown`).
  - A full state name ("Austin, Texas") is read as its code.
  - A value naming no city: "California", "New York", "Georgia", "Alabama", and "Pennsylvania" → `unknown` (each state has some part in a metro CSA); "Texas" and "Illinois" → `not_met`. No headquarters claim → `unknown`.
  - Citations inside and outside together → `conflict`. All inside → `met`.
  - The same place name in two states resolves by state.
  - `Palo Alto, CA` → `met` (the San Francisco CSA is the wider region).
  - (An "office in New York" statement is not a headquarters claim. That is a prompt rule, so T050 checks it on the `us1` Palo Alto company, whose page also names a New York office.)
  - **The real `config/metros.yaml`** lists known in-CSA suburbs (for example Cumming, GA; Menlo Park, CA; Montclair, NJ) and none of Buffalo, NY; Sacramento, CA; Savannah, GA; Philadelphia, PA; or Hartford, CT.
- [x] T047 [P] [US1] Unit tests in `tests/unit/test_size.py`:
  - Thresholds are strict "less than" and come from config; changing `maxEmployees` changes the outcome, so nothing is hard-coded.
  - A range uses its upper bound for "under" and its lower bound for "over".
  - 450 and 620 employees → `conflict`.
  - Only "over" evidence → `over`.
  - No signals → `unknown`.
  - `evaluate_parent`: a parent on `largeEnterpriseParents` (normalized name), or a parent whose `parent_employees` or `parent_revenue` reaches a threshold → `large`.
  - A parent cited under both thresholds → `small`. A parent of unknown size → `unknown_size`. No parent claim → no parent.
- [x] T048 [P] [US1] Unit tests in `tests/unit/test_confidence.py`:
  - Reliability comes from `reliabilityBySourceType`, and weights from `reliabilityWeights` (high 1.0, medium 0.7, low 0.4).
  - Confidence is the mean, over existence, location, size, and interest signal, of the best passing citation's weight, with 0 for an item that has none.
  - Bands: "High ≥ 0.8, Medium 0.5–0.79, Low < 0.5".
- [x] T079 [P] [US1] Unit tests in `tests/unit/test_rule_gate.py`, the rows that changed on 2026-10-07 (T059 adds the rest of the research R9 table):
  - `fails` (HTTP 404, HTTP 410, `dns_error`) → `exclude`.
  - `unreadable` (`robots_disallowed`, HTTP 403, HTTP 429, a redirect off the site) → `needs_verification`, with the cause in the reason.
  - Headquarters `not_met` for Buffalo, NY → `exclude`; `conflict` → `needs_verification` with both places in the reason; `unknown` → `needs_verification`.
  - `nameMatchesDomain: false` with a passing existence citation → the existence rule passes; with a failed one → `needs_verification`, and the reason names the website and the company.
  - Parent `large` → `exclude`, through the `large_enterprise` rule; parent `unknown_size` → `needs_verification`.
- [x] T080 [P] [US1] Add to `tests/unit/test_judgement_validation.py` (for T065): a judgement citing an evidence ID that is not in the passing set → `needs_verification` with the reason "judgement cited unknown evidence", even when `fitHolds` is true. A judgement citing only passing IDs can still include.
- [x] T049 [US1] Add three replay scenarios and build them with `tests/fixtures/build_fixtures.py`. Use `.test` domains only. First extend the builder with:
  - per-origin `robots` (text, or a status);
  - `unreachable` hosts (`dns` or `connect`);
  - `signalSearches` with explicit results, and `noSignalResults`, which records the three research R7 queries with empty results;
  - the ranking fields on listing and homepage responses;
  - `parent_employees` and `parent_revenue` as structured claims.

  The three scenarios:
  - `tests/fixtures/scenarios/us1_targeting.yaml` (discovery only):
    - an alphabetical A–Z directory of 12 companies whose first entries are off-target (headquartered in Dallas, Austin, or Buffalo; consumer businesses);
    - one entry whose stated location is not in its excerpt (another entry on the page has that location);
    - three metro lists (Atlanta, Bay Area, New York);
    - 19 candidates in all, of which exactly 10 are `in` and `strong`.
  - `tests/fixtures/scenarios/us1_sites.yaml`:
    - eight New York companies whose websites are blocked by robots.txt, answer HTTP 403, 429, 410, or 503, or whose domain does not resolve;
    - Larch Health Systems on `quillpad.test`, whose homepage names it;
    - Sorrel Analytics on `tallyhub.test`, whose homepage does not;
    - a robots-disallowed listing page and a `linkedin.com` result;
    - eight kept, so the shortfall is recorded.
  - `tests/fixtures/scenarios/us1.yaml`, ten companies:
    - conflicting employee counts (450 and 620);
    - a Palo Alto, CA headquarters with an exploration signal (AI for invoice processing) and a press excerpt naming a person (allowed);
    - no interest signal;
    - an unsourced "heavy recurring SaaS spend" signal (A1) beside a sourced one, and an excerpt with an email address;
    - an interest signal found only on a job-board page through a signal search;
    - a cited Buffalo, NY headquarters;
    - a parent on `largeEnterpriseParents`, a parent of unknown size, and a parent cited with 12,000 employees;
    - a judgement that cites an unknown evidence ID.

  Also add `noSignalResults` for the six `basic` companies whose website loads, and add "Omega Conglomerate" to `largeEnterpriseParents` in `tests/fixtures/config/run.yaml`. The three new scenarios can be built only once the schemas carry the ranking fields (T082) and the parent-size claims (T053). Until then their tests fail on the missing recordings.
- [x] T081 [US1] Integration test `tests/integration/test_discovery_targeting.py` on `us1_targeting` (FR-022, US1 scenario 9):
  - exactly the 10 `in` and `strong` candidates are kept, and none of the directory's off-target first entries;
  - the entry whose location is not in its excerpt is not treated as `in`;
  - `origin.match` holds the checked values;
  - `droppedOverCap` is 9;
  - every planned query is searched.
- [x] T050 [US1] Integration test `tests/integration/test_us1_finding.py` covering US1 acceptance scenarios 1–8 and US2 scenarios 9–10, on `us1` and `us1_sites`:
  - All FR-005 fields are present, including `confidence` with a value and band, and every fit claim has `primaryInterestIds` with at least 1 known ID.
  - Each record's origin traces to a retrieved page.
  - Failed excerpts become unknowns.
  - **Websites** (`us1_sites`):
    - robots-blocked, 403, 429, and 503 sites are `unreadable` → `needs_verification`, with the cause in the reason, and get no `CompanyEvidence` call or signal searches;
    - 410 and DNS-failure sites are `fails` → `exclude`.
  - **Name–domain**: Larch Health Systems passes existence with `nameMatchesDomain: false`; Sorrel Analytics is `needs_verification`, with `tallyhub.test` in the reason.
  - Both conflicting employee counts are kept as separate signals.
  - The shortfall sets `shortfallReason` (`us1_sites`).
  - Every record has `status == "finding"`.
  - A missing interest signal appears in `unknowns` with field `interestSignal`.
  - The unsourced "heavy spend" signal is absent, and every kept interest signal has at least 1 passing citation (FR-020).
  - The job-board signal is kept with `sourceType: job_board`. Each loading website gets at most 3 signal searches, and registry-only and non-resolving companies get none.
  - **Headquarters**: Buffalo, NY → `not_met` → `exclude`.
  - **Parents**: the listed parent and the 12,000-employee parent → `exclude`; the parent of unknown size → `needs_verification`.
  - The judgement citing an unknown evidence ID → `needs_verification`.
  - `linkedin.com` and the robots-disallowed URL are never fetched.
  - The email excerpt fails with `contains_contact_data`, and the person-name excerpt passes.
  - `runs.counts` stays within every budget in `config/run.yaml`.

  Also add to `tests/integration/test_end_to_end_path.py`: the `basic` verify step makes 18 signal searches (3 for each of the six loading websites).
- [x] T051 [US1] Run the new tests to confirm they fail, then present them for **user approval** (Constitution III):
  - `tests/unit/test_targeting.py`, `test_website_checks.py`, `test_location.py`, `test_size.py`, `test_confidence.py`, `test_rule_gate.py`;
  - the additions to `test_judgement_validation.py`, `test_fetch.py`, and `test_end_to_end_path.py`;
  - `tests/integration/test_discovery_targeting.py` and `test_us1_finding.py`;
  - the three scenarios.

### Implementation for User Story 1 (in this order)

- [x] T082 [US1] **Discovery targeting** (FR-022, research R19), making T077 and T081 pass. It needs two parts of T052 first, so it brings them forward: the location rules in `location.py`, and the state-keyed `Metro` shape in `config.py` with both metro files converted. The changes:
  - Add `location`, `metroMatch`, and `positionMatch` to `ListedCompany` and `HomepageIdentity` in `src/hipstraw_mm/llm_schemas.py`.
  - Write prompts `query_plan.v2.txt`, `listing_extraction.v2.txt`, and `homepage_identity.v2.txt`, and pass the position and the metro names in their payloads.
  - Implement `src/hipstraw_mm/steps/targeting.py`.
  - In `src/hipstraw_mm/steps/discover.py`: order the queries, run every search before reading, read round-robin, keep the best-ranked duplicate, rank before the cap, and store `origin.match` (add `OriginMatch` to `models.py`).
  - **Page caps** (added at the T051 review): `listingPagesPerSite` and `listingPagesPerQuery` in `config/run.yaml` and `Budgets`. `select_pages` in `targeting.py` skips a result whose site or query has reached its cap, and the discover counts record `resultsOverSiteCap` and `resultsOverQueryCap`. Tests: `TestSelectPages` in `test_targeting.py`, and the extra A–Z and Atlanta results in `us1_targeting`.
  - Add the ranking fields to the `basic` listing and homepage responses, rebuild `basic`, and build `us1_targeting`.
- [x] T083 [US1] **Blocked websites** (FR-008, FR-013, research R3, R4), making T078's `website_status` and fetch cases and T079's website rows pass:
  - Report `dns_error` from `src/hipstraw_mm/adapters/fetch.py` (live: a failed connection whose host name does not resolve; replay: `dnsFailed: true`), including for `robots.txt`.
  - Implement `website_status` in `src/hipstraw_mm/evidence/existence.py` and add `unreadable` to `IdentifierStatus`.
  - In `src/hipstraw_mm/steps/verify.py`, an `unreadable` website gets no page fetches, no `CompanyEvidence` call, and no signal searches; its unknowns say why.
  - In `src/hipstraw_mm/steps/review.py`, `fails` → `exclude`, and `unreadable` → `needs_verification` with the cause. Build `us1_sites`.
- [x] T052 [P] [US1] **Headquarters outside the metros** (research R5 as revised), making T046 and T079's headquarters rows pass:
  - The location rules and the state-keyed `Metro` shape are brought forward into T082.
  - **State names in headquarters claim checks** (added at the T051 review): in `src/hipstraw_mm/evidence/excerpt_check.py`, an `hq` claim's value passes when it appears in the excerpt with its state written as either the code or the full name ("Addison, TX" against "Addison, Texas"). Tests: `TestHeadquartersStateNames` in `tests/unit/test_excerpt_check.py`. The builder passes the claim field too.
  - Add `conflict` to the `hq` status.
  - Write `scripts/build_metro_places.py`, which builds complete place lists from the Census CSA delineation file and the place-to-county relationship file, and commit the regenerated `config/metros.yaml`, with the source files and their dates in its header. Convert `tests/fixtures/config/metros.yaml` to the new shape.
  - In `src/hipstraw_mm/steps/review.py`, `not_met` → `exclude`, and `conflict` → `needs_verification` with both places.
- [x] T084 [US1] **Name–domain mismatch** (research R4), making T078's `name_matches_domain` cases and T079's name–domain rows pass:
  - Implement `name_matches_domain`.
  - Store `identifierCheck.nameMatchesDomain` in `src/hipstraw_mm/steps/verify.py`.
  - When the existence citation fails and the names do not match, the review reason names the website and the company.
  - **Existence from about or contact pages** (FR-016, added at the T051 review): `find_existence` in `existence.py` searches the homepage, then the already-fetched own-site pages whose path contains `about` or `contact`, in fetch order. There are no extra fetches, and own-site pages are now fetched before the existence evidence is built. Tests: `TestFindExistence` in `test_website_checks.py`, and Teasel Systems (named only on its about page) in `us1_sites`.
- [x] T053 [US1] **Parent-company check**: complete size, range, conflict, and parent evaluation in `src/hipstraw_mm/evidence/size.py` per research R6, making T047 pass:
  - Add the `parent_employees` and `parent_revenue` claim fields (schema, `company_evidence.v2.txt`, `models.py`, and the unknowns mapping).
  - Fill `parent` in `src/hipstraw_mm/steps/verify.py`.
  - Add the `large_enterprise` rule to `src/hipstraw_mm/steps/review.py` (moved here from T064), so `large` → `exclude` and `unknown_size` → `needs_verification`.
- [x] T056 [US1] **Signal searches**: complete `src/hipstraw_mm/steps/verify.py`, making the T050 signal cases and the `basic` signal-search assertion pass:
  - Run up to `signalSearchesPerCompany` signal searches per resolving website, with the exact research R7 query strings. Fetch up to `thirdPartyPagesPerCompany` third-party pages (own-site results count toward `ownSitePagesPerCompany`), and give them to `CompanyEvidence` after the own-site pages.
  - Assign `sourceType` per the source type rules in contracts/config.md, and `reliability` from config.
  - Fill `hq` with `location.py`, and fill `size` and `parent` with `size.py`.
  - Require `primaryInterestIds` to be non-empty and known.
  - Label each interest signal `pain` or `exploration`, and keep only those with a passing citation.
  - Add an `unknowns` entry for every minimum-proof item without a passing citation, including `interestSignal`.
  - Keep conflicting values as separate signals.
  - Record the signal-search count in the verify `step_end` event.
  - Build `us1`. The `basic` recordings for these searches were added in T049.
- [x] T054 [US1] **Confidence**: implement reliability weights and confidence in `src/hipstraw_mm/evidence/confidence.py` per research R8, making T048 pass. Registry-only records get the normal formula, which gives 0 and the Low band. Set `companyRecords.confidence` in `src/hipstraw_mm/steps/verify.py`, and show the band in `src/hipstraw_mm/steps/report.py`.
- [ ] T065 [US2] **Cited-ID validation** (moved here from Phase 5 on 2026-10-07), making T080 pass. Complete judgement handling in `src/hipstraw_mm/steps/review.py`:
  - validate `citedEvidenceIds` against the passing evidence ("judgement cited unknown evidence" → `needs_verification`);
  - apply the invariant "`include` requires every rule to pass and `judgement.falsifierMet == false` and `judgement.fitHolds == true`";
  - store `judgement` with `model`.
- [ ] T085 [US1] Make the real model recordings again with `tests/fixtures/record_real.py` and real keys, for the three schemas that changed (`ListingExtraction`, `HomepageIdentity`, `CompanyEvidence`), so that `tests/contract/test_adapters_real.py` passes (Constitution IV, research R11). Needs a team member with keys.
- [ ] T055 [US1] *(after demo)* First write `tests/integration/test_budget_exhaustion.py` and get approval. It covers two cases:
  - With `verifyFetchesPerRun: 5` in the test config, the `us1` run runs out during `verify` with companies still unverified, so it exits with code 4, the run status is `failed`, and partial counts are recorded.
  - A run whose `QueryPlan` returns more queries than `discoveryQueries` drops the extras and completes with exit code 0.

  Then make `src/hipstraw_mm/steps/verify.py` exit with code 4 and mark the run `failed` (with `errorStep: verify` and partial counts) when it runs out of `verifyFetchesPerRun` or `verifyModelCallsPerRun` with companies still unverified. `src/hipstraw_mm/steps/discover.py` keeps treating its limits as normal completion (contracts/cli.md).
- [ ] T057 [US1] *(after demo)* First write `tests/unit/test_log_events.py` and get approval. Then emit a JSON log event for each search, fetch, model call, and failed check in `src/hipstraw_mm/steps/discover.py` and `src/hipstraw_mm/steps/verify.py`, via `src/hipstraw_mm/logging_setup.py`.
- [ ] T058 [US1] Run `pytest tests/` and confirm the Phase 3 and Phase 4 tests pass (except the after-demo tests not yet written)

**Checkpoint**: User Story 1 is complete for the demo. Discovery keeps the companies that best match
the first position; findings are bounded and evidenced, and none is included without Review.

---

## Phase 5: User Story 2 - Market Manager reviews every company record (Priority: P2)

**Goal**: The full Review step:
- the rule gate from research R9;
- a validated judgement that can only keep or downgrade;
- reasons that address conflicts.

The integration suite and the split store views come after the demo.

**Independent Test**: `pytest tests/unit/test_rule_gate.py tests/unit/test_judgement_validation.py`
(demo), plus `tests/integration/test_us2_review.py` (after demo).

### Tests for User Story 2 (write first; they must fail)

- [ ] T059 [P] [US2] Complete `tests/unit/test_rule_gate.py` (started in T079 with the website, headquarters, name–domain, and parent rows) with one case per remaining row of the research R9 table:

  | Condition | Expected disposition |
  |-----------|---------------------|
  | Registry-only (`no_website`) | `needs_verification` |
  | Website loads, existence citation failed | `needs_verification` |
  | Only over-threshold size | `exclude` |
  | Size conflict | `needs_verification` |
  | No size signal | `needs_verification` |
  | No interest signal, all else met | `needs_verification` |
  | All rules pass | goes on to judgement |
- [ ] T060 [P] [US2] Unit tests in `tests/unit/test_judgement_validation.py` (the cited-ID case moved to T080 on 2026-10-07):
  - `falsifierMet` → `exclude`.
  - `fitHolds == false` → `needs_verification`.
  - A judgement can never make a rule-gate failure `include`.
  - `judgement` is `null` when the rule gate decided.
- [ ] T061 [US2] *(after demo)* Integration test `tests/integration/test_us2_review.py`, using the scenario `tests/fixtures/scenarios/us2.yaml` built into `tests/fixtures/recorded/us2/`. The records are:
  - fully proven;
  - failed citation;
  - size conflict;
  - large-enterprise parent;
  - a fictional over-threshold company `omega-enterprise.test` whose about page says "4,800 employees" (G1; expected `exclude`, standing in for a Fortune 500 company);
  - no interest signal;
  - falsifier met.

  Assert:
  - each gets its expected disposition and a non-empty reason;
  - the size-conflict reason mentions both values (FR-015);
  - the reviewer is `market-manager/rules-v1+<model>`;
  - a second `review` exits with code 2;
  - the store view given to `discover` and `verify` has no method that writes `reviewDecisions`.
- [ ] T062 [US2] Run the new tests to confirm they fail, then present `tests/unit/test_rule_gate.py` and `tests/unit/test_judgement_validation.py` (and, after the demo, `tests/integration/test_us2_review.py`) for **user approval** (Constitution III)

### Implementation for User Story 2

- [ ] T063 [US2] *(after demo)* Split the store access in `src/hipstraw_mm/store/base.py`:
  - `FindingStore`, passed to `discover` and `verify`, has no decision or baseline write methods;
  - `ReviewStore`, passed only to `review`, adds `create_review_decision` and `create_position_baseline`.
- [ ] T064 [US2] Complete the rule gate in `src/hipstraw_mm/steps/review.py` with the rest of the research R9 table. The website, headquarters, name–domain, and `large_enterprise` rows come earlier, in T083, T052, T084, and T053. Write `ruleResults` entries `{rule: existence | hq | size | large_enterprise | interest_signal, outcome: pass | fail | unknown | conflict, evidenceIds[]}`, and make reasons name the failed rule and any conflicting values (FR-015).
- T065 moved to Phase 4 on 2026-10-07 (cited-ID validation, after T054).
- [ ] T066 [US2] Run `pytest tests/` and confirm all tests written so far pass

**Checkpoint**: Review is ready for the demo. Only Review includes companies, and every disposition has
a reason backed by evidence.

---

## Phase 6: User Story 3 - Demo report, stored records, and baseline snapshot (Priority: P3)

**Goal**: The full markdown report (all 11 sections), the `show` command, a tested immutable baseline,
and the privacy guard. The whole phase comes after the demo; the thin report from T043 serves the
demo.

**Independent Test**: `pytest tests/integration/test_us3_report.py
tests/integration/test_baseline_immutable.py` passes using the `us1` and `us2` recorded scenarios.

### Tests for User Story 3 (write first; they must fail)

- [ ] T067 [P] [US3] *(after demo)* Integration test `tests/integration/test_us3_report.py`:
  - The report has the 11 sections from contracts/demo-report.md, in order.
  - Each company appears in exactly one of sections 6, 7, and 8, and registry-only companies appear only in section 7.
  - The citations table shows the URL, the date (or "unknown"), the reliability, and the quoted excerpt.
  - There is one traceability line per included company.
  - The footer has the baseline ID and the report SHA-256, and `demoReports.sha256` matches the file.
  - **Privacy (FR-018)**: no email address, no phone-number pattern, and no person field anywhere in the report or stored records. The recorded person-name excerpt from `us1` is allowed and does appear inside its quoted excerpt.
- [ ] T068 [P] [US3] *(after demo)* Integration test `tests/integration/test_baseline_immutable.py`:
  - A second run leaves the first run's `positionBaselines/{runId}` unchanged.
  - A direct second `create` raises an error.
  - `hipstraw-mm show --run <runId> --json` returns the status, counts, and every disposition after the run.
- [ ] T069 [US3] *(after demo)* Run the new tests to confirm they fail, then present `tests/integration/test_us3_report.py` and `tests/integration/test_baseline_immutable.py` for **user approval** (Constitution III)

### Implementation for User Story 3

- [ ] T070 [US3] *(after demo)* Complete `src/hipstraw_mm/steps/report.py` with sections 9 (unknowns and conflicts), 10 (traceability), and 11 (footer with the baseline ID, SHA-256, and the fixed statement) from contracts/demo-report.md. Refuse to write the report (exit code 1, message to stderr) if the rendered text matches an email or phone pattern. Person names inside quoted excerpts are allowed (FR-018).
- [ ] T071 [US3] *(after demo)* Implement `show --run` in `src/hipstraw_mm/cli.py`: human output lists the status, counts, and one line per company with its disposition; `--json` follows the contracts/cli.md shape and adds a `companies` list
- [ ] T072 [US3] *(after demo)* Run `pytest tests/` and confirm the whole default suite passes with sockets blocked

**Checkpoint**: All three user stories are complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T073 [P] *(after demo)* Make `ruff check src tests` and `mypy src` pass, fixing issues in `src/hipstraw_mm/`
- [ ] T074 Start the emulator (`firebase emulators:start --only firestore --project demo-hipstraw-mvp`), set `FIRESTORE_EMULATOR_HOST=127.0.0.1:8085`, and run `pytest --emulator tests/contract`. Fix any difference between `src/hipstraw_mm/store/firestore.py` and `src/hipstraw_mm/store/memory.py`.
- [ ] T075 Team confirmations before the live run, recorded in `specs/002-objective-to-target-companies/validation.md`:
  - the Brave key is active and its plan permits storing result URLs;
  - `config/programs/invoice_alpha.yaml` matches https://kozmo.ai/invoice-alpha-genesis.html;
  - the `config/metros.yaml` CSA data has been checked;
  - each `denylistDomains` and `sourceTypeDomains` entry has been reviewed against that site's terms;
  - the contact URL in `userAgent` has been replaced.
- [ ] T076 Do the live demo run per quickstart.md §4 with a hand-written `positions/first_position.yaml`. Then run quickstart.md §5 (SC-001 to SC-006 and the privacy check) and record the results, the `runId`, and the report path in `specs/002-objective-to-target-companies/validation.md`.

---

## Later (beyond the slice; not part of this feature)

These are recorded so they aren't lost. Each needs its own spec or a spec change first.

- **Feature 003**: generate and select candidate micro-markets from the six experiment contexts with
  feature 001's seed graph capability (caps: 5 generated, 2 selected).
- **Feature 004**: campaign handoff package. Open questions: the fields the campaign side needs, and
  whether needs-verification companies are handed off.
- **Position versioning loop**: compare later positions against `positionBaselines`, and map them
  onto `hipstraw-faculty`'s `marketCandidates/{id}/positionHistory/mpv_N`.
- **Follow-up for needs-verification and registry-only companies**: a targeted re-verification run.
- **More evidence types**: PDF documents, and facts shown only in images or tables (today they become
  unknowns).
- **More search providers**: Tavily or SerpAPI behind `adapters/search.py`.
- **Resuming a failed run** from its failed step.
- **Other experiment contexts**: running the other five contexts, and more than one micro-market per
  run.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** has no dependencies. T001 comes first.
- **Phase 2 (Foundational)** depends on Phase 1 and blocks everything after it. T030 needs a team
  member with real keys.
- **Phase 3 (End-to-end path)** depends on Phase 2.
- **Phase 4 (US1)** depends on Phase 3. **Phase 5 (US2)** depends on Phase 3, and on Phase 4 for
  realistic `hq`, `size`, and `parent` values. Its unit tests can start right after Phase 3.
  **Phase 6 (US3)** depends on Phases 4 and 5.
- **Phase 7**: T074 needs Phase 2's stores. T075 can run any time. T076 needs every demo-path task.

### Within each phase

- Tests are written first, confirmed failing, and approved by the user (T016, T035, T051, T062, T069)
  before any implementation task in that phase. After-demo tasks that add behavior include their
  own test-first step.
- Order within a phase: models and schemas → evidence helpers → steps → CLI wiring.

### Key task dependencies

- T018 → T019, T021, T024. T021 → T022, T023.
- T024 → T025, T026, T027 → T030 → T031 (T015 passes only after T030). T028 → T030.
- T036 → T037 → T038 → T040 → T041 → T042 → T043 → T044.
- Phase 4 implementation order (2026-10-07): T082 → T083 → T052 → T084 → T053 → T056 → T054 → T065 →
  T085. T082 changes the listing and homepage schemas that every new scenario needs; T053 changes
  `CompanyEvidence`; T085 records the changed schemas for real.
- T077 → T082. T078 → T083, T084. T046 → T052. T047 → T053. T048 → T054. T080 → T065. T061 → T063.

---

## Parallel Opportunities

### Phase 2

```text
Tests together:  T009, T010, T011, T012, T013, T015
Code together:   T017, T018, T020, then T022, T023 (after T021), then T025, T026, T027, T028
```

### Phase 3

```text
Tests together:  T033, T034 (after the T032 fixtures)
Code together:   T037 with T039 (different files), while T036 → T038 run in sequence
```

### Phase 4 (User Story 1)

```text
Tests together:  T077, T078, T046, T047, T048, T079, T080 (then T049 → T081, T050)
Code:            in the listed order; T052 (location.py) can run beside T083 (verify.py, fetch.py)
```

### Phases 5 and 6

```text
Tests together:  T059, T060 (demo); T067, T068 (after demo)
```

---

## Implementation Strategy

### Live demo first

1. Run the demo-path tasks in ID order, skipping those marked *(after demo)*.
2. **Stop and validate**: T076 is the live run on Invoice Alpha, checked against SC-001 to SC-006.

### Then complete the feature

1. **After-demo US1**: exit code 4 when a verify ceiling runs out (T055), and per-event logs (T057).
2. **After-demo US2**: the integration suite with the over-threshold company (T061) and the split
   store views (T063).
3. **US3**: the full report, `show`, the baseline test, and the privacy guard (T067–T072).
4. **Polish**: the README (T008), and lint and type checks (T073).

### Notes

- Every synthetic fixture uses `.test` domains and fictional names. Real data appears only in
  `tests/fixtures/recorded/real/` (adapter contract tests) and in live runs.
- Commit after each task or logical group (the repository is created in T001), and stop at any
  checkpoint to validate.
- Only Review writes dispositions or the baseline. If a task seems to need that elsewhere, stop and
  check spec FR-011.
