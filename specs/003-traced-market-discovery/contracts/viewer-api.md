# Contract: read-only trace viewer

`hipstraw-mm view` starts a small web server for the local emulator's stored state (research R17). It
reads and shows; it never writes (FR-028, Constitution XIII).

## Guarantees

| Item | Contract |
|------|----------|
| Bind | `127.0.0.1` only (`viewer.host` must be a loopback address). No sign-in. |
| Methods | `GET` and `HEAD`. Every other method on every path returns `405` with `Allow: GET, HEAD`. |
| Host | A request whose `Host` header is not `127.0.0.1`, `localhost`, or the configured host returns `403`, to block DNS-rebinding reads of traces from a web page. |
| Store | The server holds a `ReadStore` (read methods only). It has no method that writes, edits, or deletes, and no way to start or stop a pipeline step. |
| Data | Only what the pipeline stored. Nothing is computed that is not stored, except grouping, sorting, and counting. |
| Secrets | Traces contain none (FR-024). The server adds nothing: it never reads environment variables or config files that hold secrets. |
| Errors | Unknown run or step: `404` with `{"error": "..."}`. Store unavailable: `503`. |

## Pages

| Path | Page |
|------|------|
| `/` | The single-page viewer (HTML, plain JavaScript, no build step). Views are switched in the page; the address keeps `#run=<id>&view=<name>`. |

Views: **Runs** (list), **Timeline** (steps grouped by layer), **Step** (all FR-023 fields), **Graph**
(seed graph, validation, path status), **Beam** (per level), **Companies** (companies, evidence, buyer
roles, Review decisions), **Status** (Market Status and per-path decisions; when the run has a
`finalPathShortfall` — fewer than `finalPaths` reached the final level, or none did — the view shows it
with `wanted`, `found`, and `reason`, so a shortfall is never silently absent from the decisions shown).
Empty states say so ("No runs yet", "No steps yet").

## JSON API (all `GET`)

All responses are JSON, UTF-8. `<id>` is a `marketRunId`.

| Route | Returns |
|-------|---------|
| `/api/runs` | `[{marketRunId, status, programId, model, createdAt, counts, marketStatus}]`, newest first |
| `/api/runs/<id>` | the `marketRuns` document, plus `layersOrder` from `layers.yaml` |
| `/api/runs/<id>/steps?after=<seq>` | trace step summaries with `seq > after` (default 0), ascending, each without blobs: every FR-023 field except the prompt and response bodies, plus `promptBlobId` and `responseBlobId`. Includes `running` steps. A step that was `running` when listed is sealed later without getting a new `seq`, so the page re-reads it with `refresh` (next row). |
| `/api/runs/<id>/steps?refresh=1,4,9` | the current state of the listed steps (used to update steps shown as `running`) |
| `/api/runs/<id>/steps/<seq>` | one step, complete |
| `/api/blobs/<blobId>` | `{blobId, kind, content, truncated, bytes}` |
| `/api/runs/<id>/deliberations` | the 19 dimension records with items, checks, and repair counts |
| `/api/runs/<id>/graph?version=<n>` | the seed graph (latest version by default) with `structural`, `coverage`, `unresolved`, `excluded`, and each path's status; plus `versions: [n, ...]` |
| `/api/runs/<id>/paths` | all stored paths with status, reason, history, `pathsBelow`, `meanLinkConfidence`, `searchScore`, `assessments`, `verification` |
| `/api/runs/<id>/beam` | the `beamLevels` records in level order |
| `/api/runs/<id>/links` | the `linkChecks` |
| `/api/runs/<id>/companies` | `marketCompanies` with, for each link, the child run's company record, evidence list, buyer roles, and Review decision |
| `/api/runs/<id>/decisions` | `pathDecisions`, `marketStatus`, and `finalPathShortfall` (null when `finalPaths` was fully reached) |

## Live updates

The page polls every `viewer.pollSeconds` (default 2): `steps?after=<last seq>` for new steps and
`steps?refresh=<running seqs>` for steps it shows as running. A step is visible as soon as its start
record is stored. The longest delay from storing to display is therefore about two seconds plus the
request time, inside FR-027's five seconds (SC-008).

## Separate measures (FR-029)

Three different measures never share a field, a column, or a combined number:

| Measure | JSON field | Meaning | Label in the page |
|---------|-----------|---------|-------------------|
| Search score | `searchScore` and `factors.*` | how worth searching a path looks (hypothesis) | "Search score (not evidence)" |
| Link confidence | `linkConfidence`, `meanLinkConfidence` | how well a graph link is argued | "Link confidence" |
| Evidence confidence | `evidenceConfidence` (`{value, band}`, from feature 002's company `confidence`) | how well a company's facts are cited | "Evidence confidence" |

The API renames feature 002's company field `confidence` to `evidenceConfidence` in its responses so the
bare word "confidence" never labels a search score.

## Out of scope

Any route or control that creates, edits, or deletes data, runs or stops a step, exports files, or reads
from another machine (FR-028, FR-030).
