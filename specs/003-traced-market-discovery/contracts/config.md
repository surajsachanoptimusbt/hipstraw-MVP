# Contract: configuration files (feature 003)

Same rules as [feature 002's config contract](../../002-objective-to-target-companies/contracts/config.md):
YAML, validated with Pydantic at command start (exit code 1 on error), no secrets, and no thresholds or
place names in code. Feature 002's `run.yaml`, `metros.yaml`, `source_policy.yaml`, and `programs/*.yaml`
are reused unchanged. Four files are new.

## `config/grammar.yaml`

The 19 Market Manager dimensions, copied from `hipstraw-faculty/seed_data/grammar.json` (research R5).

```yaml
# Copied 2026-10-08 from hipstraw-faculty/seed_data/grammar.json (sha256: <hash of the source file>).
# Four names or questions had a lost dash (U+FFFD); each was replaced with an en dash: <the four keys>.
dimensions:
  - key: market_scope
    name: Market Scope / Critical Boundaries
    type: Market
    question: "Is the market being evaluated clearly defined in terms of company type, ...?"
    reviewFrequency: Occasional; more frequent early
    states: [specified, partially specified, unclear, changed, stable]
    rank: {specified: 3, partially specified: 2, unclear: 1, changed: 1, stable: 4}
    level: program              # program | candidate
    evaluationKind: input       # input | evidence | derived
    assessedBy: program_input   # program_input | search_research | position_evaluation | market_development_controller | derived_rule
    decidedBy: market_manager
  # ... 18 more
```

Validation: exactly 19 unique keys; every `rank` key is in `states`; `decidedBy` is `market_manager`.

## `config/layers.yaml`

The five layers, their one responsibility each, their actors, and the **rights** they may use
(Constitution XIV; research R3). The Tracer rejects any step whose layer, actor, or right is not
declared here.

```yaml
layers:
  - id: market_manager
    responsibility: Decides. Owns path decisions, Market Status, and Review dispositions. Never traverses the graph.
    actors: [market_manager, review]
    rights: [open_run, decide_path, set_market_status, record_disposition]
  - id: market_development_controller
    responsibility: Defines what the graph means - levels, relationships, mandatory filters, what a promising path is.
    actors: [graph_meaning]
    rights: [define_graph_meaning]
  - id: search_research
    responsibility: Breaks the objective into questions; builds, validates, verifies, and searches the graph; gathers evidence.
    actors: [vichara, graph_builder, graph_validator, link_verifier, beam_search, company_search]
    rights: [ask_dimension, build_graph, repair_graph, verify_link, prune_path, keep_path, defer_path, discover_companies]
  - id: position_evaluation
    responsibility: Assesses paths, evidence, and buyer roles.
    actors: [path_assessor, evidence_evaluator, buyer_role_finder]
    rights: [assess_path, evaluate_evidence, identify_buyer_roles]   # evaluate_evidence: FR-020 evidence results (R16)
  - id: workers
    responsibility: Bounded tasks with explicit inputs and structured outputs - one model call, one search, one fetch.
    actors: [llm_worker, search_worker, fetch_worker]
    rights: [call_model, run_search, fetch_page]
```

Validation: the layer ids are these five, in this order (the viewer's grouping order); a right belongs
to exactly one layer; actors are unique.

## `config/graph_meaning.yaml`

The Market Development Controller's definition (research R8), recorded verbatim as `graphMeanings`.

```yaml
levels:                     # in order; each level links only to the next
  - {level: segment,   dimension: market_scope}
  - {level: archetype, dimension: segment_fit}
  - {level: problem,   dimension: problem}
  - {level: trigger,   dimension: timing}
  - {level: buyerRole, dimension: buyer}
  - {level: useCase,   dimension: use_case}
attributes:
  segment:   {metroIds: "list of metro ids, from the run's constraints"}
  archetype: {sizeBand: [startup, small, mid_market, enterprise]}
mandatoryFilters:
  - {id: metro_in_force, appliesTo: segment,   attribute: metroIds, rule: subset_of_run_metros}
  - {id: no_enterprise,  appliesTo: archetype, attribute: sizeBand, rule: not_in, values: [enterprise]}
caps: {nodesPerLevel: 5, parentsPerNode: 2}
promisingPath:
  definition: A chain from segment to use case that is within the filters, well argued link by link, and worth searching now.
  factors: [objectiveFit, informationValue, evidenceGap, cost]
perPathDimensions: [value_proposition, demand_signals, adoption_readiness, economics, alternatives, risks, dependencies]
verificationResults: [evidence_sufficiency, evidence_quality, critical_unknowns]
managerOnly: [trajectory, transition, market_status]
```

Validation: the six level dimensions, `perPathDimensions` (7), `verificationResults` (3), and
`managerOnly` (3) together name each of the 19 grammar keys exactly once (6 + 7 + 3 + 3 = 19).

## `config/pipeline.yaml`

```yaml
beam: {width: 5, finalPaths: 3, companiesPerPath: 5}
defaultInterestIds: [invoice_accuracy_entitlement, continuous_obligation_intelligence]   # child-run interests (R13)
factorWeights: {objectiveFit: 1, informationValue: 1, evidenceGap: 1, cost: 1}   # normalized when used
repair: {maxAttempts: 3}
vichara: {maxItemsPerDimension: 3}
links: {lowConfidenceThreshold: 0.5, linksPerCall: 12}
evidenceStates:                                  # research R16
  sufficiencyHalf: 0.5
  decisionReadyMinCompanies: 3
  qualityMixedFloor: 0.5
  qualityStrongFloor: 0.8
budgets: {modelCallsPerRun: 300}
trace: {maxBlobBytes: 900000}
modelPricing:                                    # USD per million tokens; a model not listed gives cost unknown
  gpt-4o: {input: 2.50, output: 10.00}
viewer: {host: 127.0.0.1, port: 8765, pollSeconds: 2}
```

Validation: `beam.finalPaths <= beam.width`; `beam.companiesPerPath <= 10`; factor weights all above 0;
`repair.maxAttempts` between 1 and 3 (the spec's bound is 3); `viewer.host` must be a loopback address.
The prices above are placeholders and must be checked against the provider's current price list before
any cost figure is quoted; an unlisted model records `cost.usd: null`.
