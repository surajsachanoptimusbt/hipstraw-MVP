# Config Contract: `config/campaign/`

Every file has a `version` string. All files are loaded through pydantic models with unknown keys
forbidden. `campaign lint` loads them all and runs the Line lint.

## moves.yaml

```yaml
version: campaign-repertoire.v0.1
source: "HA section 5 candidate Moves; pending the repertoire workbook (HR08, HQ1)"
moves:
  - id: M04
    version: 1
    name: Completeness check against readiness criteria
    group: readiness
    effectClasses: [E0]
    eligibility: []                 # typed checks (see Conditions), all must hold to run
    inputs: [mandate, position, criteria]
    transitions:
      - {kind: blocker, from: [null, open, cleared], to: [open, cleared]}
    risks: ["criteria list incomplete for a channel"]
    handler: readiness.completeness
  - id: M06
    version: 1
    name: Synthesize strategic assumptions and gaps
    group: strategy
    effectClasses: [E2]
    promptVersion: campaign_synthesis.v1
    transitions: []                 # proposals only; never changes a state
    handler: strategy.synthesize
  - id: M09
    version: 1
    name: Draft Test Plan
    group: testing
    effectClasses: [E0]
    producesTestPlan: true
    transitions:
      - {kind: hypothesis, from: [proposed], to: [planned]}
    handler: testing.draft_test_plan
  - id: M10
    version: 1
    name: Dispatch approved test
    group: testing
    effectClasses: [E3]
    requiresApproval: test_plan
    transitions:
      - {kind: hypothesis, from: [planned], to: [running]}
    handler: testing.dispatch_blocked
```

A Move with several effect classes (M02 is `[E1, E2]`) must pass the gate for every class it lists.

## lines.yaml

```yaml
version: campaign-repertoire.v0.1
lines:
  - id: L01
    version: 1
    name: Readiness-first
    stages: [[M01], [M04, M05], [M12]]
    reviewQuestion: "Is the campaign operationally ready for Day Zero, and what blocks it?"
    useWhen: {all: [{fact: daysToDayZero, op: "<=", value: 14}, {fact: isLive, op: "==", value: false}]}
    excludeWhen: {any: [{fact: isLive, op: "==", value: true}]}
  - id: L03
    version: 1
    name: Test before expansion
    stages: [[M07], [M09], [M10], [M11]]
    reviewQuestion: "Does the proposed variant have field signal?"
    useWhen: {all: [{fact: openHypotheses, op: ">", value: 0}]}
    excludeWhen: {any: [{fact: authorizedTestChannel, op: "==", value: false},
                        {fact: testPlanBudgetSet, op: "==", value: false}]}
```

The first release defines L01–L05 as in HA section 5. Use-when and exclude-when for L02, L04 and L05:
L02 use when `unverifiedCoreAssumptions > 0`, exclude when it is `0`; L04 use when `isLive` and
`hasMetrics`, exclude when not `isLive`; L05 use when `any` of `contestedClaims > 0` or `unknowns > 0`.

### Conditions

`{all: [...]}` or `{any: [...]}` of `{fact, op, value}`. Operators: `<`, `<=`, `>`, `>=`, `==`, `!=`.
Facts (computed from the head Position and the current mandate): `daysToDayZero` (int, negative after
Day Zero), `isLive` (bool), `hasMetrics` (bool), `openBlockers`, `openReadinessBlockers`,
`unverifiedCoreAssumptions`, `contestedClaims`, `unknowns`, `openHypotheses` (ints),
`authorizedTestChannel`, `testPlanBudgetSet` (bools). An unknown fact or operator fails the lint.

### Line lint rules (FR-018)

1. Every Move ID in every stage exists in moves.yaml, and every definition has a `version`.
2. Every Move's `handler` exists in the handler registry.
3. For every E3 Move in a Line, an earlier stage holds a Move with `producesTestPlan: true`, and the E3
   Move declares `requiresApproval: test_plan`.
4. Every Line has `reviewQuestion` and ends in a Review (the runner adds the Review; a Line may not
   declare another exit).
5. No Move whose effect classes include E2 declares a transition into a claim state above `reported`.
6. Every condition uses a known fact and operator.
7. Line and Move IDs are unique.

## criteria.yaml

```yaml
version: readiness-criteria.v0.1
status: "proposal for domain-owner review"
leadDays: 3
criteria:
  - {id: RC01, text: "Landing page address given", check: asset_present, args: {kind: landing_page}}
  - {id: RC02, text: "Objective and success measure stated", check: field_present, args: {field: objective.successMeasure}}
  - {id: RC03, text: "Approver named", check: field_present, args: {field: approver}}
  - {id: RC04, text: "Each authorized channel has its asset", check: channel_assets,
     args: {email: email_copy, paid_social: ad_copy, search: ad_copy, display: creative}}
  - {id: RC05, text: "Tracking plan stated", check: field_present, args: {field: trackingPlan}}
  - {id: RC06, text: "Campaign budget stated", check: field_present, args: {field: strategy.budget}}
dependencyRules:
  - {id: DZ01, text: "Day Zero set and in the future, or the launch is live", check: day_zero_valid}
  - {id: DZ02, text: "Every asset ready at least leadDays before Day Zero", check: assets_ready_before}
```

Checks are named functions in code; the file chooses and parameterizes them.

## layers.yaml (campaign trace layers)

```yaml
layers:
  - id: campaign_manager
    actors: [launch_desk, line_selector, stage_runner, position_keeper]
    rights: [open_launch, amend_mandate, propose_position, recommend_lines, choose_line, record_deviation, run_stage, commit_position]
  - id: readiness_testing
    actors: [move_runner]
    rights: [run_move]
  - id: authority_gate
    actors: [authority_gate]
    rights: [check_authority]
  - id: review
    actors: [review_assembler, reviewer, sponsor]
    rights: [draft_review, review_finding, validate_review, accept_review, reject_review]
  - id: workers
    actors: [llm_worker, fetch_worker]
    rights: [call_model, fetch_page]
```

## roles.yaml

```yaml
version: campaign-roles.v0.1
roles:
  sponsor: [submit_launch, amend_mandate, accept_review, reject_review]
  campaign_manager: [submit_launch, choose_line, deviate, run_line, stop_line]
  reviewer: [review_finding, validate_review]
```

## settings.yaml

```yaml
version: campaign-settings.v0.1
launchMarkets: [US, IN]
nearDayZeroDays: 14
maxVariants: 3
metricFreshDays: 7                              # M03: older windows are stale
fetch: {timeoutSeconds: 15, maxBytes: 2000000}  # M02 page reads
scopeStatement: >-
  Continuous Campaign Strategy & Readiness Testing tests a launch's campaign strategy and execution
  readiness before and during the launch, measured against Day Zero. ... (HA section 1, verbatim)
coreAssumptions:   # created at intake, all open and core
  general:
    - "The stated audience has the problem the message names"
    - "The offer is strong enough for the audience to act"
  perChannel: "The {channel} channel reaches the stated audience"   # one per channel
```

## Launch file (input to `submit` and `amend`)

```yaml
product: {name: "...", description: "...", website: "https://..."}
audience: {description: "...", segments: ["..."]}
market: US
dayZero: 2026-11-20
objective: {statement: "...", successMeasure: "..."}
strategy: {channels: [email, paid_social], message: "...", offer: "...", budget: {amount: 5000, currency: USD}}
authorizedChannels: []
approver: "..."
trackingPlan: "..."
assets:
  - {kind: landing_page, url: "https://..."}
  - {kind: email_copy, channel: email, text: "...", readyDate: 2026-11-10}
metricsFile: metrics.csv          # optional; path relative to the launch file
```

Metrics CSV columns: `metric, value, unit, window_start, window_end, denominator, definition,
captured_at`. Missing `definition`, window or `captured_at` makes the row `unverified`.
