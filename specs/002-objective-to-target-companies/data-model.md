# Data Model: Find and Review Target Companies for a Micro-Market

**Feature**: 002-objective-to-target-companies | **Storage**: Firestore emulator, project
`demo-hipstraw-mvp` (see research R10)

Collection names follow the `hipstraw-faculty` camelCase style. Every document carries `createdAt`
(a server timestamp). The in-memory store used by hermetic tests implements the same interface.

## Collection tree

```text
programs/{programId}                  Program objective, contexts, interests, default constraints
marketCandidates/{candidateId}        One per experiment context (copied from the program, not generated)
runs/{runId}                          One run: first position, constraints in force, step status
companyRecords/{runId}__{domainKey}   Findings for one company in one run (input to Review)
evidence/{evidenceId}                 One citation, with its check result
reviewDecisions/{runId}__{domainKey}  One Market Manager disposition per company record
positionBaselines/{runId}             Immutable baseline snapshot of the first position
demoReports/{runId}                   Metadata for the markdown demo report
```

`domainKey` is the website's host in lowercase, with a leading `www.` removed and dots replaced by `-`
(`www.Acme.test` → `acme-test`). This approximates the registrable domain without a public-suffix
dependency. It is the company's identity, so the same company is never recorded twice in a run
(FR-005).

A company found only on a registry page, with no website, gets `domainKey` = `registry-` plus its
name in lowercase with every run of non-alphanumeric characters replaced by `-` (for example,
`registry-zeta-holdings-llc`). Such records are always dispositioned needs verification (FR-008).

**Registry-only record contents (FR-005)**: `fitClaims` and `interestSignals` are empty, `falsifier`
is null, and `unknowns` includes `fit`, `interestSignal`, and `falsifier`, plus every minimum-proof
item without a passing citation.

**Merge rule (FR-005)**: Discovery applies this before writing any record. If the run also has a
website record whose normalized company name equals the registry-only company's normalized name, the
registry-only record is dropped and its origin evidence is not written. A normalized name is:
- `casefold()`;
- with punctuation removed and whitespace collapsed;
- with one trailing legal suffix removed (`inc`, `incorporated`, `llc`, `ltd`, `limited`, `corp`,
  `corporation`, `co`, `company`, `lp`, `llp`, `plc`).

For example, "Alpha Ledger, Inc." and "Alpha Ledger" both normalize to `alpha ledger`.

## programs/{programId}

| Field | Type | Rule |
|-------|------|------|
| `programId` | string | `invoice_alpha_genesis` |
| `name` | string | "Kozmo Invoice Alpha Genesis Cohort" |
| `objective` | string | From config (research R15) |
| `sourceUrl` | string | The Kozmo program page |
| `experimentContexts` | list of `{id, label}` | Exactly the six contexts |
| `primaryInterests` | list of `{id, label}` | Exactly the six interests |
| `defaultConstraints` | map | `{maxEmployees, maxRevenueUsd, metroIds[]}` from config |

## marketCandidates/{candidateId}

| Field | Type | Rule |
|-------|------|------|
| `candidateId` | string | `<programId>__<experimentContextId>` |
| `programId`, `experimentContextId`, `label` | string | |
| `origin` | enum | Always `program_experiment_context` (no generation, FR-019) |

## runs/{runId}

| Field | Type | Rule |
|-------|------|------|
| `runId` | string | `run_<UTC yyyymmddThhmmss>` |
| `programId`, `candidateId` | string | `candidateId` must exist |
| `position` | map | The first position: `{segment, companyArchetype, buyer, problem, trigger, primaryInterestIds[], searchHints[]}`. Every field is required except `searchHints`. |
| `constraintsInForce` | map | `{maxEmployees, maxRevenueUsd, metros[{id, csaCode, name}]}`, copied from config when the run is created (FR-001) |
| `budgets` | map | A copy of the config budgets (research R13) |
| `model` | string | The model name in force |
| `status` | enum | See the state transitions below |
| `stepTimes` | map | `{discoveredAt, verifiedAt, reviewedAt, reportedAt}` |
| `counts` | map | `{searches, fetches, modelCalls, candidatesFound, returned, shortfall}` |
| `shortfallReason` | string or null | Required when `returned < 10` (FR-004) |

### Run state transitions

```text
created → discovered → verified → reviewed → reported
   any step failure → failed (with errorStep, errorMessage); a failed run is never resumed silently
```

Each CLI step requires the previous status (contracts/cli.md, exit code 2 otherwise).

## companyRecords/{runId}__{domainKey}

| Field | Type | Rule |
|-------|------|------|
| `runId`, `candidateId` | string | |
| `name` | string | As written in its origin source |
| `domain` | string or null | The company's own website domain. Null only for a registry-only company. |
| `origin` | map | `{kind: listing_link \| profile_hop \| direct_homepage \| registry_only, searchQuery, resultUrl, listingEvidenceId, profileUrl}`: the retrieved source the company came from (FR-006). `profileUrl` is set only for `profile_hop`. |
| `identifierCheck` | map | `{status: resolves \| fails \| no_website, httpStatus, finalUrl, failReason, checkedAt}` (FR-008). `failReason` is the fetcher's reason (for example `robots_disallowed`) when the website did not load. `resolves` needs a 2xx response from the company's own website, with redirects only within the same company key or its subdomains. `no_website` is used for registry-only companies, which are never fetched. |
| `existenceEvidenceId` | string or null | The `existence` evidence document built from the homepage (FR-016). Null when the website did not load or the company has no website. |
| `hq` | map | `{city, state, status: met \| not_met \| unknown, evidenceIds[]}` (research R5) |
| `size` | map | `{signals[{kind: employees \| revenue, low, high, evidenceId}], status: under \| over \| conflict \| unknown}` (research R6) |
| `parent` | map or null | `{name, evidenceIds[], status: none \| large \| unknown_size}` |
| `fitClaims` | list | `{aspect: buyer \| problem \| trigger, statement, primaryInterestIds[≥1], evidenceIds[]}` (FR-005) |
| `interestSignals` | list | `{kind: pain \| exploration, statement, evidenceIds[≥1]}` (FR-020) |
| `unknowns` | list | `{field, reason}`. Covers every required item that has no passing citation, including `interestSignal` when the list is empty (FR-009, FR-020). |
| `falsifier` | string or null | What evidence would show the company does not fit (FR-005). Null only for registry-only records. |
| `confidence` | map | `{value 0–1, band: High \| Medium \| Low}`, computed (research R8) |
| `status` | enum | Always `finding` (FR-011). There is no `included` value on this collection. |

**Validation**:
- Every `evidenceIds` entry must reference an `evidence` document for the same run.
- A claim whose citations all failed must not appear in `fitClaims` or `interestSignals`; it goes to
  `unknowns` (FR-007, FR-009).
- A claim may cite several evidence documents. Conflicting values stay as separate signals and are
  never merged (FR-010).

## evidence/{evidenceId}

| Field | Type | Rule |
|-------|------|------|
| `evidenceId` | string | `ev_<runId>_<seq>` |
| `runId` | string | |
| `companyRecordId` | string or null | Null for listing-page evidence used at discovery |
| `claimField` | enum | `origin`, `existence`, `hq`, `employees`, `revenue`, `parent`, `fit_buyer`, `fit_problem`, `fit_trigger`, `signal_pain`, `signal_exploration` |
| `claimValue` | string | The structured value, for example `Atlanta, GA` or `120` |
| `url` | string | The source URL (planning input: every claim stores its source URL) |
| `sourceType` | enum | `registry`, `news`, `company_site`, `job_board`, `directory` |
| `reliability` | enum | `high`, `medium`, `low` (from source policy) |
| `publishedAt` | date or null | Null means unknown. Never guessed. |
| `fetchedAt` | timestamp | |
| `excerpt` | string | Copied verbatim from the page, at most 300 characters |
| `contentSha256` | string | Hash of the page text the check ran against |
| `check` | map | `{status: pass \| fail, reason: null \| not_retrievable \| robots_disallowed \| denylisted \| excerpt_not_found \| value_not_in_excerpt \| excerpt_too_long \| contains_contact_data}` (research R4). An excerpt over 300 characters fails with `excerpt_too_long`. An excerpt containing an email address or phone number fails with `contains_contact_data` and is stored with its excerpt replaced by `[withheld: contact data]` (FR-018). |

Evidence documents are written once and never edited.

**Existence evidence**: For each company whose website loads, the verify step builds one evidence
document with `claimField: existence`, `claimValue` = the company name, `sourceType: company_site`,
and `url` = the homepage. No model is involved. The excerpt is the text around the first occurrence
of the normalized company name in the homepage text: the containing sentence, or 100 characters on
each side if no sentence boundary is found, capped at 300 characters. If the name does not occur,
the document is stored with `check: {status: fail, reason: excerpt_not_found}` and an empty excerpt.

## reviewDecisions/{runId}__{domainKey}

Written only by the Review step. It is created once per company record and never updated.

| Field | Type | Rule |
|-------|------|------|
| `companyRecordId` | string | Must exist |
| `disposition` | enum | `include`, `exclude`, `needs_verification` (FR-012) |
| `reason` | string | Non-empty. Must address any size conflict (FR-015). |
| `ruleResults` | list | `{rule: existence \| hq \| size \| large_enterprise \| interest_signal, outcome: pass \| fail \| unknown \| conflict, evidenceIds[]}` |
| `judgement` | map or null | `{falsifierMet, fitHolds, citedEvidenceIds[], reason, model}`. Null when the rule gate already decided. |
| `evidenceIds` | list | The IDs of the record's passing evidence documents (its origin citation plus its own passing evidence), attached by the system, not the model. An `include` needs at least one. |
| `reviewer` | string | `market-manager/rules-v1+<model>` |
| `reviewedAt` | timestamp | |

**Invariants** (research R9):
- `include` requires every rule to pass and `judgement.falsifierMet == false` and
  `judgement.fitHolds == true`, and a non-empty `evidenceIds`. A judgement that would include a
  record with no passing evidence becomes `needs_verification`.
- Every `citedEvidenceId` must exist with `check.status == pass`.
- A company whose existence check fails is never `include` (FR-013).
- The `existence` rule outcome is:
  - `fail` when the website does not load (disposition `exclude`);
  - `unknown` when the company is registry-only (`no_website`), or when its website loads but the
    existence evidence failed its check (disposition `needs_verification`).

## positionBaselines/{runId}

Created at the end of the Review step with `create()`. It is never updated (FR-021).

| Field | Type |
|-------|------|
| `runId`, `programId`, `candidateId` | string |
| `position` | map (a copy of `runs.position`) |
| `constraintsInForce` | map (a copy) |
| `companies` | list of `{companyRecordId, name, domain, disposition}` |
| `baselineAt` | timestamp |

## demoReports/{runId}

| Field | Type |
|-------|------|
| `runId` | string |
| `path` | string: local markdown path, `reports/<runId>.md` |
| `sha256` | string: hash of the report file |
| `counts` | map: `{returned, included, excluded, needsVerification, shortfall}` |
| `generatedAt` | timestamp |

## Entity mapping to the spec

| Spec entity | Stored as |
|-------------|-----------|
| Micro-Market (first position) | `runs.position`, frozen in `positionBaselines.position` |
| Cohort Constraints | `runs.constraintsInForce` |
| Company / Company Record | `companyRecords` |
| Interest Signal | `companyRecords.interestSignals` + `evidence` |
| Citation | `evidence` |
| Unknown | `companyRecords.unknowns` |
| Review Disposition | `reviewDecisions` |
| Demo Report | `reports/<runId>.md` + `demoReports` |
| Baseline Snapshot | `positionBaselines` |

No collection has person fields or person entities, and none stores email addresses or phone numbers
(FR-018). The model's extraction schemas have no fields for them (contracts/llm-outputs.md). Person
names may appear only incidentally, inside verbatim excerpts.
