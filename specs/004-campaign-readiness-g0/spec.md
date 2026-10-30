# Feature Specification: Hipstraw G0 Campaign Strategy & Readiness Testing

**Feature Branch**: `004-campaign-readiness-g0`

**Created**: 2026-10-29

**Status**: Draft

**Input**: User description: "Hipstraw G0 — Continuous Campaign Strategy & Readiness Testing (vertical
slice), built as a separate module for Hipstraw (not shared with Zimplii)." (Full description, with
the first-release repertoire, the eight-step flow, the fixed core C1–C10 and the model-use rules, as
supplied on 2026-10-29.)

## References

- **HA**: `docs/Hipstraw Faculty Harness — Evolutionary Architecture.pdf` (28 October 2026). Sections
  1 (scope statement), 4 (fixed core C1–C10), 5 (Moves, Lines, effect classes), 6 (domain model),
  8 (lifecycle and state machines), 9 (data classes, roles), 12 (fixtures and checks), 13 (decisions
  HR01–HR12) and 14 (open questions HQ1–HQ7).
- **Method Compiler spec**: `docs/Hipstraw Method Compiler — Architecture Specification.pdf`. Used here
  only for what G0 must record so G3 can start later: stable Move and Line IDs, versioned definitions,
  and the tactic record (C10). The compiler itself is G3 and out of scope.
- **Repertoire summary**: `docs/hipstraw_campaign_review_repertoire.xlsx - Summary.pdf`. It counts 29
  first-release Moves and 6 Lines; the full sheet is not yet in the repository, so this feature starts
  from HA section 5 (12 Moves, 5 Lines) and loads the repertoire from versioned configuration.
- **Meetings**: 27 and 28 October 2026. G0 is the first release; launch markets are the US and India
  first; a human review queue checks every G0 Review; Lines and Moves come from the team's own
  methodology, not from a model; the compiler arrives only at G3; whether G0 shows a readiness score is
  deferred to the product owner.
- **Constitution v1.2.0**: II (CLI), III (test-first), VI (Faculty Systems loop), VII (no agent SDK),
  VIII (evidence provenance), IX (real-world data integrity), X (smallest units), XI (Jev deferred),
  XII (traceability), XIII (read-only viewer), XIV (layer boundaries).
- **Separation**: this is Hipstraw's own module. It shares no code path with Zimplii and does not change
  the market discovery pipeline (features 002 and 003).

## Clarifications

### Session 2026-10-29

- Q: Without a readiness score, how does G0 say whether a campaign is good for its audience and market?
  → A: A versioned **campaign rubric** of plain questions (audience, problem, value, offer, proof, channel
  fit, consistency across assets, market fit). M06 judges each question as `met`, `partly`, `not met` or
  `unknown`, quoting the campaign word for word and naming a fix. There is no total or score; each verdict
  is a finding the reviewer can accept, correct or reject.
- Q: Which scenario first? → A: One scenario: the Kozmo Invoice Alpha launch campaign in the US (New York,
  San Francisco and Atlanta metros). India uses the same rubric later.
- Q: Does M02's model summary ship first? → A: No. M02 reads the mandate's pages as evidence; M06 judges the
  rubric directly on that evidence. M02's summary step follows later.

### Session 2026-10-30

- Q: Where does a campaign start? → A: From its channels. The launch file names each channel (email,
  LinkedIn ads, Instagram ads, Reddit ads) with who it reaches, its budget, success measure, setup facts and
  its own assets. A vague channel ("paid social") or a channel with no stated audience is an unknown from
  submission (FR-052).
- Q: How does G0 say whether the message is right for the audience? → A: Per channel. Rubric v0.2 judges five
  questions for every channel, led by "Message fits the audience" and "Channel reaches the audience" (judged
  against each channel's reach notes), and four for the whole campaign (FR-053).
- Q: How are the industry's own checks covered? → A: Channel standards in versioned config, each check with its
  source (platform rules, the law, practice), run by a deterministic Move, M13 Check channel standards, in L01.
  A `must` not met opens a blocker; a `must` not stated opens an unknown; a `should` not met is a fix for the
  Review (FR-054).
- Q: Which scenarios? → A: Kozmo on one channel (email) first, then the same campaign on three channels to show
  how one message is judged differently per channel (`docs/campaign_channel_scenarios.md`).
- Q: Separate views for the customer, the reviewer and the report? → A: Yes, as three views of the read-only
  page (Report, Campaign, Reviewer desk) plus an Audit view. Decisions stay in the CLI (constitution XIII);
  the desk shows the command. Writing from the page needs a constitution decision (FR-055).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit a launch and see the first Campaign Position (Priority: P1)

A Sponsor (the customer's GTM leader) submits a launch: the product, the target audience, the market,
Day Zero and the objective, the campaign strategy (channels, message and offer, budget, authorized
channels), the campaign assets (landing page address, ad copy, email copy, creative descriptions) and,
if the campaign is already live, a metrics export. Hipstraw records the launch mandate, captures every
asset as an evidence record, and builds a first **proposed** Campaign Position that keeps provided
claims, verified evidence, open assumptions, blockers and unknowns apart, each tied to its evidence.

**Why this priority**: Every later step reads the mandate, the evidence and the Position. Without them
there is nothing to test, review or report.

**Independent Test**: Submit one launch file and read back the mandate, the evidence records and the
proposed Position. Every claim cites an evidence record; every required input that is missing appears
as an explicit unknown.

**Acceptance Scenarios**:

1. **Given** a complete launch submission, **When** it is submitted, **Then** a Launch with a versioned
   mandate exists, each asset is an immutable evidence record with source, capture time, provenance and
   verification state `reported`, and a Position snapshot in state `proposed` lists claims, assumptions,
   blockers and unknowns with evidence references and an evidence cutoff.
2. **Given** a submission without a landing page address, **When** it is submitted, **Then** the launch
   is accepted, the missing landing page is recorded as an unknown, and no claim about the landing page
   appears in the Position.
3. **Given** a submission whose market is not one of the configured launch markets, **When** it is
   submitted, **Then** it is rejected with a message that names the allowed markets.
4. **Given** an accepted launch, **When** the Sponsor submits a corrected strategy, **Then** a new mandate
   version is recorded and the earlier version is kept unchanged.

---

### User Story 2 - Choose a Line from the approved repertoire (Priority: P1)

The Campaign Manager asks which Lines fit this launch. Hipstraw evaluates every approved Line's
use-when and exclude-when conditions against the current Position and mandate (for example days to
Day Zero, unverified core assumptions, whether the campaign is live, whether a test channel is
authorized) and lists the eligible Lines with the reason each fits, plus the excluded Lines with the
reason each is excluded. The Campaign Manager picks one. Hipstraw records which Line and version was
chosen, by whom and why, and opens the launch tactic record.

**Why this priority**: Lines and Moves are the product's method from day one. Every Test must record
its Line so that usage can be compared later.

**Independent Test**: Load the repertoire, check it with the Line lint, ask for recommendations for a
prepared Position, pick a Line, and read back the tactic record.

**Acceptance Scenarios**:

1. **Given** the approved repertoire, **When** it is loaded, **Then** every Line passes the Line lint:
   every Move ID exists and is versioned, every external-effect (E3) Move sits behind a Test Plan approval
   step, every Line ends in a Review, and no inference (E2) output can become a Position claim without
   evidence references.
2. **Given** a repertoire file with a Line that names an unknown Move, **When** it is loaded, **Then** it
   is rejected and the error names the Line and the unknown Move.
3. **Given** a launch 7 days before Day Zero with open readiness blockers, **When** Lines are
   recommended, **Then** L01 Readiness-first is eligible with that reason, and L04 Live checkpoint is
   excluded because the campaign is not yet live.
4. **Given** a launch whose mandate authorizes no test channel, **When** Lines are recommended, **Then**
   every Line containing M10 is excluded with that reason.
5. **Given** a recommendation list, **When** the Campaign Manager picks a Line with a reason, **Then** the
   tactic record stores the Line ID and version, the chooser, the reason and the time.

---

### User Story 3 - Run the chosen Line, stage by stage, to a Review (Priority: P1)

Hipstraw runs the chosen Line's stages in order. The Moves in a stage run together; the next stage
starts when every Move in the current stage has finished. Between stages the Campaign Manager may skip a
Move, add an approved Move from the catalogue, or stop the Line, each with a reason. The Line always ends
in a Review run that proposes a successor Position with findings that separate strategy validity from
operational readiness.

**Why this priority**: This is the G0 product: testing strategy and readiness through named tactics,
with every human judgment recorded.

**Independent Test**: Run L01 Readiness-first on a prepared launch with no model calls; then run L02
Strategy validation with recorded model responses. Read back the tactic record, the Move outputs and the
Review run.

**Acceptance Scenarios**:

1. **Given** L01 chosen, **When** it runs, **Then** M01 runs first, then M04 and M05 together, then M12,
   and the tactic record lists each Move execution in order with its result.
2. **Given** a running Line, **When** the Campaign Manager skips a Move with a reason, **Then** the Move
   does not run, the deviation is recorded with its reason, and the Review still proposes a successor
   Position.
3. **Given** a Line that reaches M10 Dispatch approved test, **When** no approved Test Plan exists, **Then**
   M10 does not run, no external effect happens, and the block is recorded with its reason.
4. **Given** an inference Move (M06 or M07), **When** it runs, **Then** its output is stored as proposals
   with evidence references, it never raises any claim above `reported`, and the model call is traced
   with its prompt, structured response, cost and latency.
5. **Given** the Campaign Manager stops the Line early, **When** they stop it, **Then** the Line is marked
   abandoned in the tactic record and the run still ends in a Review on the evidence gathered so far.
6. **Given** every stage finished, **When** the Line ends, **Then** a Review run exists in state `drafted`
   that pins the base Position version and the evidence cutoff and lists findings, uncertainty, blockers,
   open assumptions and the proposed successor Position.

---

### User Story 4 - Review queue: check, correct and accept (Priority: P2)

Every drafted Review enters a review queue. A Hipstraw reviewer checks each finding and may accept it,
reject it or correct it, always with a reason; corrections and rejections are kept, never overwritten.
When the reviewer has validated the Review, the Sponsor accepts or rejects it. Only acceptance commits the
successor Position snapshot, and only against the base version the Review pinned.

**Why this priority**: G0 has no proven Lines yet. Human review is how the team learns which Lines work
and is the gate that keeps unreviewed output from becoming the Position (constitution VI).

**Independent Test**: Take a drafted Review, correct one finding, reject one, validate the Review, accept
it as the Sponsor, and read back the corrections, the audit events and the new Position version.

**Acceptance Scenarios**:

1. **Given** a drafted Review, **When** the reviewer corrects a finding with a reason, **Then** the
   original finding, the correction and the reason are all kept, and the Review shows the corrected text.
2. **Given** a validated Review, **When** the Sponsor accepts it, **Then** a new Position snapshot is
   committed as `accepted`, the previous accepted snapshot becomes `superseded`, and both remain readable.
3. **Given** a validated Review whose base version is no longer the latest accepted version, **When** the
   Sponsor accepts it, **Then** the commit is refused as stale and the Review must be re-run.
4. **Given** a drafted Review, **When** anyone tries to accept it before the reviewer validates it,
   **Then** the acceptance is refused.
5. **Given** any accept, reject, correct or choose action, **When** it happens, **Then** an append-only
   audit event records the actor, the right used, the before and after references and the reason.

---

### User Story 5 - Campaign readiness report (Priority: P2)

From an accepted Position, Hipstraw renders a report for the Sponsor: the scope statement, strategy
findings, readiness findings, blockers with what clears them, open assumptions, unknowns, the Line used
and its deviations, and the evidence behind each finding.

**Why this priority**: The report is what the customer receives and pays for in G0.

**Independent Test**: Render the report for an accepted Position and check its sections, its citations,
and that it has no score or forecast.

**Acceptance Scenarios**:

1. **Given** an accepted Position, **When** the report is rendered, **Then** it opens with the scope
   statement and every finding cites at least one evidence record or is labelled as an assumption or
   unknown.
2. **Given** any Position, **When** a report is requested before acceptance, **Then** it is refused.
3. **Given** any rendered report, **When** it is checked, **Then** it contains no readiness score, no
   success probability and no forecast.

---

### User Story 6 - Evidence for the G0 → G1 gate (Priority: P3)

The product owner asks how G0 is performing. From stored records alone, Hipstraw reports, for a period:
Reviews completed, reviewer correction and rejection rate, blockers found before Day Zero versus found
after, Line usage, deviation counts per Line stage with the most common deviations, and model cost and
elapsed time per Review.

**Why this priority**: Moving to G1 needs measured evidence (HA section 10, HQ6). Recording it from the
start costs little; reconstructing it later is impossible.

**Independent Test**: After two recorded launches, ask for the measures and check each number against
the stored records.

**Acceptance Scenarios**:

1. **Given** two launches with Reviews, **When** the measures are requested, **Then** each measure
   matches a count over the stored records and the report names the period and the launches counted.
2. **Given** a Line stage skipped in both launches, **When** the measures are requested, **Then** that
   stage shows two deviations of type "skipped" with their reasons.

---

### Edge Cases

- **Day Zero in the past**: the launch is treated as live; readiness Lines that assume pre-launch are
  excluded with that reason, and L04 Live checkpoint becomes eligible if metrics were provided.
- **Metrics export without a metric definition, window or capture time**: M03 marks the observation
  `stale` or `unverified` and records why; it never treats the numbers as observed.
- **Landing page unreachable or blocked**: M02 records the failed read as an explicit unknown with the
  reason; no claim is made about the page.
- **Contradictory evidence** (for example the brief names one audience and the ad copy another): both
  claims are kept side by side and marked `contested`; L05 Contested evidence becomes eligible.
- **A chosen Line names a Move whose handler is withdrawn**: the choice is refused; the Campaign Manager
  picks another Line or runs Moves individually, recorded as deviations.
- **Humans deviate until no stage of the Line remains**: the test continues as human-directed and the
  tactic record marks the Line abandoned.
- **Model call fails or returns output that fails its checks**: the inference Move records the failure,
  the task router escalates or the Move ends without a proposal, and the Review notes the gap; nothing
  model-produced reaches the Position without passing its checks.
- **Reviewer rejects every finding**: the Review cannot be validated as it stands; it is either re-run or
  closed as rejected, and the Position stays at its last accepted version.
- **Two Reviews race to commit**: the second commit is refused as stale (it pinned an older base).
- **A model output contains a success prediction**: the field does not exist in any structured output or
  record, so it cannot be stored or shown.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and product boundary**

- **FR-001**: Every Review and every report MUST carry the scope statement from HA section 1.
- **FR-002**: The system MUST NOT publish, send, spend, contact third parties or change budgets in this
  feature; the only external-effect Move (M10) MUST be blocked unless an approved Test Plan and an
  authorized mandate channel exist, and in this feature no approval path for E3 exists, so it always
  fails closed.
- **FR-003**: No Position, Review, report or structured model output MUST contain a readiness score, a
  success probability or a forecast field.
- **FR-004**: This feature MUST be self-contained for Hipstraw and MUST NOT change the behaviour of the
  market discovery pipeline.

**Launch intake (C1, C2)**

- **FR-005**: The system MUST accept a launch submission containing product, target audience, market,
  Day Zero, objective, campaign strategy (channels, message and offer, budget, authorized channels),
  assets, and an optional metrics export.
- **FR-006**: The system MUST reject a submission whose market is not in the configured launch markets
  (default: United States and India) and name the allowed markets.
- **FR-007**: The mandate MUST be versioned; a change creates a new version and keeps the old one.
- **FR-008**: Each asset MUST become an immutable evidence record with source, capture time, effective
  time, provenance, verification state (`unverified`, `reported`, `observed`, `verified`), uncertainty
  note and content hash.
- **FR-009**: Metric observations MUST keep the metric definition, window, denominator and capture time
  when given; raw values MUST never be rewritten.
- **FR-010**: Missing required inputs MUST be recorded as explicit unknowns, not filled by default.

**Campaign Position (C3)**

- **FR-011**: The system MUST build a first proposed Campaign Position listing claims, assumptions,
  blockers and unknowns, each with its state and evidence references, plus the evidence cutoff.
- **FR-012**: Claims taken from the customer's own submission MUST start no higher than `reported`.
- **FR-013**: Accepted snapshots MUST be immutable; a successor MUST commit only against the base version
  its Review pinned, and a stale commit MUST be refused.
- **FR-014**: Snapshot states MUST follow `proposed` → `accepted` → `superseded`.

**Repertoire: Moves and Lines**

- **FR-015**: Moves and Lines MUST be loaded from versioned configuration, so the repertoire can grow (for
  example to the workbook's first-release set) without code changes where handlers already exist.
- **FR-016**: Each Move definition MUST state ID, version, name, group, effect class (E0 internal, E1 read
  external, E2 bounded inference, E3 external effect), eligibility, inputs, the Position transitions it
  may make, risks, and the handler that implements it.
- **FR-017**: Each Line definition MUST state ID, version, name, ordered stages of Move IDs, use-when
  conditions, exclude-when conditions, and end in a Review.
- **FR-018**: The Line lint MUST reject a repertoire when any Move ID is unknown or unversioned, any E3
  Move is not preceded by a Test Plan approval step, any Line does not end in a Review, any E2 Move
  declares a transition that raises a claim above `reported`, or any Move names a handler that does not
  exist; each error MUST name the Line or Move.
- **FR-019**: The first-release repertoire MUST contain M01–M12 and L01–L05 as defined in HA section 5.

**Line choice and tactic record (C10)**

- **FR-020**: The system MUST evaluate every Line's use-when and exclude-when conditions against the
  current Position and mandate and return eligible Lines with reasons and excluded Lines with reasons.
- **FR-021**: Conditions MUST be typed checks over Position and mandate facts (for example days to Day
  Zero, count of unverified core assumptions, live or not, authorized test channel present), never model
  judgement.
- **FR-022**: A human (Campaign Manager role) MUST choose the Line; the tactic record MUST store Line ID
  and version, chooser, reason and time.
- **FR-023**: The tactic record MUST list every Move execution in order with its result, and every
  deviation (skipped, added, reordered, stopped) with actor and reason.

**Stage runner**

- **FR-024**: The system MUST run a Line's stages in order; Moves in one stage run as one group, and the
  next stage starts only when every Move in the current stage has finished.
- **FR-025**: Between stages, the Campaign Manager MUST be able to skip a Move, add an approved Move, or
  stop the Line, each with a reason recorded as a deviation.
- **FR-026**: Every Line run MUST end in a Review run, including a stopped or abandoned Line.
- **FR-027**: Every Move execution MUST pass the policy and authority gate for its effect class before it
  runs; the gate MUST fail closed when authority is missing.

**Move behaviour (first release)**

- **FR-028**: M01 MUST capture customer assets as evidence records (E0).
- **FR-029**: M02 MUST read only approved sources named in the mandate (for example the landing page) and
  may summarise them through a bounded model step; its claims MUST stay at `reported` or `contested`.
- **FR-030**: M03 MUST check each metric's identity and freshness and mark it `observed` or `stale`.
- **FR-031**: M04 MUST check the launch against a versioned readiness criteria list and open or clear
  blockers deterministically.
- **FR-032**: M05 MUST check Day Zero dependencies (deadlines and required assets) deterministically and
  open or clear blockers.
- **FR-033**: M06 and M07 MUST be bounded model steps with explicit inputs and structured output; their
  output is a proposal (findings, assumptions, gaps, variants), cites evidence, and never changes a claim
  state by itself.
- **FR-034**: M08 MUST record an evidence request against an unverified assumption, setting it to
  `awaiting evidence`.
- **FR-035**: M09 MUST draft a Test Plan (hypothesis, cohort, stop rule, budget, risks) in state `draft`;
  it MUST NOT approve it.
- **FR-036**: M11 MUST record an observation and a Delta (expected versus observed) with attribution
  notes; it MUST NOT mark a Delta as causal proof.
- **FR-037**: M12 MUST record an escalation of a blocker or contested finding to the Sponsor.

**Review run, review queue and acceptance (C4, C5, C9)**

- **FR-038**: A Review run MUST record its question, base Position version, evidence cutoff, findings
  (each marked strategy validity or operational readiness, with evidence references and uncertainty),
  blockers, open assumptions and the proposed successor Position.
- **FR-039**: Review runs MUST follow `requested` → `gathering` → `drafted` → `validated` → `accepted` /
  `rejected` / `failed`.
- **FR-040**: A reviewer MUST be able to accept, reject or correct each finding with a reason; originals,
  corrections and reasons MUST all be kept.
- **FR-041**: Only a validated Review MAY be accepted, and only by the Sponsor role; only acceptance commits
  the successor Position.
- **FR-042**: Every choose, deviate, correct, validate, accept and reject action MUST write an append-only
  audit event with actor, role, right used, before and after references, reason and correlation ID.

**Mechanism stamp, traceability and model use (C8)**

- **FR-043**: Every Review run and Position snapshot MUST carry a mechanism stamp: model family and version,
  prompt versions, repertoire version, readiness criteria version and code version.
- **FR-044**: Only E2 Moves MAY call a model, and only through the existing task router, with explicit
  inputs and structured output; every call MUST be traced with prompt, structured response, cost and
  latency, and without secrets or hidden reasoning.
- **FR-045**: Every Move execution MUST be traced with its layer, actor, operation, inputs, outputs,
  decision, checks and their results.

**Report**

- **FR-046**: The system MUST render a report only from an accepted Position, containing the scope
  statement, strategy findings, readiness findings, blockers and what clears them, open assumptions,
  unknowns, the Line used with its deviations, and evidence citations.

**G0 → G1 measures**

- **FR-047**: The system MUST compute, for a stated period and from stored records only: Reviews completed,
  finding correction and rejection rates, blockers found before versus after Day Zero, Line usage counts,
  deviation counts per Line stage and the most common deviations, and model cost and elapsed time per
  Review.

**Campaign rubric (Session 2026-10-29)**

- **FR-049**: The rubric MUST be versioned configuration: each question has an ID, area, plain question,
  what evidence it needs, what `met`, `partly` and `not met` look like, and the Move or Line that fixes a
  miss.
- **FR-050**: M06 MUST judge every rubric question once, citing evidence IDs and quoting them word for word
  for `met` and `partly`; with too little evidence the verdict MUST be `unknown`, never a guess.
- **FR-051**: Each verdict MUST become a Review finding with its quotes and fix; reports MUST show the
  verdicts question by question with no total, score or forecast.

**Channel by channel (Session 2026-10-30)**

- **FR-052**: A launch MUST name its channels, each with who it reaches, its setup facts and its own assets; a
  channel that is not a specific platform with standards on file, or that has no stated audience, MUST be an
  open unknown from submission.
- **FR-053**: Channel-scoped rubric questions MUST be judged once per channel (FR-050 applies per channel),
  led by whether the message fits the audience that channel reaches; reports MUST show each channel's
  verdicts and, with more than one channel, the channels side by side.
- **FR-054**: Channel standards MUST be versioned configuration, each check with its level (`must`: platform
  rule, law, or a fact needed to judge the channel; `should`: practice) and its source; M13 MUST apply them
  deterministically, opening a blocker for a `must` not met and an unknown for a `must` not stated.
- **FR-055**: The page MUST offer separate views for the report, the customer's campaign and the reviewer
  desk, and MUST stay read-only (constitution XIII): the desk shows the command for each decision.

**Interface**

- **FR-048**: All capabilities MUST be available from the command line, with JSON output for machine use
  and errors on stderr with non-zero exit codes. A read-only viewer page is a later unit.

### Key Entities *(include if feature involves data)*

- **Launch**: one customer launch; has an ID, tenant, owner, market and a chain of mandate versions.
- **Mandate (C1)**: versioned terms of the launch: objective, Day Zero, audiences, scope, budget,
  authorized channels.
- **Evidence Record / Observation (C2)**: an immutable captured asset or metric with source, times,
  provenance, verification state, uncertainty and hash; observations add metric definition and window.
- **Campaign Position Snapshot (C3)**: a versioned set of claims, assumptions, blockers and unknowns with
  states and evidence references, an evidence cutoff and a lifecycle state.
- **Move Definition / Line Definition**: versioned repertoire entries (see FR-016, FR-017).
- **Readiness Criteria Set**: the versioned checklist M04 applies.
- **Line Recommendation**: the eligible and excluded Lines for a Position, each with its reason.
- **Tactic Record (C10)**: the Line chosen, by whom and why; Move executions in order; deviations.
- **Review Run (C4)**: question, base version, cutoff, findings, blockers, assumptions, proposed successor,
  lifecycle state and mechanism stamp.
- **Finding and Correction (C9)**: a finding with its type (strategy or readiness), evidence and
  uncertainty; corrections and rejections with reasons, kept beside the original.
- **Audit Event (C5)**: an append-only decision record.
- **Test Plan**: a drafted, unapproved test; in this feature it can only be `draft`.
- **Escalation and Evidence Request**: records produced by M12 and M08.
- **Mechanism Stamp (C8)**: the versions of everything that produced a Review or snapshot.
- **Report**: rendered output of an accepted snapshot.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a complete launch submission, the first proposed Campaign Position is available within
  5 minutes, excluding time spent waiting for a human.
- **SC-002**: 100% of claims and findings in accepted Positions and reports cite at least one evidence
  record or are explicitly labelled as an assumption or unknown.
- **SC-003**: 0 external effects occur in this feature; 100% of attempts to run M10 are blocked and
  recorded.
- **SC-004**: 100% of executed Moves and human deviations appear in the tactic record, checked by
  comparing the tactic record with the traced Move executions.
- **SC-005**: 0 Positions, Reviews or reports contain a score, probability or forecast.
- **SC-006**: A reviewer can check, correct and validate a Review with up to 10 findings in under 15
  minutes using the command-line output alone.
- **SC-007**: Adding a new Line that uses existing Moves takes a configuration change only and passes or
  fails the Line lint with a message naming the problem.
- **SC-008**: The G0 → G1 measures for any period are produced from stored records alone, and each number
  can be traced to the records it counts.
- **SC-009**: Running L01 end to end makes no model call; a full L02 run on a typical launch costs under
  $0.50 in model calls.

## Assumptions

- **Findings only, no score**: G0 reports findings and blockers without a readiness score, as HA requires
  (section 1, HR03). The score question is with the product owner; adding one later is a new decision.
- **Roles**: the Sponsor is the customer's GTM leader and the only role that accepts a Review or would
  approve a Test Plan; the Campaign Manager chooses Lines and records deviations; the reviewer is a
  Hipstraw team member working the review queue. In G0 all three are people at the command line.
- **Repertoire source**: HA section 5's 12 Moves and 5 Lines are the starting repertoire. The workbook's
  sixth first-release Line and its extra Moves (HR08, HQ1) are loaded later as configuration once the
  sheet is shared.
- **Use-when thresholds**: "Day Zero is near" defaults to 14 days or fewer; "core assumptions
  unverified" means at least one core assumption below `observed`. Both are configuration, to be
  confirmed by the domain owner.
- **Readiness criteria**: a first, versioned criteria list (for example landing page live, tracking in
  place, budget and approver named, required assets per authorized channel, consent wording for email)
  is proposed by this feature and marked for domain-owner review.
- **Markets**: the configured launch markets are the United States and India; others are rejected in G0.
- **Data**: customer strategy and assets (D2) and metrics (D3) are in scope; personal data (D4) is not
  accepted in this feature because no E3 test runs; secrets stay in the environment only.
- **Source reads**: M02 reads only addresses named in the mandate (read-only, E1); no other connectors.
- **Live checkpoints**: L04 runs on demand when metrics are supplied; scheduled checkpoints (T0, T+7) are
  G2.
- **Out of scope**: the method compiler and adaptive selection (G3), scheduling and durable jobs (G2),
  typed Market and Launch Positions and rubrics (G1), outbox and idempotent dispatch (C6, needed only
  once E3 runs), the read-only viewer page (a later unit), the Market Review (HQ3), and anything shared
  with Zimplii.
- **Pending product-owner decisions** that this feature does not block on: readiness score in G0, the
  final first-release repertoire (HR08), which deviations need reason codes (HQ2), and default live
  checkpoints (HQ4).
