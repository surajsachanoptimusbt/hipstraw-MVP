# Data Model: Hipstraw G0 Campaign Strategy & Readiness Testing

All records live in the campaign SQL store (research R1). Field names are camelCase in JSON documents.
"Immutable" means the store refuses an update after insert. Every timestamp is UTC ISO 8601.

## Launch and Mandate (C1)

**Launch** (immutable): `launchId` (`lch_<timestamp>`), `tenant` (default `default`), `owner` (Sponsor
name), `market` (`US` or `IN`, from settings), `productName`, `createdAt`. The current mandate version
and the head Position are derived on read (`latest_mandate`, `head_position`), never stored twice.

**Mandate** (immutable per version): `launchId`, `version` (1, 2, ...), `createdAt`, `createdBy`,
- `product`: `name`, `description`, `website?`, `priceNote?`
- `audience`: `description`, `segments[]`
- `market`, `dayZero` (date), `objective`: `statement`, `successMeasure?`
- `strategy`: `channels[]`, `message`, `offer?`, `budget?` (`amount`, `currency`)
- `authorizedChannels[]`: channels the Sponsor allows tests on; empty means no E3 is ever eligible
- `approver` (Sponsor name), `trackingPlan?`
- `assets[]`: `assetId`, `kind` (`landing_page`, `ad_copy`, `email_copy`, `creative`, `brief`, `other`),
  `channel?`, `url?`, `text?`, `readyDate?`
- `metricsFile?`: path of the submitted CSV, with its `sha256`

Rules: `market` must be a configured launch market (FR-006). A new version copies nothing implicitly;
it is a complete mandate. Earlier versions stay readable (FR-007).

## Evidence Record and Observation (C2)

Immutable. `evidenceId` (`ev_<launch>_<n>`), `launchId`, `kind` (`asset`, `metric`, `page_read`,
`evidence_response`, `observation`), `source` (`customer_submission`, `mandate_url`, `metrics_export`),
`sourceRef` (mandate version, URL or file hash), `capturedAt`, `effectiveAt`, `provenance` (`by`,
`method`, `moveId?`), `verificationState` (`unverified`, `reported`, `observed`, `verified`, `stale`),
`uncertainty` (text), `contentHash` (sha256 of `content`), `content` (text or object), `accessClass`
(`D2` strategy and assets, `D3` metrics).

Observations (metric rows) add `metric`, `value`, `unit?`, `window` (`start`, `end`), `denominator?`,
`definition?`. Raw values are never rewritten (FR-009). Records with missing definition, window or
capture time are stored as `unverified` and M03 marks them `stale` or leaves them unverified, with a
reason.

## Campaign Position Snapshot (C3)

`positionId` (`pos_<launch>_v<n>`), `launchId`, `version`, `state` (`proposed`, `accepted`,
`superseded`), `baseVersion` (null for v1), `evidenceCutoff`, `createdAt`, `origin` (`intake` or
`reviewId`), `mechanismStamp`, `items[]`.

**Position item**: `itemId` (stable within a launch: `C01` claim, `A01` assumption, `B01` blocker,
`U01` unknown, `H01` hypothesis, `O01` observation), `kind`, `area` (`strategy` or `readiness`),
`text`, `state`, `core` (assumptions only), `evidenceRefs[]`, `setBy` (`intake` or Move ID), `note?`,
`key?` (a stable source key such as the criterion `RC01`, `DZ02:A3`, `page:<url>` or `metric:<evidence>`,
so a later run updates the same item instead of adding another).

| Kind | States |
|---|---|
| claim | `unverified`, `reported`, `contested`, `observed`, `verified` |
| assumption | `open`, `awaiting_evidence`, `supported`, `not_supported` |
| blocker | `open`, `cleared` |
| unknown | `open`, `resolved` |
| hypothesis | `proposed`, `planned`, `running`, `supported`, `not_supported`, `inconclusive` |
| observation | `observed`, `stale` |

Rules:
- An intake claim starts no higher than `reported` (FR-012). No E2 Move can set any claim above
  `reported` (FR-018, FR-033).
- Lifecycle `proposed → accepted → superseded`. Accepted snapshots are immutable (FR-013).
- The **head** is the latest accepted snapshot, or the intake proposal (v1) while none is accepted. A
  Review pins the head as its base. A commit succeeds only if the pinned base is still the head, in one
  transaction that inserts the successor as `accepted` and marks the old head `superseded`. Otherwise it
  is refused as stale.
- No field holds a score, probability, likelihood or forecast (FR-003, research R11).

## Repertoire (configuration, see contracts/config.md)

**Move Definition**: `id`, `version`, `name`, `group`, `effectClasses` (one or more of `E0`–`E3`; the
gate checks each), `eligibility` (typed checks), `inputs[]`, `transitions[]` (`{kind, from[], to[]}`),
`risks[]`, `handler`, `promptVersion` (E2 only), `producesTestPlan` (M09), `requiresApproval` (E3
only).

**Line Definition**: `id`, `version`, `name`, `stages` (list of lists of Move IDs), `useWhen`,
`excludeWhen` (typed checks with `all` or `any`), `reviewQuestion`, `endsIn: review`.

**Readiness Criteria Set**: `version`, `criteria[]` (`id`, `text`, `check`, `blockerText`),
`dependencyRules[]` (`id`, `text`, `check`, `leadDays`).

## Line Recommendation

Not stored separately. It is computed on request and copied into the tactic record when a Line is
chosen: `positionVersion`, `facts` (every fact and its value), `eligible[]` (`lineId`, `version`,
`reasons[]`), `excluded[]` (`lineId`, `version`, `reasons[]`).

## Tactic Record (C10): Line Run, Move Execution, Deviation

**Line Run**: `lineRunId` (`lrun_<launch>_<n>`), `launchId`, `lineId`, `lineVersion`,
`repertoireVersion`, `chosenBy`, `chosenRole`, `reason`, `chosenAt`, `recommendation` (above),
`basePositionVersion`, `plannedStages` (current plan after deviations), `nextStage` (index),
`state` (`opened`, `staged`, `completed`, `abandoned`), `reviewId?`.

**Move Execution**: `executionId`, `lineRunId`, `stageIndex`, `moveId`, `moveVersion`, `effectClass`,
`status` (`succeeded`, `failed`, `blocked`), `gate` (`allowed` or the refusal reason), `startedAt`,
`endedAt`, `transitions[]` (`itemId`, `fromState`, `toState`, `evidenceRefs[]`), `newItems[]` (items the
Move created), `produced[]` (record IDs), `proposals[]` (E2 output kept as proposals), `note?`, `error?`,
`traceStepId`. A Line run's working Position is its base snapshot plus every succeeded execution's new
items and transitions, in order.

**Deviation**: `deviationId`, `lineRunId`, `beforeStage`, `type` (`skipped`, `added`, `reordered`,
`stopped`), `moveId?`, `by`, `role`, `reason`, `at`.

Lifecycle: `opened` (Line chosen) → `staged` (one or more stages run) → `completed` (all stages done) or
`abandoned` (stopped, or every remaining stage removed). Both end states draft a Review (FR-026).

## Review Run (C4), Findings and Corrections (C9)

**Review Run**: `reviewId` (`rev_<launch>_<n>`), `launchId`, `lineRunId`, `question`,
`basePositionVersion`, `evidenceCutoff`, `state`, `findings[]`, `proposedItems[]` (the successor
Position's items), `scopeStatement`, `mechanismStamp`, `createdAt`, `validatedBy?`, `validatedAt?`,
`decidedBy?`, `decidedAt?`, `decisionReason?`, `committedPositionVersion?`.

Lifecycle `requested → gathering → drafted → validated → accepted | rejected | failed`:
- `requested → gathering → drafted`: the runner assembles the Review when the Line ends (research R9).
- `drafted → validated`: reviewer role only, and only when no finding is still `pending`.
- `validated → accepted | rejected`: Sponsor role only. `accepted` commits the successor (C3 rules).
- `failed`: assembly error; the Line run keeps its record.

**Finding**: `findingId` (`F01`...), `area` (`strategy` or `readiness`), `kind` (`blocker`, `gap`,
`contested`, `stale_metric`, `assumption`, `proposal`, `test_plan`, `delta`, `escalation`, `unknown`),
`text`,
`currentText`, `evidenceRefs[]`, `itemRefs[]`, `uncertainty`, `sourceMove`, `isProposal` (true when a
model produced it), `reviewState` (`pending`, `accepted`, `rejected`, `corrected`).

**Correction** (append-only): `correctionId`, `reviewId`, `findingId`, `action` (`accept`, `reject`,
`correct`), `originalText`, `newText?`, `by`, `role`, `reason`, `at`. A rejected finding is left out of
the successor Position; a corrected one is carried with its corrected text and a link to the correction.

## Supporting records

- **Test Plan**: `testPlanId`, `launchId`, `lineRunId`, `hypothesisItemId`, `hypothesis`, `cohort`,
  `method`, `successCriteria`, `stopRule`, `budget?`, `risks[]`, `state`. Full HA machine `draft →
  eligible → awaiting_approval → approved | rejected → running → evaluated | failed | cancelled`; in this
  feature only `draft` is reachable.
- **Evidence Request** (M08): `requestId`, `launchId`, `assumptionItemId`, `question`, `requestedFrom`,
  `state` (`open`, `answered`), `createdAt`.
- **Escalation** (M12): `escalationId`, `launchId`, `itemRefs[]`, `reason`, `to` (Sponsor), `createdAt`.
- **Delta** (M11): `deltaId`, `launchId`, `hypothesisItemId`, `expected`, `observedEvidenceRefs[]`,
  `attributionNotes`, `causal` (always false).
- **Report**: `reportId`, `launchId`, `positionVersion`, `renderedAt`, `path`, `sha256`.
- **Audit Event (C5)** (append-only): `eventId`, `launchId`, `at`, `actor`, `role`, `action`, `right`,
  `beforeRef?`, `afterRef?`, `reason?`, `correlationId`.

## Mechanism Stamp (C8)

`codeVersion`, `gitCommit?`, `repertoireVersion`, `criteriaVersion`, `routerVersion?`,
`promptVersions[]`, `models[]` (`configured`, `served`). Stored on every Review run and Position
snapshot.

## Trace tables

`trace_runs` (one per launch: `runId` = launch ID, `lastSeq`, `counts`), `trace_steps`, `trace_blobs`:
the same shapes the market tracer writes, so the existing trace code works unchanged (research R3).

## G0 → G1 measures (computed, not stored)

Over a period `[from, to)`: Reviews completed (accepted or rejected); findings corrected and rejected as
a share of all reviewed findings; blockers opened before Day Zero versus after (by the opening Move's
time against the mandate's Day Zero); Line runs per Line; deviations per Line, stage and type, with the
three most common reasons; model cost and elapsed time per Review (from trace steps). Each number lists
the record IDs it counted (SC-008).
