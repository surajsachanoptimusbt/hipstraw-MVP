<!--
SYNC IMPACT REPORT (temporary - remove before commit)
Version change: 1.1.0 → 1.2.0 (MINOR: four principles added; none removed or redefined)
Modified principles: none (I-XI retained verbatim)
Added principles:
  - XII. Traceability
  - XIII. Read-Only Viewer
  - XIV. Layer Boundaries
  - XV. Bounded Search
Added sections: none
Removed sections: none
Templates: plan/spec/tasks templates read the constitution at runtime; not modified here
Follow-up TODOs (compliance gaps in existing work, not placeholders):
  - Feature 002 logs step start/end and model-call events only; it does not yet record the full
    per-step trace that XII requires (inputs, outputs, decision and right used, rationale, checks,
    prompt and structured response, tool calls, cost/latency).
  - Feature 002 spec FR-019 excludes any user interface; XIII permits only a read-only viewer, so
    the two agree, but a viewer needs its own spec.
  - XIV names layers that feature 002's plan does not yet map: discover/verify (Search & Research),
    Review (Market Manager), report. The plan's Constitution Check should record the mapping.
-->

# hipstraw MVP Constitution

A living document establishing the core engineering principles and governance for the hipstraw MVP
project.

## Core Principles

### I. Library-First Architecture

Every feature starts as a standalone, reusable library. Libraries MUST be self-contained,
independently testable, and clearly documented with explicit purpose. No organizational-only
libraries without clear contract boundaries.

**Rationale**: Enforces modularity, reusability, and clear separation of concerns. Libraries become
building blocks for both MVP and future iterations.

### II. CLI Interface Contract

Every library MUST expose its functionality via a command-line interface. Data flows through
stdin/args and outputs to stdout (or structured formats like JSON). Errors go to stderr with
non-zero exit codes.

**Rationale**: Text I/O ensures debuggability, scriptability, and language-agnostic integration.
Supports both human operators and automated workflows.

### III. Test-First (NON-NEGOTIABLE)

Test-driven development is mandatory. Tests MUST be written before implementation; user approval
MUST precede code. Red-Green-Refactor cycle strictly enforced.

**Rationale**: Prevents scope creep, clarifies requirements, and ensures high confidence in MVP
quality. Tests serve as executable specifications.

### IV. Integration Testing Focus

Integration tests are required for:
- New library contract boundaries
- Inter-service communication paths
- Shared schema or data model changes
- External dependency integration

Unit tests verify internal correctness; integration tests verify the system works end-to-end.

**Rationale**: MVP success depends on components working together reliably. Integration tests catch
architectural mismatches early.

### V. Observability & Maintainability

Text-based I/O ensures debugging without external tools. Structured logging (JSON or delimited) MUST
be provided for production observability. Code MUST be self-documenting; comments explain WHY, not
WHAT.

**Rationale**: MVP goes live; observability prevents production surprises. Self-documenting code
reduces knowledge silos.

### VI. Faculty Systems Design Methodology

HipStraw is built as a Faculty System: a bounded responsibility maintained through the loop
Reality → Review → Position → Attention/Decision → Action → Outcome → Review again.

- Each faculty MUST declare its bounded responsibility explicitly.
- Review, not raw evidence, is the interface to reality. No component acts on raw evidence that has
  not passed through Review.
- The manager layer owns the Position. Only the manager layer MAY change the canonical Position.
- Controller and worker output is input to Review and MUST NOT become canonical on its own.
- Every Action's Outcome MUST feed back into Review, closing the loop.

**Rationale**: A single governed path from reality to canonical state keeps the system's view
accountable and stops unreviewed output from silently becoming truth.

### VII. System-Level Intelligence (No Agent SDK)

Intelligence lives in the system (state, Review, rubrics, policies, governed actions), not in an
autonomous agent framework.

- Agent SDKs and agent frameworks MUST NOT be used.
- Direct LLM calls are permitted only for bounded reasoning steps, invoked by the system's own
  orchestration.
- Every LLM call MUST take explicit inputs and return structured output.
- LLM output is worker output under Principle VI: input to Review, never canonical on its own.

**Rationale**: Keeping control flow in the system's own orchestration makes behavior inspectable,
testable, and governed, rather than delegated to an opaque autonomous loop.

### VIII. Evidence Provenance

- Every material claim MUST record its source, recency, and reliability.
- Conflicting evidence MUST be preserved side by side, not averaged or silently resolved.
- Missing evidence MUST be recorded as an explicit unknown, not filled by default or inference.

**Rationale**: Review can only weigh what it can trace. Provenance, preserved conflict, and explicit
unknowns let Review reason about confidence instead of hiding it.

### IX. Real-World Data Integrity

- Anything presented as a real company or fact MUST be verifiable from a cited source.
- The system MUST NOT fabricate a company.
- The system MUST NOT present an inferred company or fact as real; inferred content MUST be labeled
  as inferred.

**Rationale**: Users act on what HipStraw presents as real. A single fabricated or unmarked
inference undermines trust in every other output.

### X. Smallest-Unit Increments

- Each feature MUST be the smallest testable unit.
- Each unit MUST be specified, reviewed, implemented, and tested before the next unit is added.

**Rationale**: Small, fully closed units keep defects local and keep every step reviewable against
this constitution.

### XI. Deferred Technology: Jev

- Jev (efficient vichara) MUST NOT be used until research validates its role.
- Lifting this deferral requires a constitution amendment that cites the validating research.

**Rationale**: Adopting an unvalidated technology would bake unknown assumptions into the system's
core before their value is established.

### XII. Traceability

Every pipeline step MUST record a structured trace as a stored record, containing:
- layer, actor, and operation;
- inputs and outputs;
- the decision made and the right under which it was made;
- the rationale and the checks applied, with their results;
- for each model call, the prompt and the structured response;
- tool calls (searches, fetches, store writes);
- cost and latency.

Traces MUST NOT contain the model's hidden reasoning; only what the system sent and received is
recorded. Traces MUST NOT contain secrets (API keys, tokens, credentials).

**Rationale**: Review, debugging, and audit all depend on being able to reconstruct why the system
did what it did from stored records, not from memory or opaque model state.

### XIII. Read-Only Viewer

A user interface is in scope only as a read-only viewer of stored state and traces. A viewer MUST
NOT write, edit, or delete data, and MUST NOT trigger pipeline steps. All changes to state go
through the governed pipeline (Principle VI).

**Rationale**: A viewer that can write would be a second, ungoverned path to canonical state.

### XIV. Layer Boundaries

Each layer has one responsibility and MUST NOT take over another's:
- **Market Manager**: decides (Review, dispositions, the Position). It MUST NOT traverse the graph.
- **Market Development Controller**: defines what the graph means (its schema and semantics).
- **Search & Research**: builds, validates, verifies, and searches the graph.
- **Position & Evaluation**: assesses positions and outcomes.
- **Workers**: perform bounded tasks with explicit inputs and structured outputs.

Every trace (Principle XII) names its layer, so a crossing of these boundaries is visible.

**Rationale**: Separating deciding from searching and assessing keeps each layer testable and keeps
decisions with the layer that is accountable for them (Principle VI).

### XV. Bounded Search

- Search MUST keep a bounded frontier: filter → score → diversity → keep the top N, with N set in
  configuration.
- Exhaustive traversal is a defect.
- Search scores rank what to look at next. They MUST NOT be presented as evidence confidence, which
  comes only from cited evidence (Principle VIII).

**Rationale**: Bounded search keeps cost, latency, and attention predictable, and keeping ranking
scores apart from confidence stops a heuristic from passing as evidence.

## Technology & Dependencies

- **Language**: Determined per library; prefer statically typed languages for contract clarity
- **Package Management**: Use standard ecosystem tools (pip, npm, cargo, etc.) with locked versions
- **External Dependencies**: Minimize for MVP. Justify every external dependency for size, security,
  and maintenance burden
- **Vendoring**: Prefer pinned versions and reproducible builds over dynamic resolution

## Development Workflow

1. **Specification**: Start with a spec describing desired behavior, inputs, outputs, and failure
   modes
2. **Test Design**: Write tests that validate the spec before code exists
3. **Implementation**: Code until tests pass; refactor only after green tests
4. **Code Review**: Every commit reviewed for spec compliance and test coverage
5. **Deployment**: Only tested, reviewed code reaches production

Quality gates are non-negotiable checkpoints, not suggestions.

## Governance

**Amendment Procedure**: Constitution changes require:
- Written rationale and impact assessment
- Team review and consensus (no unilateral changes)
- Version bump with semantic versioning rules (MAJOR: breaking governance, MINOR: new principle,
  PATCH: clarification)
- Explicit migration plan if changing existing principles

**Compliance**: All PRs and deployments MUST verify constitution compliance. Complexity or exception
requests MUST include written justification.

**Version Strategy**:
- **MAJOR** bump: Removal or redefinition of existing principles (breaking change)
- **MINOR** bump: New principles added or existing ones materially expanded
- **PATCH** bump: Clarifications, wording improvements, or non-semantic refinements

**Version**: 1.2.0 | **Ratified**: 2026-10-05 | **Last Amended**: 2026-10-08
