# LLM Output Contract: the three E2 Moves

Each output is a pydantic model with unknown keys forbidden, requested as strict structured output
through `TaskRouter.call`. No model has a score, probability, likelihood or forecast field (R11). Every
call passes a validator; failed checks are recorded on the business step and the Move ends without
proposals (no partial acceptance).

## `campaign_source_summary.v1` (M02, summary part)

Input: the page text M02 read (E1) as one evidence record, plus the mandate's claims about the product,
audience and offer, each with its item ID.

```text
SourceSummary
  claims[]: {text, area: strategy|readiness, quote, state: reported|contested, contradictsItemIds[]}
  unreadable: bool
  unreadableReason?: str
```

Checks: each `quote` appears word for word in the page text; `state` is never above `reported`
(`contested` only with at least one `contradictsItemIds` entry that exists); if `unreadable`, `claims`
is empty.

## `campaign_synthesis.v1` (M06)

Input: the head Position's items and the launch's evidence records (IDs and content).

```text
Synthesis
  assumptions[]: {text, core: bool, evidenceRefs[]}
  gaps[]: {text, area: strategy|readiness, itemRefs[], evidenceRefs[]}
  findings[]: {text, area: strategy|readiness, evidenceRefs[], uncertainty}
```

Checks: every `evidenceRefs` and `itemRefs` entry exists in this launch; every finding cites at least
one evidence record; every gap cites at least one item or evidence record.

## `campaign_variants.v1` (M07)

Input: the head Position's strategy items and the mandate's message, offer, audience and channels.

```text
Variants
  variants[]: {dimension: message|audience|offer|channel, text, rationale, evidenceRefs[], hypothesis}
```

Checks: at most `maxVariants` (settings); every `evidenceRefs` entry exists; each variant states a
`hypothesis`. Each variant becomes a `proposed` hypothesis item in the successor Position, labelled as a
proposal.
