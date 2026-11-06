# Validating market demand for small businesses

Draft, 2026-11-04. Responds to the Nov 4 meeting: "Develop validation rubrics: draft a document identifying the
criteria and metrics used to validate market demand for small businesses." Follows the Hipstraw Strategic &
Operating Blueprint v0.1, section 07 (rubric family "Demand evidence").

The rubric is in [config/foundry/demand_evidence.yaml](../config/foundry/demand_evidence.yaml). The code that
applies it is [src/hipstraw_mm/foundry/demand.py](../src/hipstraw_mm/foundry/demand.py). The worked case, Hipstraw
itself, is [input/demand/hipstraw_small_business_shadow_launch.yaml](../input/demand/hipstraw_small_business_shadow_launch.yaml).

## The question it answers

**Does this segment demand this offering, at a price that works?** That is demand validation, not market
discovery. The segment and the offering are named before any evidence is read. The answer is one of seven
decisions, each with what is missing and the next Moves to run. There is never a single score.

The rules come from the Blueprint:
- **No single score.** "Rubrics should not all collapse into one score." Each criterion is judged on its own.
- **Gates win.** "A strong average must not override a critical compliance or supply gate."
- **The right to abstain.** Too little evidence means no verdict, not a weak one.
- **Clicks are not demand.** The critical failure this rubric family must catch is "equating clicks with
  willingness to buy".

## The evidence ladder

Every piece of evidence is classified by type. Its type fixes its rung on the ladder.

| Rung | What it is | Examples | Counts as demand |
|---|---|---|---|
| L0 | Simulation or model output | synthetic personas, forecasts | never |
| L1 | Secondary research or expert opinion | industry reports, competitor pricing, case studies | no: says the problem may exist |
| L2 | Attention | ad clicks, page visits, outreach sent | no: attention, not intent |
| L3 | Expressed interest | sign-ups, replies, survey answers, a stated price | yes |
| L4 | Qualified conversation | problem interview or sales call with a decision-maker | yes |
| L5 | Commitment | letter of intent, deposit, pre-order, signed pilot | yes |
| L6 | Paid fulfilment | paid for and delivered | yes |
| L7 | Repeat demand | repeat order or renewal | yes |

Each item also records four things:
- whether it came from the target segment;
- whether it is independent (not the team, friends, existing customers, or a panel told what to answer);
- how many people or instances it stands for;
- which criteria it supports or contradicts.

## The ten criteria, in six demand dimensions

Updated 2026-11-05 (rubric v0.3). The criteria are grouped into Hipstraw's six demand dimensions, as named in the
Nov 5 meeting. Each dimension is judged by its own criteria. A dimension has no score of its own, and the
dimensions are never combined.

| Demand dimension | The question | Criteria |
|---|---|---|
| Problem demand | Is the problem real, frequent and costly enough to act on now? | DE01, DE02 |
| Buyer demand | Who has the problem, and who decides and controls the budget for solving it? | DE10 |
| Solution demand | Would they choose this offering over what they do today, and act on it? | DE04, DE05 |
| Payment demand | Will they commit and pay a price that works? | DE06, DE07 |
| Recurring demand | Do they keep paying, period after period? | DE09 |
| Reachable demand | Can enough qualified buyers be reached, through more than one channel, on independent evidence? | DE03, DE08 |

Thresholds are for the `small_business` profile. Mid-market and enterprise profiles use smaller counts, because
those buyers are fewer and each conversation is worth more.

These are **Hipstraw's starting values, not published standards**. No source sets them. The ~10 interviews follow
the Nov 4 meeting. Field results should recalibrate them.

| ID | Criterion | Metric (from the segment unless noted) | Met | Not met | Gathered by |
|---|---|---|---|---|---|
| DE01 | The problem is real for this segment | problem interviews that confirm the problem unprompted | 6+ of at least 10 interviews | 6+ interviews do not recognise it | DV01, DV02 |
| DE02 | Solving it is a priority now | conversations describing current spending or a workaround they want replaced | 4+ | 4+ say it can wait | DV01, DV02 |
| DE03 | Buyers can be reached | replies or sign-ups through a named channel | 25+ | 100+ reached, no replies | DV09, DV03, DV13 |
| DE04 | Better than what they use today | conversations or commitments saying they would switch from their current alternative, and why | 3+ | 6+ satisfied with what they use | DV01, DV02 |
| DE05 | Interest beyond attention | sign-ups, replies or survey answers; clicks never count | 25+ | 100+ saw it, nobody acted | DV03 |
| DE06 | Concrete commitment | letters of intent, deposits, pre-orders, signed pilots | 3+ | 10+ declined, none committed | DV10, DV05 |
| DE07 | Pays a price that works | commitments or paid orders at or above the price floor | 3+ at or above the floor | all commitments below the floor | DV06, DV10, DV05, DV04, DV12 |
| DE08 | Evidence is independent and representative | sources, channels and independent share of the demand-level evidence | 3+ sources, 2+ channels, 70%+ independent | under 50% independent | DV03, DV13, DV02 |
| DE09 | They pay again (only for offerings bought again and again) | renewals or repeat orders | 2+ customers pay again | 3+ paying customers offered the next period, none paid | DV11 |
| DE10 | The buyer who decides and pays is known | conversations or commitments that name who approves the spend, with that person taking part | 5+ | 6+ say no one with a budget sees the problem as theirs | DV09, DV02, DV10 |

"Partly" means some evidence, short of the threshold. Desk research alone can make DE01, DE02 or DE04 partly; it
can never make them met.

Two cases need their own rule:
- **Contested.** If the evidence meets both the met and the not-met anchors, the criterion is "partly" and flagged
  as contested. For example, 7 interviews confirm the problem and 6 do not. The likely reason is a segment that is
  too broad, so split it rather than average it.
- **Unknown.** No evidence for or against yet.

Rates go in the report as context but are not thresholds: reply rate, sign-up rate per segment visitor, and
interview-to-commitment rate. A rate on a handful of contacts says little; the counts above set the minimum.

## Gates

A gate applies once the evidence reaches its rung. An applicable gate must be confirmed. A gate that is false or
unconfirmed blocks the decision.

| ID | Gate | Applies from | Source |
|---|---|---|---|
| GX1 | Claims were truthful and contacts consented: seller disclosure, actual availability, claims substantiation, contact permission | first field exposure (L2) | Blueprint Appendix E, G2 field exposure |
| GX2 | The offering can be supplied as promised to those who committed | first commitment (L5) | Blueprint G2 and G3 |
| GX3 | The rubric version and decision rule were recorded before the results were seen | first field exposure (L2) | Blueprint section 05: "recorded before the result is interpreted" |

## Decisions

The first decision whose conditions hold wins.

| Decision | When | Next |
|---|---|---|
| Blocked | a gate is not confirmed | fix the gate |
| Disproved | DE01, DE06 or DE07 is not met | independent review (DV08), then reframe or stop |
| Validated | DE01, DE02, DE05, DE06, DE07, DE08 and DE09 met; DE03, DE04 and DE10 at least partly | independent review (DV08) before scaling |
| Promising | DE01 and DE05 met; DE02 and DE08 at least partly | the Moves for whatever is missing, usually a commitment test |
| Problem confirmed | DE01 met; the segment has not yet been shown an offer | a shadow offer (DV03) |
| Abstain | under 5 demand-level items from the segment, and nothing not met | the field Moves |
| Not validated | anything else: segment evidence exists, but not enough of it points to demand | the Moves for whatever is missing |

## Methods: the Moves that gather the evidence

Line LD1, "Demand validation", runs:
DV01 → DV02 + DV03 → DV07 → DV05 + DV06 → DV07 → DV08.
The second half runs only when the first assessment is promising.

Every Move that contacts people, publishes or spends (effect class E3) needs an approved Shadow Launch charter
(Blueprint Appendix E). Hipstraw does not dispatch these Moves itself in G0.

| Move | Effect | What it shows | Its weakness |
|---|---|---|---|
| DV01 Desk scan of the segment and its alternatives | E1 | the problem may exist; who sells what, at what price | says nothing about this segment acting |
| DV02 Problem interviews (~10) | E3 | whether the problem is felt and what it costs today | compliments and future promises mislead; ask about past behaviour (The Mom Test) |
| DV03 Shadow offer page and targeted outreach | E3 | reach and action: replies, sign-ups | a sign-up costs nothing; lists are noisy (Harry's: 100K emails, about 85K valid) |
| DV04 Concierge delivery to a few buyers | E3 | whether people pay for the result delivered by hand | says nothing about cost or scale |
| DV05 Commitment test | E3 | letters of intent, deposits, pre-orders | letters of intent are often non-binding; deposits must be refundable and honoured |
| DV06 Price test | E3 | which price people accept | choosing a plan is not paying |
| DV07 Assess the evidence against this rubric | E0 | the decision, what is missing, next Moves | as good as the rubric, which is still a candidate |
| DV08 Independent review | E0 | a second reader before a consequential decision | needs a reviewer who did not run the test |

## Worked case: do small businesses need a Shadow Launch service?

### Segment and offering

The segment follows the Blueprint's commercial wedge: "B2B professional services, workflow software and
software-enabled services with clear buyer identification and narrow pilot delivery". It is also the Nov 2 focus
on Atlanta IT services.
- **Segment:** US B2B service and software companies, 10–100 staff, planning a new offering or market within 12
  months.
- **Offering:** a managed Shadow Launch.
- **Price floor:** not set yet (see the open questions).

Run it:

```
python -c "from hipstraw_mm.cli import main; raise SystemExit(main())" demand assess --case input/demand/hipstraw_small_business_shadow_launch.yaml
```

### Result today: abstain

| Criterion | Judgement | Why |
|---|---|---|
| DE01 problem real | partly | 15 desk sources describe pre-launch testing and the cost of launching blind; none from the segment |
| DE02 priority | partly, 1 for, 2 against | founders are mostly confident they know demand (LivePlan: 69% of pre-revenue owners); few test (under a fifth of startups A/B test) |
| DE03 reachable | unknown | no channel tried |
| DE04 better than today | partly, 3 for, 3 against | managed help near $1–3K looks thinly served, but do-it-yourself pages ($9/yr up) and AI reports ($0–179) are cheap |
| DE05–DE08 | unknown | no field evidence yet |

Next Moves:
1. DV02: about 10 problem interviews.
2. DV03: a shadow offer page and outreach.
3. DV05 and DV06: commitment and price tests.
4. DV07: assess again.

The desk scan (DV01) has already run.

### Ashish's question: do small companies use blind or shadow launches?

**They test in the real market, small and early. They rarely do it under a hidden brand.** All ten companies
below tested demand before a full launch, and all ran the test themselves. One tested under a different name, but
nothing says that was a deliberate tactic.

Deliberate neutral-brand tests are documented at large companies:
- **Starbucks:** ran "15th Avenue Coffee and Tea" as a three-store test.
- **Facebook:** ran its "NPE Team" apps under a separate brand, always shown as "from Facebook".

Practitioners call this "off-brand testing".

| Company | Size then | How they tested | What it showed | Outcome |
|---|---|---|---|---|
| Buffer | solo founder | two-page fake door, then a pricing page | emails; a few clicked paid plans | first paying customer within 4 days of launch |
| Dropbox | pre-launch | demo video | 75K waitlist sign-ups in a day (15K expected) | launched |
| Zappos | solo founder | took orders for shoes photographed in local stores and bought them when ordered | real orders before inventory | became Zappos |
| Groupon | small team | a blog; coupons sent as PDFs by script | up to 500 coupons sold a day | built the platform |
| DoorDash | 4 students | one-day prototype; founders delivered | first order in 30 minutes; 200 deliveries by hand | Y Combinator, then DoorDash |
| Food on the Table | early startup | concierge service after 150+ conversations | use, by hand | dropped as not cost-effective |
| Innocent Drinks | 3 founders | festival stall; buyers voted with empty bottles | "yes" bin full | founders quit their jobs |
| Three Over Seven (Allbirds) | solo founder | Kickstarter pre-orders under another name | $30K target in about a day | relaunched as Allbirds |
| Harry's | pre-launch brand | referral waitlist | 100K emails in 7 days, 77% from referrals | store opened a week later |
| Supercell, Spooky Pop | mid-size studio | soft launch in Canada and Australia | too few players | pulled; 30+ games stopped this way |

How to read this table:
- These are well-known successes plus one stopped launch. Companies that tested and quietly dropped an idea are
  rarely written up.
- None of the ten is in the target segment. The case therefore counts them only as desk evidence (L1).
- The answer for small B2B firms has to come from interviewing them (DV02).

What it suggests for Hipstraw:
- **The need to test is real**, but the buyer's alternative is to do it themselves.
- **The case for a managed service rests on what do-it-yourself tests lack.** That means discipline, truthful
  exposure, real commitments rather than sign-ups, and a reviewed stop or go.
- **Only interviews can show whether small firms value that enough to pay.**

### Alternatives and prices (checked 2026-11-04)

| Tier | Examples | Price |
|---|---|---|
| Do-it-yourself pages and waitlists | Carrd, Unbounce, LaunchList | $9/yr to $149/mo |
| AI idea-validation reports | ValidatorAI, IdeaProof, DimeADozen | free to $179 (one $149 launch kit) |
| Managed validation sprints | Proof Engine; JAK Solutions | from $4,500 (2–4 weeks); €8,000 (14 days) |
| Closest to a Shadow Launch | Prelaunch.com (ads, deposits, surveys, AI interviewer, concierge); LaunchBoom ($1 deposit funnels, consumer) | not public |
| Enterprise testing and research | Wynter; UserTesting | $20K–100K/yr; median $41.2K/yr |

Context for pricing:
- **Budgets.** 52% of small businesses spend under $1,000 a month on all marketing (LocaliQ 2026). A test costing
  several thousand dollars is months of their budget.
- **Likelier buyers:**
  - funded new ventures, about 1.7M high-propensity business applications in 2025;
  - established firms launching a new line (46% of owners plan a new product or service within 12 months,
    U.S. Bank 2026).
- **Upmarket tools.** Venture money is going into AI interviews and simulated customers for large companies
  (Listen Labs, Simile, Outset, Aaru). These tools could move downmarket, but none produces real commitments.
- **No one uses the name.** No service is sold as a "shadow", "blind" or "stealth" launch.

### Problem interview guide (DV02)

Ask about past behaviour, not the idea (The Mom Test). Record each interview as one evidence item:
- `problem_interview`, from the segment;
- tagged DE01, DE02 or DE04 for or against;
- with the company described, never a person's name.

1. Tell me about the last new offering or market you launched. What happened?
2. Before launch, how did you check that people wanted it? What did that cost in time and money?
3. What did you learn too late? What did that cost?
4. Who decides whether to launch, and who pays for checking first?
5. What do you use today for this: an agency, a tool, your own team, nothing?
6. Is the next launch planned? When? What would you do differently?

Close with a commitment ask, not a compliment ask: a call with the decision-maker, or a letter of intent for a
trial at a stated price (DV05).

## Truth and consent

"Shadow" means low-visibility, not deceptive (Blueprint section 04). These rules feed gate GX1 and the charter:
- **FTC truth in advertising:** claims must be truthful, non-deceptive and backed by evidence. Leaving out material
  information can itself deceive.
- **FTC Mail, Internet or Telephone Order Rule (pre-orders and deposits):**
  - the seller needs a reasonable basis to ship within the stated time, or 30 days if none is stated;
  - any delay needs the buyer's consent;
  - a cancellation is refunded within 7 working days.
- **Off-brand testing practice:** fulfil or refund every commitment promptly. Never keep money for a product you
  do not intend to ship.

## Qualification: this rubric is a candidate

The Blueprint ladder is candidate → lab-tested → shadow-tested → field-qualified → monitored or retired. A candidate
"may help a specialist think, but should not govern high-stakes allocation alone". The report says so on every run.

**Lab set.** There are nine lab cases in
[config/foundry/lab/demand_evidence/](../config/foundry/lab/demand_evidence/), most of them adversarial:
- simulations only;
- clicks without action;
- friends and family;
- an unconfirmed gate;
- commitments below the price floor;
- a contested segment;
- plus validated, disproved and promising cases.

`demand lab` runs them. All nine agree today, but the rubric's author wrote both the rubric and the expected
results. To reach **lab-tested**, someone else should write the expected results, including hard cases.

**Later stages:**
- **Shadow-tested:** apply the rubric alongside real decisions without letting it decide.
- **Field-qualified:** needs prospective results, reviewer consistency and documented limits.

Commands, run from the repo root:

```
python -c "from hipstraw_mm.cli import main; raise SystemExit(main())" demand rubric
python -c "from hipstraw_mm.cli import main; raise SystemExit(main())" demand lab
python -c "from hipstraw_mm.cli import main; raise SystemExit(main())" demand assess --case <case.yaml> [--out <report.md>] [--json]
```

## Open questions for Ashish

1. **Segment.** Start with small B2B service and software firms (the Blueprint's wedge, and Atlanta IT services),
   or test "small businesses" broadly? A broad segment risks the contested result above.
2. **Price floor.** What must a Shadow Launch trial cost? The Blueprint proposes 1 HT = US$1 without a rate card,
   and Appendix F illustrates 8,000 HT for one Shadow Launch. Until a floor is set, DE07 cannot be judged.
3. **Thresholds.** Are 10 interviews, 25 sign-ups and 3 commitments right for small businesses? Who sets lab
   expectations independently?
4. **Brand.** For Hipstraw's own test, show the offer as Hipstraw or under a neutral name, with seller identity
   disclosed where material?

## Sources

All checked 2026-11-04. Figures the research could not confirm at the primary source are noted in the case file
or left out.

**Failure rates and testing practice**
- CB Insights, startup failure reasons (Mar 2026): https://www.cbinsights.com/research/report/startup-failure-reasons-top/
- LivePlan, early-stage owner survey (2023): https://www.liveplan.com/blog/starting/optimism-uncertainty-2023-survey-of-early-stage-small-business-owners
- Koning et al., via Duke Fuqua (2021): https://www.fuqua.duke.edu/duke-fuqua-insights/sharique-hasan-scientific-approach-testing-ideas-helps-startups-fail-and-scale
- Camuffo et al., Management Science (2020): https://pubsonline.informs.org/doi/10.1287/mnsc.2018.3249

**Segment size and budgets**
- U.S. Bank small business survey (2026): https://www.usbank.com/business-banking/business-resource-center/small-business-survey.html
- Census Business Formation Statistics, via FRED: https://fred.stlouisfed.org/series/BABATOTALNSAUS
- LocaliQ, small business marketing report (2026): https://localiq.com/blog/small-business-marketing-trends-report-2026/

**Methods**
- Kromatic, Real Startup Book, off-brand testing: https://kromatic.com/real-startup-book/5-out-of-the-box/off-brand-testing/
- The Mom Test: https://www.momtestbook.com/
- Strategyzer, B2B experiments (2018): https://www.strategyzer.com/library/get-creative-with-your-b2b-experiments
- PocketGamer.biz, soft launch trends (2016): https://www.pocketgamer.biz/data-and-research/63706/soft-launch-trends/

**Truth and consent**
- FTC, advertising FAQs for small business: https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business
- FTC, Mail, Internet or Telephone Order Rule: https://www.ftc.gov/business-guidance/resources/business-guide-ftcs-mail-internet-or-telephone-order-merchandise-rule

**Prices**
- Proof Engine: https://blog.proofengine.studio/startup-idea-validation-cost/
- JAK Solutions: https://www.jak.solutions/service/web-application-development/validation-saas
- Prelaunch.com: https://prelaunch.com/
- Unbounce: https://unbounce.com/pricing/
- Carrd: https://carrd.com/pro
- DimeADozen: https://www.dimeadozen.ai/pricing
- IdeaProof: https://ideaproof.io/pricing
- Wynter: https://www.wynter.com/pricing
- UserTesting, via Vendr: https://www.vendr.com/marketplace/usertesting

**The ten companies:** sources are listed per company in the case file, items E21–E30.
