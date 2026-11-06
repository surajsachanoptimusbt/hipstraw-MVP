# First slice: G0 with a Shadow Launch

Draft, 2026-11-04, for Ashish to confirm. It responds to the Nov 4 meeting: "Update first slice: incorporate the
provided platform details into the first implementation phase". The platform details are the Hipstraw Strategic &
Operating Blueprint v0.1.

Once confirmed, this becomes spec 005 in this repository, beside feature 004.

## What the Blueprint keeps, adds and leaves out

**Keeps:**
- **G0 as a bounded service.** Section 10 defines G0 as "strategy/readiness reviews + small managed Shadow Launch
  trials; manual HT ledger acceptable". The evidence to advance is "paid customers, valid decisions, safe field
  work, acceptable cost".
- **The Faculty grammar.** Section 05 adopts it: Evidence → Review ↔ Position → Strategy → Line → Move → Action →
  Outcome. The grammar "does not require a separate microservice for every noun". Lines and Moves stay the
  baseline, as Ashish said on Nov 4.

**Adds:**
- Shadow Launch as the flagship offer.
- A Stage A founding use case: Hipstraw tests itself.
- The Shadow Launch charter (Appendix E).
- Gates G1 to G4.
- Rubric families with a qualification ladder.
- The outcome package.
- Hipstraw Tokens (HT) and Shadow Accounts.

**Leaves out of G0:** "a general autonomous agent harness, a multi-tenant workflow compiler or persistent AI
sessions."

## The first slice

Run Stage A of the Blueprint: Hipstraw's own Shadow Launch, as one governed experiment case. The question is
whether small B2B service and software firms need a managed Shadow Launch service.

The case moves through these steps:

charter → G1 → desk evidence → G2 → field Moves → demand assessment → G3 → outcome package

It reuses the campaign module for readiness checks and the daily review.

## What already exists

| Blueprint concept | Where it is today |
|---|---|
| Evidence with provenance and verification state | campaign evidence records (C2) |
| Versioned Position | Campaign Position snapshots (C3) |
| Review: accept, correct or reject; preserve dissent | Review runs, review queue, reviewer desk, corrections (C4, C9) |
| Line and Move, effect classes, E3 blocked without approval | repertoire M01–M14 and L01–L06, Line lint, policy gate (C7) |
| Decision history | append-only audit (C5), tactic record (C10) |
| G2 "truthful claims, compliant outreach" | M13 channel standards, campaign rubric CR01–CR09 |
| Monitoring a field run daily | L06 daily review, M14, M11 Delta, simulation |
| Demand evidence rubric | `hipstraw_mm.foundry.demand`, Moves DV01–DV08, Line LD1 (added Nov 4, candidate) |
| Customer and reviewer act in the browser, governed | campaign console (constitution XIII) |

## What the first slice adds, in order

Each unit is test-first.

1. **Demand evidence rubric and lab.** Done Nov 4. See
   [market_demand_validation.md](market_demand_validation.md). It stays a candidate until someone other than its
   author writes the lab expectations.
2. **Experiment case and Shadow Launch charter.** Appendix E becomes a versioned record. Accepting the charter is
   separate from permission to run E3 Moves. Its fields:

   | Field | What it holds |
   |---|---|
   | Mandate and owner | sponsor, accountable decision-maker, opportunity boundary, restrictions, delegate |
   | Commercial question | the decision to improve, and its alternatives |
   | Hypotheses and rubric | expected buyer behaviour, rubric versions, disqualifiers |
   | Target and method | population, selection rule, channel, method version |
   | Evidence and measurement | qualifying signal, source, denominator, window, confounders |
   | Funding | maximum reservation, external cash budget, renewal or stop rule |
   | Truth and consent | seller disclosure, actual availability, claims substantiation, privacy, contact permission |
   | Execution authority | allowed tools, human approvals, effect classes, revocation |
   | Outcome decision | Review date, independent evaluator, proceed / reframe / pause / stop |

3. **Gates G1 to G4 as recorded decisions on the case.** Each records who decided, the rubric version (fixed
   before results, gate GX3) and the evidence cutoff. A gate does not imply automatic progression.

   | Gate | Possible decisions |
   |---|---|
   | G1 question worth testing | run probe / reframe / do not spend |
   | G2 field exposure | launch limited trial / fix blocker |
   | G3 pilot commitment | offer paid pilot / collect more evidence |
   | G4 graduation | scale / redesign / stop |

4. **Field evidence intake.** Today a case is a YAML file. In the slice, field evidence is stored as evidence
   records with provenance, and the case is assembled from the store:
   - interview notes become `problem_interview` items;
   - a sign-up or visit CSV becomes L2 or L3 items with counts;
   - letters of intent, deposits and pre-orders become L5 items with a price.
5. **G2 readiness for the shadow offer.** The offer page and outreach copy go through the existing campaign
   readiness checks: M13 channel standards and the campaign rubric. That covers disclosure, consent, claims and the
   email and LinkedIn rules.
6. **Field run monitoring.** The shadow offer's funnel (visits, replies, sign-ups) runs through L06 daily review,
   unchanged.
7. **Outcome package report.** Blueprint section 04 lists its contents:
   - an evidence-linked Position;
   - what was attempted;
   - actual work and costs;
   - what happened, and what was not established;
   - expected versus observed deltas;
   - a recommendation with alternatives;
   - the next approval request.

   Negative results must be as legible as successes.
8. **Cost record.** Hours and external spend per case, entered by hand. This stands in for the HT ledger until
   Stage C.

## Deferred

| What | Why |
|---|---|
| HT ledger and Shadow Accounts | G0 accepts a manual ledger; Stage C is the HT pilot. Ashish on Nov 4: tokens are not the focus now |
| Shadow Portfolio (several cases, allocation) | Stage D and G2 persistent orchestration |
| Hipstraw sending outreach, publishing pages or spending (E3 dispatch) | people act under the charter; Hipstraw records and reviews |
| Other rubric families (Opportunity, Offer, Supply readiness, Experiment validity, Investment readiness) | after demand evidence reaches lab-tested; they reuse the same config and lab pattern |
| Autonomous agents, compiler, persistent sessions | excluded from G0 by the Blueprint |

## The Stage A run

1. **G1.** Ashish confirms the question, the segment, the price floor and the thresholds. The rubric version is
   committed before any field result.
2. **DV02.** About 10 problem interviews with small B2B service and software firms, starting with Atlanta IT
   services. The guide is in [market_demand_validation.md](market_demand_validation.md).
3. **G2, then DV03.** A truthful shadow offer page, with the seller disclosed where material, and targeted email or
   LinkedIn outreach. Both pass the campaign readiness checks first.
4. **DV07.** Assess. If the result is promising, run DV05 (a letter of intent or refundable deposit for a paid
   trial at the price floor) and DV06. G3 decides on a paid pilot.
5. **DV08.** An independent review, then the outcome package. G4 comes only after a pilot is delivered.

## Architecture

Unchanged from the Nov 3 advice:
- **Same repository**, with the same constitution and CLI-first rule.
- **Same store pattern** (SQLite behind a store protocol) and the same viewer and console pattern.
- **New packages** beside `hipstraw_mm.campaign`:
  - `hipstraw_mm.foundry` holds the rubrics; it exists now;
  - `hipstraw_mm.shadow` will hold the experiment case, charter, gates and outcome package.

## Decisions needed from Ashish

1. **Scope.** Is the first slice Stage A on Hipstraw itself, with small B2B service and software firms as the
   segment?
2. **Price floor.** What price must a Shadow Launch trial reach? Appendix F illustrates 8,000 HT reserved for one
   Shadow Launch.
3. **Brand.** Should the shadow offer show Hipstraw, or a neutral name with the seller disclosed where material?
4. **Reviewers.** Who reviews the assessment independently (DV08), and who writes the lab expectations?
5. **Authority.** Who signs the charter that authorises the E3 field Moves (interviews, outreach, deposits)?
