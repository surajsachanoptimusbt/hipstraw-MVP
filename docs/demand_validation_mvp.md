# Demand validation MVP: from a market thesis to a program

5 Nov 2026, updated 6 Nov (rules pick the Lines; the web app). Responds to the Nov 5 meeting:
- build an MVP that takes a product and its market and works out how to validate demand, using Lines and Moves;
- produce a demand scorecard;
- show a complete walkthrough log of what it picked and why.

This is market demand validation, not market discovery: the input is a thesis that discovery already produced.

## Same repository

The MVP lives in this repository, in `hipstraw_mm.foundry`, beside the campaign module.

**Why:**
- It reuses what is already here: the demand evidence rubric, the Faculty pattern of Lines and Moves (use-when and
  exclude-when rules, effect classes, charter before E3), the CLI and the report and page patterns.
- A new repository would rebuild all of that before showing anything.
- The product is a single team, deployment and constitution.

**When to split:** only if it becomes a separately deployed product with its own team or customers. Nothing today
needs that.

Zimplii appears only as an example input (a thesis file). No Zimplii code is used.

## Lines picked by the playbook's rules (6 Nov)

The 6 Nov meeting settled it: **no model decides the Lines.** "We already have lines. We already have moves...
we don't need LLM for that." Lines and Moves are predefined and proven, and the playbook's rules pick them. The
model-decided version of the morning of 6 Nov was removed.

The Lines and Moves are in [config/foundry/demand_repertoire.yaml](../config/foundry/demand_repertoire.yaml); the
worksheet [docs/hipstraw_demand_lines_and_moves.xlsx](hipstraw_demand_lines_and_moves.xlsx) lists them.

**The four tasks, and the Lines each can take:**

| Task | Lines it can take |
|---|---|
| T1 Confirm the problem and who pays | LD0 Reframe or stop, LD1 Problem first |
| T2 Test purchase | LD2 Paid pilot, LD3 Shadow offer |
| T3 Test repeat purchase | LD4 Recurring conversion, or no Line |
| T4 Test economics and reach | LD5 Economics and reach |

**How a Line is picked** ([src/hipstraw_mm/foundry/playbook.py](../src/hipstraw_mm/foundry/playbook.py)):
1. List the task's available Lines.
2. Check each Line's conditions against the hypothesis (buyer, sales motion, bought again, how far the problem is
   shown).
3. Rank the eligible Lines in playbook order.
4. Pick the first.

Every pick keeps the Lines that were available and why each was or was not eligible. Jev may later help rank Lines
within a scenario; it stays deferred (constitution XI), so the playbook order ranks alone.

**Where it is shown:** the Hipstraw web app, which has the reviewer desk and the customer workspace. See
[hipstraw_web_mvp.md](hipstraw_web_mvp.md).

## Run it

```
.venv\Scripts\python scripts\start_hipstraw.py      # the desk API and the web app, then the reviewer desk opens
```

From the command line:
- `hipstraw-mm demand recommend --thesis <file>`: the Line picked for each task, and the Lines that were not
  eligible;
- `hipstraw-mm desk submit --thesis <file>`: open a case at the reviewer desk; the agent works it;
- `hipstraw-mm demand worksheet`: rewrite the worksheet from config, after the Lines or Moves change;
- `hipstraw-mm demand program --thesis <file>`: the full written program as a static page (the 5 Nov version).

**A new product:** send a request from the customer workspace, or copy a thesis file and fill in:
- the product, market, buyer and how it is sold;
- one entry per demand hypothesis: a segment, an offering, who decides and pays, and the buying triggers.

## The full written program (5 Nov, `demand program`)

The log has 13 steps. Each says what the agent did and lists what it looked at, what it picked and why:

1. **Read the market thesis:** the product, market, buyer, sales motion, source, the starting point (an existing
   market plan or account list) and the hypotheses.
2. **Set what demand validation must show:** Hipstraw's six demand dimensions and the rubric questions that judge
   each. Only actions count as demand, and there is no total.
3. **Frame one demand question per hypothesis:** does this segment demand this offering? It also names who decides
   and pays, and the buying triggers.
4. **Place the evidence so far on the ladder:** every item with its type, rung, source and independence. Rungs 3
   to 7 count as demand; simulations, desk research and clicks do not.
5. **Judge each hypothesis on the six demand dimensions:** each rubric question met, partly, not met or unknown,
   with why, then the decision.
6. **Read each hypothesis's market:** the four facts the Lines' conditions test (buyer, sales motion, bought again,
   how far the problem is shown), and where each came from.
7. **Choose the Lines (strategies), phase by phase:** every Line considered, each condition checked, and chosen or
   not.
8. **Pick the Moves (methods) of each chosen Line:** each Move by stage, filled in for this market, with:
   - the demand dimensions it tests;
   - the evidence types it records and their rung;
   - when it passes (its indicator, now against its target);
   - what it needs first.
9. **Map each demand dimension to its Lines, Moves and evidence,** with its indicators.
10. **Set the demand scorecard,** grouped by demand dimension; never added up.
11. **Set the checkpoint rule:** continue, revise or stop, by rubric decision.
12. **Order the hypotheses and name the first action.**
13. **List what needs a decision.**

The page shows the same log (open any line for the detail under it), then one card per hypothesis:
- **The program at a glance:** one Line per phase and its Moves in order, with done and next marked.
- **Demand dimensions:** for each of the six, its rubric questions now, the Lines and Moves that test it, the
  evidence they record, and its indicators.
- **Lines considered,** with each condition checked.
- **The chosen Lines in detail.** Each Line shows its strategy, why it was chosen, what it tests and when it is
  done. Each Move shows, for this market:
  - what it does and how, step by step;
  - what it needs, the evidence it records and what it tests;
  - when it passes, what it gives, and what to watch out for.
- **The demand scorecard and the rubric questions,** grouped by demand dimension.

A **repertoire** section lists every Line and Move the agent could pick, and which hypotheses each was picked for.

The phases and their Lines:

| Phase | What it tests | Lines |
|---|---|---|
| 1 | reach and problem | LD1 Problem first, or LD0 Reframe or stop |
| 2 | purchase | LD2 Paid pilot (sales-led B2B) or LD3 Shadow offer (self-serve) |
| 3 | repeat purchase | LD4 Recurring conversion, only for offerings bought again |
| 4 | economics and reach | LD5 Economics and reach |

For Zimplii, the three hypotheses get different programs from the same rules:

| Hypothesis | How it is sold | Program |
|---|---|---|
| H1 active-project assurance | sales-led, recurring | LD1 → LD2 → LD4 → LD5 |
| H2 pre-engagement verification | self-serve, one-time | LD1 → LD3 → LD5 |
| H3 continuous assurance | sales-led, recurring | LD1 → LD2 → LD4 → LD5 |

All three are "not enough evidence yet" today: everything so far is desk research. The first action is to map 150
Atlanta accounts from the existing market plan, each with a live buying trigger and the person who approves the
spend. That is also the example's own top next step.

## How it maps to the GPT example, and where it differs

The six demand dimensions are now the rubric's own grouping (v0.3):

| Demand dimension | Hipstraw rubric questions | Main Moves |
|---|---|---|
| Problem demand | DE01 the problem is real, DE02 it is a priority now | DV01, DV02 |
| Buyer demand | DE10 the buyer who decides and pays is known (new in v0.3) | DV09, DV02, DV10 |
| Solution demand | DE04 better than what they use today, DE05 interest beyond attention | DV01, DV02, DV03 |
| Payment demand | DE06 commitment, DE07 pays a price that works | DV10, DV05, DV06, DV04, DV12 |
| Recurring demand | DE09 they pay again | DV11 |
| Reachable demand | DE03 buyers can be reached, DE08 independent sources and channels | DV09, DV03, DV13 |

The example's demand indicators map onto the scorecard:

| The example's indicator | Hipstraw scorecard |
|---|---|
| Problem exists | SC02 buyer interviews held, SC03 raised the problem unprompted, SC04 already spend on it |
| Differentiation | SC05 see value beyond what they use today |
| Commercial interest | SC06 acted on the offer (requests, replies, sign-ups) |
| Willingness to pay | SC07 commitments |
| Fulfilment | SC08 paid and delivered |
| Recurring demand | SC09 paid again |
| Market accessibility | SC01 accounts mapped with a live trigger, SC10 channels bringing qualified buyers |
| (none) | SC11 budget holders named and taking part |

| The example's stages | Hipstraw Moves |
|---|---|
| A. Map reachable buyers | DV09 |
| B. Buyer interviews | DV02 |
| C. Test purchase intent | DV03 |
| D. Sell 3 paid pilots | DV10, DV04 |
| E. Validate ongoing assurance | DV11 (Line LD4) |
| F. Economics and distribution | DV12, DV13 (Line LD5) |

Where Hipstraw's own approach differs:
- **No combined gate score.** The example's "initial gate completion 0/5" is a combined count. Hipstraw has no
  such number: the indicators sit side by side, and the rubric's rules decide.
- **Only actions count.** Clicks, simulations and desk research never count as demand.
- **Gates block.** Truthful claims and consent, the ability to deliver, and rules fixed before results all block a
  decision until confirmed.
- **It can abstain.**
- **One-time sales are not recurring demand.** Recurring demand is judged only for offerings bought again, and one
  sale never counts as recurring.
- **Interview targets differ.** The example plans 18 interviews across four buyer types; the rubric asks for 10 per
  hypothesis. This is listed as a decision for review.

## Limits of this MVP

- **Few Lines per task.** Most tasks offer one or two Lines, so most picks are made by a single condition. A
  richer playbook needs more proven Lines per scenario.
- **Theses are entered by hand.** The Zimplii thesis file was written by hand from the discovery output.
- **No field evidence yet.** Every hypothesis therefore starts at "not enough evidence".
- **Draft thresholds.** The rubric is a candidate, and its thresholds are starting values.

## Next increments

1. **Drafting the thesis from the discovery output.** Today the thesis is entered by hand or in the customer
   workspace's form.
2. **Evidence as the Moves run.** Interview records, sign-up exports and signed pilots would feed in, so the
   scorecard and decisions update each time.
3. **Charter and gates** (Blueprint Appendix E, gates G1 to G4) for the Moves that contact people, publish or spend.
4. **More proven Lines per task,** so the playbook ranks real alternatives for each scenario.
