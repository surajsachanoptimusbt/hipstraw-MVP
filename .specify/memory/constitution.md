<!--
SYNC IMPACT REPORT (temporary - remove before commit)
Version change: 1.0.0 → 1.1.0 (MINOR: new principles added, none removed or redefined)
Modified principles: none (I-V retained verbatim)
Added principles:
  - VI. Faculty Systems Design Methodology
  - VII. System-Level Intelligence (No Agent SDK)
  - VIII. Evidence Provenance
  - IX. Real-World Data Integrity
  - X. Smallest-Unit Increments
  - XI. Deferred Technology: Jev
Added sections: none
Removed sections: none
Templates: plan/spec/tasks templates read the constitution at runtime; not modified here
Follow-up TODOs: none
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

**Version**: 1.1.0 | **Ratified**: 2026-10-05 | **Last Amended**: 2026-10-05
