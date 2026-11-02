# Live campaign simulation: how Hipstraw reviews a running campaign every day

From the 2 November 2026 internal meeting. A campaign is running and not doing well. How does Hipstraw see it,
what direction does it give, and how do we know the change worked? This is a 14-day walkthrough on email,
LinkedIn and Instagram, reviewed **daily**, not weekly.

**This is a simulation.** The daily numbers come from a response model in
`input/campaign/simulations/kozmo_atlanta_14_days.yaml`, not from Kozmo or any platform. Every metric record
says so. Everything else is real: every review, diagnosis, Delta and audit record runs through the same
governed operations as the CLI. Hipstraw never sees the model; it diagnoses from the exported numbers alone.

## Run it

```powershell
hs simulate          # writes 14 daily exports and runs 14 daily reviews; prints the walkthrough
hs view              # Performance view: the timeline, and each channel's charts
hs report --launch <L> --out reports/simulation.md
```

`python scripts/campaign_demo.py` runs it too, after the two pre-launch scenarios.

## The campaign

The campaign is Kozmo's Invoice Alpha Genesis Cohort, aimed at **Atlanta IT-services and software-services
companies (50 to 500 employees)**. That is one of the micro-markets from the market-discovery work. Day Zero is
10 November 2026.
- **Email:** 1,200 contacts.
- **LinkedIn ads:** Accounting, Finance and Purchasing, Manager to VP, Atlanta IT services.
- **Instagram ads:** interests: small business, accounting, technology.

Before launch, L01 Readiness-first found practice fixes: no DMARC; the LinkedIn offer sits behind "see more";
the LinkedIn audience is under 50,000. The Sponsor launched anyway.

## What happened, day by day

The simulation holds four problems, one planted per channel plus one that appears later. Hipstraw has to find
each one from the numbers.

| Day | What Hipstraw saw (L06 daily review) | Direction | Applied | Delta (observational) |
|---|---|---|---|---|
| 1 | **Email:** spam complaints 0.43%, over Gmail's 0.30% limit (DX01). A **blocker**: mail risks rejection | Stop sending to addresses without opt-in or 90-day engagement; one-click unsubscribe; DMARC | Day 2 (list cleaned to 780) | Day 5: **0.43% → 0.00%**, supported |
| 1 | **Instagram:** 0% of 9 applications from the target roles and company sizes (DX05) | Pause Instagram; move its budget to LinkedIn, which targets by role and company size | Day 2 | Day 5: campaign cost per qualified application **$400 → $300**, supported. Day 1 had no qualified application, so $400 is a lower bound |
| 2 | **LinkedIn:** clicks but no applications, 0% against a 4.02% benchmark (DX04) | Make the landing page repeat the ad's promise (the free 90-day check), or use the lead form | Day 3 | Day 6: **0% → 5.98%**, supported |
| 2 | **Repertoire gap:** LinkedIn cost per click $14.76 against an $8.99 benchmark, and no rule reads cost per click | For the domain owner: a candidate new rule or Move | n/a | n/a |
| 4 | Email complaint rate back under the limit: **blocker cleared** | n/a | n/a | n/a |
| 9 | **LinkedIn:** CTR down to 0.42%, 30% or more off its best, and each member has seen the ad more than 3 times (DX07, creative fatigue) | Refresh the creative: new image and first line; rotate two versions | Day 10 | Day 13: **0.42% → 0.57%**, supported |

Over the 14 days: 21 qualified applications from 37, $5,580 spent, $266 per qualified application.

Every Delta names the other changes made in the same days. On days 2 and 3, three changes landed together, so
no single one can claim the whole improvement.

## How the daily review works

- **Line L06, Daily performance review**, runs every day the campaign is live with metrics:
  - **M11 Record observation and Delta** (v2): for each direction the Sponsor applied, it compares the measure over the 3 days before the change with the days since, once 3 days have passed. A 20% move in the expected direction reads as supported; no move or a wrong-way move reads as not supported. Always observational.
  - **M14 Review live performance** (new): each channel's measures over the last 3 days, computed from counts, against sourced benchmarks. Rules then turn a gap into a direction (a hypothesis plus a Direction record), or into a blocker for a delivery defect. A measure with too little data waits; it is never judged.
  - **M09** drafts a Test Plan for each direction: before and after, with the success line and when to revert.
  - **M12** escalates only what is new.
- **The rules** live in `config/campaign/performance.yaml`, in funnel order: delivery (DX01), worn-out creative (DX07), weak copy (DX02, DX03), landing mismatch (DX04), wrong audience (DX05), under-delivery (DX06). Every benchmark and rule names its source:
  - Gmail sender rules;
  - Mailchimp email benchmarks;
  - ZenABM LinkedIn 2026;
  - LinkedIn's Lead Gen Forms data;
  - LocaliQ Meta 2026;
  - Unbounce 2024;
  - WordStream and LinkedIn guidance on fatigue and under-delivery.

  Where no platform publishes a number (minimum data, a frequency limit), the file says it is Hipstraw's own.
- **People still decide.** The reviewer accepts or corrects each finding and the Sponsor accepts the Review; in the simulation, both accept everything. Hipstraw applies nothing: the Sponsor applies the change on their own platform and records it (`hs applied`).
- **The daily feed.** `hs metrics --launch L --file day.csv` adds a day's export as evidence. In G0 a person supplies the file; a platform connector can call the same operation for truly continuous review.

## Toward self-improvement

Ashish's long-term view is that the system should learn new Lines and Moves as the industry changes. A first,
concrete step is already here: a measure far from its benchmark that **no rule reads** is raised once as a
**repertoire gap**. In this run, that was LinkedIn cost per click. Today a person turns a gap into a new rule or
Move. Later, a coding agent can draft that rule and its tests for review, under the same constitution:
proposals first, nothing changes canonical state without review.

## Limits, said plainly

- **Scripted market:** the simulated market responds as the scenario says. A change helps only if it addresses a problem the scenario holds.
- **Benchmarks are averages:** they come from other companies' campaigns, mostly all-industry or B2B, not this audience.
- **Deltas are not causal proof:** they compare before and after, and other changes in the same days are named, not ruled out.
- **Nothing runs on a schedule:** the daily review runs when the command runs. A scheduler and platform connectors are the next step.
