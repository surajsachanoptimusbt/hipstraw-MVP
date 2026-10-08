# Contract: model calls (feature 003)

Same rules as [feature 002's model-call contract](../../002-objective-to-target-companies/contracts/llm-outputs.md):
each call is one strict-schema OpenAI request with explicit inputs and no tools or loop (Constitution
VII); every field is required (nullable where stated) and extra fields are forbidden; a response that
fails its schema is retried once, then the step fails; output has **no field** for a person's name, email
address, or phone number (FR-030); count limits are enforced by the system after parsing. Each call is a
Worker step in the trace (layer `workers`, actor `llm_worker`, right `call_model`), with its prompt and
response stored as blobs.

Nine new schemas. Prompt files are `src/hipstraw_mm/prompts/<name>.v1.txt`. Replay match keys are listed
for each (research R19).

## 1. `DimensionDeliberation` (vichara; one call per dimension)

Match key: `Vichara:<dimensionKey>`. Prompt: `vichara.v1`.
**Input**: `dimension` {key, name, question, states}; `objective` (the objective bundle text: program
objective, the six experiment contexts, constraints); `maxItems`.

```json
{
  "dimensionKey": "string",
  "items": [
    {"question": "string", "status": "answered|unresolved", "answer": "string|null",
     "basis": ["string"], "reason": "string|null"}
  ]
}
```

Rules: 1 to `maxItems` items; `dimensionKey` equals the input's. `answered` needs `answer` and at least one
`basis`; `unresolved` needs `reason` and an empty `basis`. Each `basis` is copied word for word from the
objective text and is **checked by the system** (research R6); a failing basis sends the dimension to
repair. Zero information means `unresolved` with the reason "no information in the objective".

## 2. `CoverageJudgement` (vichara relevance; one call)

Key: `VicharaCoverage:<attempt>`. Prompt: `vichara_coverage.v1`. **Input**: the 19 dimensions with their
items.

```json
{"dimensions": [{"dimensionKey": "string", "addressesDimension": true, "reason": "string"}]}
```

One entry per dimension that has an answered item. `addressesDimension: false` fails that dimension.

## 3. `DimensionRepair` (one call per attempt, all failing dimensions)

Key: `VicharaRepair:<attempt>`. Prompt: `vichara_repair.v1`. **Input**: the failing dimensions with what
failed and why, and the objective text. **Output**: a list of `DimensionDeliberation` objects, only for
the failing dimensions. Other dimensions cannot appear (the system rejects them).

## 4. `GraphLevelProposal` (graph generation; one call per level)

Key: `GraphLevel:<level>`. Prompt: `graph_level.v1`. **Input**: the graph meaning (levels, filters,
attribute values); the level to build; the vichara items for that level's dimension (with item IDs); the
previous level's nodes (none for `segment`); `maxNodes`, `maxParents`.

```json
{
  "level": "segment|archetype|problem|trigger|buyerRole|useCase",
  "nodes": [
    {"label": "string", "description": "string", "parentLabels": ["string"],
     "metroIds": ["string"], "sizeBand": "startup|small|mid_market|enterprise|null",
     "sourceItemIds": ["string"]}
  ]
}
```

Rules: `parentLabels` name nodes of the previous level exactly (empty only for `segment`); `metroIds` is
required (non-empty) for `segment` and empty otherwise; `sizeBand` is required for `archetype` and null
otherwise; `sourceItemIds` are vichara item IDs. The system assigns node IDs, drops nodes that break a
mandatory filter ("excluded by filter") and nodes over the caps, and rejects `parentLabels` that match no
node.

## 5. `GraphCoverage` (graph coverage judgement; one call per check)

Key: `GraphCoverage:<attempt>`. Prompt: `graph_coverage.v1`. **Input**: the graph and the answered vichara
items.

```json
{"gaps": [{"itemId": "string", "reason": "string"}]}
```

Each gap names a vichara item the graph does not cover. An empty list means covered. Advisory only
(feature 001): it drives repair, not a sufficiency verdict.

## 6. `GraphRepair` (one call per attempt)

Key: `GraphRepair:<attempt>`. Prompt: `graph_repair.v1`. **Input**: the graph, the structural violations
and coverage gaps to fix, the graph meaning. **Output**:

```json
{"addNodes": [ /* same node shape as GraphLevelProposal, plus "level" */ ],
 "addEdges": [{"fromLabel": "string", "toLabel": "string"}]}
```

Additive only: it cannot delete or change existing nodes or edges (the system checks this by comparison).
Added nodes pass the same filters and caps.

## 7. `LinkVerification` (one call per level pair, chunked)

Key: `LinkVerification:<levelPair>:<chunk>`. Prompt: `link_verification.v1`. **Input**: up to `linksPerCall`
links, each with both nodes' labels and descriptions and the vichara items they cite; the objective text.

```json
{"links": [{"edgeId": "string", "rationale": "string", "linkConfidence": 0.0}]}
```

`rationale` answers "why is this node connected to that one", from the objective and the cited items.
`linkConfidence` is 0 to 1 and measures how well the connection is argued, not evidence about companies.
Every input link must appear exactly once.

## 8. `BeamScoring` (one call per level)

Key: `BeamScoring:<level>`. Prompt: `beam_scoring.v1`. **Input**: the level, the candidate paths (node
labels and descriptions, mean link confidence), the objective text, and the factor definitions.

```json
{"candidates": [{"pathId": "string",
  "objectiveFit":      {"value": 0.0, "rationale": "string"},
  "informationValue":  {"value": 0.0, "rationale": "string"},
  "evidenceGap":       {"value": 0.0, "rationale": "string"},
  "cost":              {"value": 0.0, "rationale": "string"}}]}
```

Values are 0 to 1; higher is better for the first three, and for `cost` higher means **cheaper** to
search (so all four are combined the same way). These are hypotheses labelled as such and are never
shown or stored as confidence. Every candidate must appear exactly once.

## 9. `PathAssessment` (one call per kept final-level path)

Key: `PathAssessment:<pathKey>`. Prompt: `path_assessment.v1`. **Input**: the path's nodes and links, the
objective text, the grammar states for the seven dimensions.

```json
{"assessments": [{"dimensionKey": "value_proposition|demand_signals|adoption_readiness|economics|alternatives|risks|dependencies",
  "state": "string", "rationale": "string"}]}
```

Exactly the seven dimensions, each with a state from the grammar's list for that dimension. These are
hypotheses drawn from the objective only and are stored with `label: "hypothesis"` (FR-013); they are
not evidence.

## 10. `BuyerRoles` (one call per final path, batched over its companies)

Key: `BuyerRoles:<pathKey>`. Prompt: `buyer_roles.v1`. **Input**: the path's problem and buyer-role
labels; for each company: name, domain, and its passing evidence documents (`evidenceId`, `claimField`,
`claimValue`, `excerpt`).

```json
{"companies": [{"domainKey": "string",
  "roles": [{"function": "string", "authority": "owns_budget|approves|uses|influences",
             "evidenceIds": ["string"]}]}]}
```

Rules: no person fields; `function` is a function or job title, never a person; every `evidenceId` must be
a passing evidence document of that company (the system keeps a role only then; otherwise the company
gets an explicit unknown); at least one `evidenceId` per role.

## Prompt rules shared by all nine

- Use only the provided input. Never add a company, a person, or a fact the input does not contain.
- Never output person names, email addresses, or phone numbers.
- Return only the schema.
- Prompts are versioned files; the version is stored in the trace step (FR-023).
