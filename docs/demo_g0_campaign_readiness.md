# Demo: Hipstraw G0 Campaign Strategy & Readiness Testing

One campaign, channel by channel (30 October meeting): the Kozmo Invoice Alpha Genesis Cohort, US (New York,
San Francisco, Atlanta), Day Zero 2026-11-10. First the **email-only** scenario live, then the **same campaign
on three channels** from the rehearsal. About 12 minutes. Scenarios and sources:
`docs/campaign_channel_scenarios.md`. Spec: `specs/004-campaign-readiness-g0/`.

## Setup (repo root, PowerShell)

Terminal 1, the flow:

```powershell
function hs { & .\.venv\Scripts\python.exe -c "from hipstraw_mm.cli import main; raise SystemExit(main())" campaign --db .runs/demo_live.db @args }
Remove-Item .runs\demo_live.db -ErrorAction SilentlyContinue
```

Terminal 2, the page: define `hs` the same way, then `hs view` and open http://127.0.0.1:8766/. Delete
`demo_live.db` before starting the page (Windows cannot delete a file the page has open), and restart a page
that was started before an update: it keeps the code it started with.

`OPENAI_API_KEY` comes from `.env`. A live run costs a few cents (two gpt-4o calls per Line at temperature 0).

**Rehearsal and fallback:** `.runs/campaign_demo.db` holds both scenarios, fully reviewed and accepted, plus the
29 October launch (judged with rubric v0.1). Their reports are `reports/demo_kozmo_email.md` and
`reports/demo_kozmo_three_channels.md`. To show them, point `hs` at `.runs/campaign_demo.db` and run `hs view`.

## The page: three views and the audit

- **Report:** what the customer finally gets, channel by channel.
  - The headline: *Is this message right for this audience on this channel?*
  - The five channel questions, with quotes, fixes and reviewer corrections.
  - The channel's rules (M13), with sources.
  - With several channels, a side-by-side table.
  - Then the whole-campaign questions, and the open blockers and unknowns.
- **Campaign:** what the customer submitted.
  - Progress: submitted, message and audience checked, readiness checked, report ready.
  - Each channel with who it reaches, its setup and its assets, previewed as the channel shows them: the inbox view of the email; the LinkedIn ad with the text after 150 characters shaded ("see more").
- **Reviewer desk:** what awaits a decision, with the exact command for each decision, and every decision made with its reason.
  - The page stays read-only (constitution XIII); decisions are taken in the CLI.
- **Audit:** Position versions, Reviews, Lines (the tactic record), Evidence, and Trace (every authority-gate decision and model call).

## Flow (email only, live)

| # | Command | Show and say |
|---|---|---|
| 1 | `hs lint` | 13 Moves and 5 Lines are config. Channel rules (`config/campaign/channels.yaml`) and the rubric are versioned config with sources |
| 2 | `hs submit --file input/campaign/kozmo_email_us.yaml --by "Kozmo GTM lead" --as sponsor` | **Campaign** view: a campaign starts from its channel. Email to 2,100 opted-in AP, procurement and finance contacts; the email as the inbox shows it |
| 3 | `hs lines --launch <L>` | Which Lines fit and why. Plain rules, no model |
| 4 | `hs choose --launch <L> --line L02 --reason "core assumptions unverified" --by "Hipstraw CM" --as campaign_manager`, then `hs run --line-run lrun_<L>_1 --by "Hipstraw CM" --as campaign_manager` | M06 answers per channel: is this message right for the audience email reaches? Every verdict quotes the copy word for word. Nothing is sent or spent |
| 5 | **Reviewer desk** | The model's proposals, each with its quotes and the command to decide it |
| 6 | `hs review finding --review rev_<L>_1 --finding <CR04 Email's F..> --correct "The landing page offers an 8-week Genesis Cohort by selection ('Request a spot'); the email promises a free check of the last 90 days of invoices: two different offers." --verdict not_met --reason "the pages make different offers" --by "Hipstraw Reviewer" --as reviewer` | **The key moment.** The model said "same promise: partly". The reviewer, with both quotes side by side, says the offers differ |
| 7 | Accept the rest (below), `hs review validate --review rev_<L>_1 --by "Hipstraw Reviewer" --as reviewer`, `hs review accept --review rev_<L>_1 --by "Kozmo GTM lead" --as sponsor` | Only the Sponsor's acceptance commits Position v2 |
| 8 | `hs choose --launch <L> --line L01 --reason "Day Zero in 11 days" --by "Hipstraw CM" --as campaign_manager`, `hs run --line-run lrun_<L>_2 ...`, then accept, validate and accept as in 7 | M13 checks the email against the rules, each with its source. **Unknown:** no postal address (US CAN-SPAM). **Fixes:** no DMARC, link not tagged with `utm_campaign`, success measured by opens (Apple Mail Privacy Protection inflates them) |
| 9 | **Report**, then `hs report --launch <L> --out reports/demo.md` | The answer for the email channel, then the whole campaign. **No score, no forecast** |
| 10 | Switch `hs` to `.runs/campaign_demo.db`, restart `hs view`, open the three-channel launch | **Side by side:** the same message fits on email and LinkedIn, but Instagram does not reach Heads of AP at 50 to 2,000 employee companies. LinkedIn has a blocker: the ad copy is ready after the lead-time deadline, and its offer sits behind "see more" |

Accept every remaining finding of a Review (step 7 and step 8):

```powershell
$R = "rev_<L>_1"
((hs review show --review $R --json) -join "" | ConvertFrom-Json).findings | Where-Object reviewState -eq "pending" |
  ForEach-Object { hs review finding --review $R --finding $_.findingId --accept --reason "checked against the evidence" --by "Hipstraw Reviewer" --as reviewer --json | Out-Null }
```

## Answers to have ready

- **"Is this message good for this audience?"**
  - Rubric v0.2 answers it per channel: *Message fits the audience*, *Channel reaches the audience*, *Offer and one next step*, *Same promise as the landing page*, *Written for the channel*.
  - Four more questions cover the whole campaign: specific audience, outcome, proof, market.
  - Every verdict quotes the campaign; there is no total.
  - Verdicts are proposals until a reviewer checks them.
- **"How do marketers test this?"**
  - Message testing with the target audience: clarity, relevance, value, differentiation.
  - Message match with the landing page.
  - Platform rules and pre-send QA.
  - A/B tests on a sample before scaling.
  - `docs/campaign_channel_scenarios.md` maps each practice to where Hipstraw does it, with sources.
- **"Why can't the customer type in the page, or the reviewer click accept?"**
  - Constitution XIII: the UI is a read-only viewer, so the page has no second, ungoverned path that writes.
  - The desk shows the exact command instead.
  - A governed write path (forms with role checks) is a decision for the product owner.
- **"Launch orchestrator":** every choice, deviation and correction is in the tactic record, per channel. That is the G0 → G1 evidence.
