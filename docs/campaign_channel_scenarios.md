# Campaign strategy & readiness, channel by channel: scenarios

 A campaign starts from its channels, and each channel reaches a
different audience: Instagram reaches small companies, not enterprise buyers. So Hipstraw's first answer is
per channel: **is this message right for the audience this channel reaches, and is this channel ready to
spend on?** This document has the two scenarios, how marketers test a campaign before they pay for it, and
what Hipstraw checks.

## How practitioners test a campaign before spending

| Practice | What they check | Where Hipstraw does it |
|---|---|---|
| Campaign brief | Objective, target audience, key message, call to action, channels; often timeline, budget and success metrics (HubSpot creative brief) | The launch file: product, audience, objective, then each channel with its own audience, budget, success measure, setup and assets |
| Message testing with the target audience | Clarity, relevance, value and differentiation, all backed by proof (Wynter's message layers, with panels filtered by seniority, industry and company size) | M06, channel by channel: CR01 *Message fits the audience*, CR07 *Outcome, not features*, CR08 *Reason to believe* |
| Channel–audience fit | Each platform reaches different people: LinkedIn targets by job function, seniority and company size. On Meta, job title is self-reported, there is no company-size targeting, and Advantage+ can widen the audience | CR02 *Channel reaches the audience*, judged against the reach notes in `config/campaign/channels.yaml` |
| Message match | The landing page repeats the promise and offer of the ad or email that brought the visitor (Unbounce) | CR04 *Same promise as the landing page*, per channel |
| Platform and legal rules | Email: Gmail/Yahoo sender rules and US CAN-SPAM. Ads: each platform's specs, minimum audience and budget, and conversion tracking | M13 *Check channel standards*, deterministic, each check with its source |
| Pre-send QA | Rendering across clients, spam-filter and seed tests, links tagged with UTM parameters, preview text (Litmus checklist) | M13 `should` checks: practice, so a miss is a fix rather than a blocker |
| A/B test before scaling | Subject-line or message variants sent to a sample first | M07 proposes variants; M09 drafts Test Plans; nothing is sent in G0 |

## Scenario 1: one channel, email

`input/campaign/kozmo_email_us.yaml`

- **Campaign:** Kozmo Invoice Alpha Genesis Cohort, US (New York, San Francisco, Atlanta). Day Zero is 10 November.
- **Audience:** Heads of Accounts Payable and Procurement at companies with 50 to 2,000 employees.
- **Channel:** email to 2,100 opted-in finance, AP and procurement contacts (webinar registrants and the waitlist). Budget USD 1,500.

What Hipstraw finds:

| Question | Answer | Why |
|---|---|---|
| Message fits the audience | Met | The copy names their problem in their words ("Your contract says one price; the invoice says another") |
| Channel reaches the audience | Met | An opted-in list of exactly these roles |
| Same promise as the landing page | **Not met** (reviewer correction) | The email promises a free check of 90 days of invoices. The landing page offers an 8-week cohort by selection ("Request a spot"). The model said "partly"; the reviewer, reading both quotes, corrected it |
| Reason to believe | Not met | No proof point anywhere |

Email rules (M13), 12 checks for a US launch:

- **Unknown (must):** no physical postal address. US CAN-SPAM requires one in every commercial email, B2B included.
- **Fixes (should):**
  - No DMARC record. Required only for senders of 5,000 or more emails a day to Gmail, so a fix here, not a blocker.
  - Unsubscribe is a link, not one-click.
  - The link lacks `utm_campaign`.
  - Success is measured partly by **open rate**, which Apple Mail Privacy Protection inflates.
- **Not stated (should):** no rendering or seed test planned.
- **Met:** list source and consent, SPF/DKIM, unsubscribe link, subject line (39 characters), preview text (84 characters).

## Scenario 2: the same campaign on three channels

`input/campaign/kozmo_three_channels_us.yaml`: email, plus LinkedIn ads (USD 4,500) and Instagram ads (USD 2,000).

| Question | Email | LinkedIn ads | Instagram ads |
|---|---|---|---|
| Message fits the audience | met | met | partly met |
| Channel reaches the audience | met | met | **not met** |
| Same promise as the landing page | not met | not met | not met |
| Written for the channel | met | partly met | met |
| Open blockers | 0 | **1** | 0 |
| Open unknowns | 1 | 0 | 1 |
| Practice fixes | 4 | 2 | 0 |

The difference between the channels:

- **Instagram:** the copy is fine, but the channel cannot reach "Heads of AP at 50 to 2,000 employee companies" precisely: targeting by interests ("accounting, small business") reaches the wrong buyer. Conversion tracking (Meta Pixel or Conversions API) is not stated. The fix is to move the budget, not to rewrite the ad.
- **LinkedIn:** it reaches the right roles by job function, seniority and company size. But the ad copy is ready on 8 November, after the lead-time deadline of 7 November, so it is a **blocker** escalated to the Sponsor. The offer sits in characters 151 to 291 of the intro text, behind "see more" (LinkedIn's guidance is to keep within 150). The audience (38,000) is under the 50,000 LinkedIn suggests.
- **Email:** as in scenario 1.

The verdicts above are from the rehearsal on 30 October (gpt-4o, temperature 0). A live run can word its reasons differently. The M13 checks are deterministic and do not vary.

## What changed in Hipstraw (30 October)

1. **Channel-first input.** The launch file lists `channels`, each with its audience, budget, success measure, setup facts and assets. Email assets have from, subject, preview text, body, call to action, link and footer; ads have intro text or caption, headline, visual, call to action and destination. A vague channel such as `paid_social` becomes an unknown at submission: name the platform.
2. **Rubric v0.2** (`config/campaign/rubric.yaml`):
   - Five questions per channel, led by *Message fits the audience*; four for the whole campaign.
   - No total and no score.
   - A verdict without a word-for-word quote is discarded.
3. **Channel standards** (`config/campaign/channels.yaml`):
   - Covers email, LinkedIn ads, Instagram ads and Reddit ads.
   - Each channel has who it reaches, how it is read, and its checks.
   - `must` is a platform rule, the law, or a fact needed to judge the channel; `should` is practice.
   - Each check names its source.
   - M13 runs them in L01 Readiness-first.
4. **Three views on the page:**
   - **Report:** the answer channel by channel, side by side.
   - **Campaign:** what the customer submitted, with each asset previewed as the channel shows it.
   - **Reviewer desk:** what awaits a decision, and every decision made.
   - Lines, evidence and trace move under **Audit**.
5. **The console** (`hs console`; `hs view` stays read-only). Constitution XIII was amended to v2.0.0.
   - The customer submits a launch from a form built from the channel rules, and accepts or rejects a validated Review.
   - The reviewer accepts, corrects or rejects findings and validates, from the desk.
   - Each action runs the same governed command as the CLI: the role is checked, and every decision is traced and audited.

## Sources (read 30 October 2026)

- Gmail sender guidelines: support.google.com/a/answer/81126 and /14229414. Yahoo: senders.yahooinc.com/best-practices
- FTC, CAN-SPAM compliance guide: ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- India DPDP Act 2023; Rules notified 13 Nov 2025, with notice and consent duties from 13 May 2027
- Litmus: Apple Mail Privacy Protection, preview text, the pre-send checklist. Mailchimp: subject lines, A/B tests. Validity: seed testing
- LinkedIn: ad specs (a426534), targeting (a424655), audience size (a423690), budget, Insight Tag and Conversions API (67513), Lead Gen Forms
- Meta: Instagram feed ad specs, the 2022 targeting removals (sensitive topics only), Advantage+ audience, Conversions API
- Reddit: community targeting, comments on ads. Unbounce: message match. Wynter: B2B message layers. HubSpot: the creative brief

## Open questions for the product owner

1. **Levels.** Should "list source and consent stated" stay a `must` for US email? US law is opt-out, but Gmail's 0.3% complaint limit makes an unknown list risky.
2. **Thresholds.** These come from platform guidance: LinkedIn audience 50,000; subject line 60 and intro text 150 characters. Do they need tuning per market (India)?
3. **Writing from the page: decided 30 October.**
   - The customer and the reviewer act in the browser through `hs console` (constitution XIII, v2.0.0).
   - Still open: should the Campaign Manager also choose and run Lines from the page?
   - Still open: when does real sign-in replace the declared "Acting as" identity?
4. **More channels.** Google Search, display and WhatsApp (India) are not in the standards file yet.
