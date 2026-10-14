# Market Mastery Playbook v0.1: gaps found in review

Review of *The Hipstraw Market Mastery Playbook* (v0.1, 13 Oct 2026) against itself and the
*Market Mastery Master Workbook* v0.2. Recorded for discussion, not applied: the playbook is still a
working draft (agreed 14 Oct 2026).

Every card was cross-checked against the tables that refer to it with a script: 16 Strategies,
32 Plays, 20 Lines, 56 Moves, 12 Gambits, 60 Actions, and 80 names against the workbook. Apart from
the three stance mismatches below, every reference agrees. The situation finder matches workbook §10
and the market type × Play table matches workbook §9.3.

## Gaps in the rules

These affect how an agent decides.

1. **Most axes have no Unknown state.** Rule 3 says missing evidence means Unknown, but only MP2 has
   an Unknown state. MP1, MP3–MP7 start at states that make a claim (Not mapped, Concept, Untested,
   Fragile, Not modeled, First of its kind). The cases already drift: C6 writes "MP5 · Unknown", which
   is not a defined state, and C1 leaves MP5 and MP7 out. Suggested fix: a "Not assessed" state on
   every axis.
2. **Nothing says how to pick the binding constraint.** It sets the default stance, so an agent needs a
   rule. One option: the axis behind the lowest evidence gate not yet passed, with a tie-break order.
3. **Every case runs several Plays at once,** which common mistake #4 warns against (C1: P04 with
   P02; C2: P07, then P19 with P22). Suggested fix: a primary Play plus named supporting Plays.
4. **Stage grouping moved more Plays than decision 4 lists.** Besides P27 and P32, P04 moved from
   Explore to Develop, P08 from Explore to Build, P21 from Build to Develop, and P23 to Scale.
5. **The suggested v1 core (decision 9) fits the local-services pilot only.** It covers none of the
   Plays or Lines that C1 or a B2B program uses (P04, P11, P17, L03, L07).

## Stance mismatches

6. Three Plays have a default stance that their own primary Strategy and first Line do not allow:
   - P25 Channel Saturation and Renewal: Probe; S10 and L10 run in Activate, Build, Expand.
   - P29 Creator / Community Fit: Probe; S14 and L14 run in Co-create, Listen.
   - P26 Permission and Compliance Review: Protect; S13 and L13 run in Scout, Listen, Co-create.
7. Minor: MP4 Saturated calls for S10, which shares only Protect with that state's allowed stances.

## Case C1 (vertical B2B SaaS)

- **The stance does not fit the Gambit.** C1 sets Probe; G02 runs only in Co-create (default) or
  Activate, and Activate is ruled out by MP1 and MP3. The design-partner work should switch to
  Co-create, which is L07's default and allowed by every C1 axis.
- **Steps and Actions do not match.** The Steps list M10, whose Actions (A11, A12) are absent. The
  Actions include A15 and A16 (from M14), A30 (M28) and A58, A59 (M56), whose Moves are not in the Steps.
  A consistent chain: L03 = M09 → A10 → M14 → A15 → A16, then L07 = M17 → M24 → M37 → A40 → M28 →
  A30 → M56.
- **M10 comes from P02, but P02's Lines (L02, L06) are not used.** Either add L06, or drop P02 and make
  M37 the request for a paid slot.
- **Two buying archetypes share one Position** ("strong for RevOps, weak for CIOs"). The archetype is
  part of the market unit, so the unit should be RevOps only, with CIO recorded as a rejected
  alternative.
- **Price before economics.** A $20,000 list price is set while MP6 is Not modeled. Running A10 (L03's
  economics step) first moves MP6 to Assumed.
- MP5 and MP7 should appear as not assessed. G02 needs its fallback and approver (rule 14).
- The numbers check out: 40% off $20,000 is $12,000; two partners make a maximum loss of $16,000,
  under the $25,000 investment-authority threshold.

## Other cases and layout

- C2 records MP5 as Fragile with 15% cancellations against a 10% gate, which meets the playbook's own
  definition of Broken.
- Workbook cases 04 (two-sided, AR07) and 08 (adjacency, AR06) were dropped, so those market types
  have no worked example.
- Each case's table starts on the following page; page 72 holds only C1's introduction.
