# Data Model: Traced Market Discovery Pipeline

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

New collections in the same Firestore emulator project (`demo-hipstraw-mvp`). Feature 002's collections
(`programs`, `marketCandidates`, `runs`, `companyRecords`, `evidence`, `reviewDecisions`,
`positionBaselines`, `demoReports`) are reused unchanged, except that a child `runs` document gains two
optional fields (below). Field names are camelCase, as stored.

**Write rules** (enforced by the store, as in 002):
- *create-only*: a second create raises `AlreadyExistsError`; there is no update method.
- *upsert*: replaced as a whole by the step that owns it.
- *seal-once* (trace steps only): created `running`, changed once to `ok` or `failed`, then never again.

| Collection | ID | Write rule | Written by |
|------------|----|-----------|-----------|
| `marketRuns` | `mrun_<UTC timestamp>` | upsert; `status` only through `transition_market_run` | `start`, each stage |
| `traceSteps` | `<marketRunId>__<seq 6 digits>` | seal-once | the Tracer |
| `traceBlobs` | `<marketRunId>__<seq>__<n>` | create-only | the Tracer |
| `deliberations` | `<marketRunId>__<dimensionKey>` | upsert (vichara and its repair) | `vichara` |
| `graphMeanings` | `<marketRunId>` | create-only | `meaning` |
| `seedGraphs` | `<marketRunId>__v<n>` | create-only (one version per generation or repair) | `graph`, `validate` |
| `linkChecks` | `<marketRunId>__<linkId>` | create-only | `links` |
| `paths` | `<marketRunId>__<pathId>` | upsert (status changes, with history) | `beam`, `assess` |
| `beamLevels` | `<marketRunId>__L<n>` | create-only | `beam` |
| `buyerRoles` | `<marketRunId>__<pathId>__<domainKey>` | create-only | `buyers` |
| `marketCompanies` | `<marketRunId>__<domainKey>` | upsert | `companies` |
| `pathDecisions` | `<marketRunId>__<pathId>` | create-only | `decide` |

## marketRuns/{marketRunId}

| Field | Type | Notes |
|-------|------|-------|
| `marketRunId` | string | `mrun_20261008T101500` |
| `programId` | string | the loaded program (feature 002's `programs`) |
| `objective` | map | `{text, experimentContexts[6] {id, label}, constraints}`: the **objective bundle** the vichara may use (R6) |
| `constraintsInForce` | map | as feature 002's `ConstraintsInForce` (size limits, metros, large-enterprise parents) |
| `config` | map | frozen copy of the pipeline settings used (beam width, final paths, companies per path, repair limit, caps, factor weights, thresholds, model call ceiling) |
| `model` | string or null | model name at start |
| `status` | enum | `opened`, `deliberated`, `defined`, `graphed`, `validated`, `linked`, `searched`, `assessed`, `verified`, `roled`, `decided`, `reported`, `failed` |
| `stepTimes` | map | stage name → ISO time |
| `counts` | map | `modelCalls`, `searches`, `fetches`, `traceSteps`, `paths`, `companies`, and stage counts |
| `unresolved` | list | `UnresolvedItem` (below) |
| `marketStatus` | map or null | `{state, reason, right, ruleFired, decidedAt}`; state in `progressing`, `needs-attention`, `at-risk`, `blocked`, `awaiting-evidence` (FR-022a) |
| `unassessed` | list | `[{dimensionKey: "trajectory" or "transition", reason}]` ("needs a comparison with an earlier run") |
| `errorStage`, `errorMessage` | string or null | when `failed` |
| `lastSeq` | integer | highest trace sequence number written |
| `finalPathShortfall` | map or null | when fewer than `finalPaths` reach the final level: `{wanted, found, reason}` |

**Stage machine**: `opened → deliberated → defined → graphed → validated → linked → searched → assessed
→ verified → roled → decided → reported`. Any stage may move to `failed`; a failed run cannot be resumed in this
feature. `searched` = beam done; `verified` = companies done; `roled` = buyer roles done.

### UnresolvedItem

`{kind: "dimension" | "level" | "gap", ref, reason, detail}` where `reason` is `no information in the
objective`, `excluded by filter`, or `repair exhausted` (FR-004, FR-005, FR-008, FR-011).

## traceSteps/{marketRunId}__{seq}

One record per step (FR-023). Fields that do not apply are present and empty, never omitted.

| Field | Type | Notes |
|-------|------|-------|
| `marketRunId`, `seq`, `stepId` | | `stepId` = the document ID |
| `parentStepId` | string or null | the step that opened this one |
| `layer` | enum | `market_manager`, `market_development_controller`, `search_research`, `position_evaluation`, `workers` |
| `actor` | string | declared in `config/layers.yaml` (for example `vichara`, `graph_validator`, `beam_search`, `review`, `llm_worker`) |
| `operation` | string | for example `ask_dimension`, `check_structure`, `score_level`, `decide_path` |
| `status` | enum | `running`, `ok`, `failed` |
| `inputs` | map | what the step was given: IDs and short values, not page text |
| `outputs` | map | what it produced, with the IDs of stored records |
| `decision` | string or null | the decision made, if any |
| `right` | string or null | the declared right used (from `layers.yaml`) |
| `rationale` | string or null | why, from what the step stored; never model reasoning |
| `alternatives` | list | options considered and not taken, each with a reason |
| `checks` | list | `[{name, status: "pass" | "fail", reason}]` |
| `model` | map or null | `{name, promptVersion, schema, attempt}` for a model call |
| `promptBlobId`, `responseBlobId` | string or null | links to `traceBlobs` |
| `toolCalls` | list | `[{kind: "search" | "fetch" | "model" | "store", target, status, detail, blobId?}]` |
| `cost` | map | `{inputTokens, outputTokens, usd}`; each `null` when unknown |
| `latencyMs` | integer or null | measured |
| `startedAt`, `endedAt` | ISO string, null | |
| `error` | string or null | scrubbed message when `failed` |

**Sealing**: `finish_trace_step(stepId, fields)` is valid only while `status = "running"` and sets
`status` to `ok` or `failed`, `endedAt`, and the output fields. Any later write raises
`InvalidTransitionError` (FR-025). Every string in the record has passed `scrub` (FR-024).

## traceBlobs/{marketRunId}__{seq}__{n}

`{blobId, marketRunId, stepId, kind: "prompt" | "response" | "tool_result", content, truncated, bytes}`.
`content` is JSON text. `truncated` is true when cut at 900 KB, with the original `bytes`.

## deliberations/{marketRunId}__{dimensionKey}

| Field | Type | Notes |
|-------|------|-------|
| `dimensionKey` | string | one of the 19 grammar keys |
| `items` | list | `[{itemId, question, status: "answered" | "unresolved", answer, basis[], basisCheck: {status, reason}, confidenceNote, reason}]` |
| `state` | enum | `answered`, `unresolved` |
| `repairAttempts` | integer | 0 to 3 |
| `coverage` | map | `{present: bool, relevant: bool or null, reason}` from the two checks (FR-005) |

`itemId` = `<dimensionKey>.<n>`; nodes cite these in `sourceQuestionIds`.
**Validation**: an `answered` item needs at least one `basis` excerpt and `basisCheck.status = "pass"`;
`unresolved` needs `reason`. A dimension is `answered` if it has at least one answered, grounded item.

## graphMeanings/{marketRunId}

The Market Development Controller's record (FR-006): `{levels[6] {level, dimensionKey, name, order},
relationships[] {from, to}, mandatoryFilters[] {id, appliesTo, attribute, rule}, promisingPath {factors[4]
{name, weight}, definition}, caps {nodesPerLevel, parentsPerNode}, source: "config/graph_meaning.yaml",
sha256}`.

## seedGraphs/{marketRunId}__v{n}

| Field | Type | Notes |
|-------|------|-------|
| `version` | integer | 1 = generated; later versions are repairs |
| `nodes` | list | `Node` |
| `edges` | list | `Edge` |
| `unresolved` | list | `UnresolvedItem` |
| `structural` | map | `{status, violations[] {rule, nodeId or edgeId, detail}}` |
| `coverage` | map | `{status, gaps[] {itemId, reason}}` |
| `repair` | map or null | `{attempt, addedNodeIds[], addedEdgeIds[], countedAsFailed: bool}` |
| `excluded` | list | candidates removed by a mandatory filter: `[{label, level, filterId}]` |
| `createdBy` | string | the stepId that wrote it |

### Node

`{nodeId, level, label, attributes, sourceQuestionIds[]}`.
`level` is one of `segment`, `archetype`, `problem`, `trigger`, `buyerRole`, `useCase`.
`attributes` by level: segment `{metroIds[]}`; archetype `{sizeBand}` (`startup`, `small`, `mid_market`,
`enterprise`); the others `{}` plus a short `description`.

### Edge

`{edgeId, from, to, kind}`: `from` is a node one level above `to`. `edgeId` = `<from>><to>`.

## linkChecks/{marketRunId}__{edgeId}

`{edgeId, rationale, linkConfidence (0 to 1), flagged (below the threshold), threshold, stepId}`.
`linkConfidence` is a **link** measure (how well the connection is argued from the objective), kept apart
from `searchScore` and from `evidenceConfidence` (feature 002's company confidence).

## paths/{marketRunId}__{pathId}

`pathId` = the node IDs joined with `>` and hashed to 8 hex characters; `nodeIds` holds the list.

| Field | Type | Notes |
|-------|------|-------|
| `nodeIds` | list | partial paths too (a prefix of a complete path) |
| `level` | string | the deepest level reached |
| `complete` | boolean | true when it ends at a use case |
| `status` | enum | `candidate`, `kept`, `pruned`, `deferred`, `flagged` (a complete path with a low link), `final`, `has_evidence`, `no_evidence_found` |
| `statusHistory` | list | `[{status, reason, level, at, stepId}]`, appended on each change |
| `reason` | string | the current reason (the latest history entry) |
| `pathsBelow` | integer | complete paths under this node set, counted over edges; for pruned and deferred partial paths (R11) |
| `linkIds` | list | the `edgeId`s on the path |
| `meanLinkConfidence` | number or null | shown beside the score, not part of it |
| `scores` | map or null | latest `{factors: {objectiveFit, informationValue, evidenceGap, cost} each {value, rationale}, weights, searchScore, level}` |
| `assessments` | map or null | the seven per-path dimensions: `{dimensionKey: {state, rationale, assessedBy, label: "hypothesis"}}` (FR-013) |
| `verification` | map or null | for final paths: `{evidenceSufficiency, evidenceQuality, criticalUnknowns}` each `{state, reason, assessedBy}` (FR-020) |
| `childRunId` | string or null | the feature 002 run that searched it |

**Status rules** (FR-012, FR-014, FR-018):
- a path is `no_evidence_found` only after company verification finds no verified company for a final
  path, and `has_evidence` only when at least one company on it is `include`d;
- "verified" for this purpose means passing feature 002's existence rule and Review's `include`;
- a status never goes back from `final` to `kept`.

## beamLevels/{marketRunId}__L{n}

For one level: `{level, beamWidth, candidates[] {pathId, extendsPathId, nodeId, filter: {status, reason},
factors, searchScore, diversity: {status, duplicateOf}, outcome: "kept" | "pruned" | "deferred", reason,
pathsBelow, rank}, keptPathIds[], stepIds[]}`. This is what the beam view reads (FR-026).

## buyerRoles/{marketRunId}__{pathId}__{domainKey}

`{pathId, companyRecordId, roles[] {function, authority, evidenceIds[]}, unknown: null | {reason}}`.
`authority` is `owns_budget`, `approves`, `uses`, or `influences`. There is no field for a person's name,
email address, or phone number (FR-021, FR-030); every `evidenceId` is a passing evidence document of that
company.

## marketCompanies/{marketRunId}__{domainKey}

`{domainKey, name, domain, links[] {pathId, childRunId, companyRecordId, disposition}, conflict: bool}`.
`conflict` is true when two links have different dispositions; both are kept (Constitution VIII).

## pathDecisions/{marketRunId}__{pathId}

`{pathId, decision: "pursue" | "needs more evidence" | "drop", reason, right, ruleFired, inputs {…}, decidedAt, stepId}`.
Written only by the Market Manager step (Constitution VI).

## Changes to feature 002 documents

- `runs`: optional `parentMarketRunId` (string) and `pathId` (string) on child runs.
- `marketCandidates`: child runs reuse this collection with one synthetic record per final path,
  `origin: traced_path` (a new literal added to `MarketCandidate.origin`, additive), `candidateId` =
  `<marketRunId>__<pathId>`, and `experimentContextId` set to the path's `pathId`.
- `evidence` and `companyRecords`: unchanged.
- Model recordings gain an optional `usage` object (token counts) on **new** recordings only.

## Relationships

```text
marketRuns 1─* traceSteps 1─* traceBlobs
marketRuns 1─* deliberations ──(sourceQuestionIds)── seedGraphs.nodes
marketRuns 1─1 graphMeanings;  marketRuns 1─* seedGraphs (versions)
seedGraphs.edges 1─1 linkChecks
marketRuns 1─* paths 1─* beamLevels.candidates
paths(final) 1─1 runs(child) 1─* companyRecords ─ evidence ─ reviewDecisions
paths(final) 1─* buyerRoles;  marketCompanies ─ companyRecords (several child runs)
paths(final) 1─1 pathDecisions;  marketRuns.marketStatus
```

## Validation summary

- IDs are deterministic from the run, so replays and tests are stable.
- Every record that came from a model call stores the trace step ID (`stepId`) that produced it, so a
  viewer can jump from any value to its step.
- No stored record contains a secret (FR-024) or a person's name, contact, or email as a field (FR-030).
