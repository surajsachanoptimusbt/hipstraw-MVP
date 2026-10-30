# Demo: Hipstraw G0 Campaign Strategy & Readiness Testing

One campaign, channel by channel (30 October meeting): the Kozmo Invoice Alpha Genesis Cohort, US (New York,
San Francisco, Atlanta), Day Zero 2026-11-10. First the **email-only** scenario live in the browser, then the
**same campaign on three channels** from the rehearsal. About 12 minutes. Scenarios and sources:
`docs/campaign_channel_scenarios.md`. Spec: `specs/004-campaign-readiness-g0/`.

## One command (any machine)

`python scripts/campaign_demo.py` runs both scenarios end to end through the same commands as the flow below:
submit, L02, review, L01, review, report. The reviewer and Sponsor decisions are scripted. It then opens the
console on http://127.0.0.1:8766/. It needs `OPENAI_API_KEY` in `.env`. Use `--read-only` for the read-only
page, or `--no-view` to skip the page.

## Setup (repo root, PowerShell)

Terminal 1, for the Campaign Manager's steps (choosing and running Lines stay in the CLI):

```powershell
function hs { & .\.venv\Scripts\python.exe -c "from hipstraw_mm.cli import main; raise SystemExit(main())" campaign --db .runs/demo_live.db @args }
Remove-Item .runs\demo_live.db -ErrorAction SilentlyContinue
```

Terminal 2, the page: define `hs` the same way, then `hs console` and open http://127.0.0.1:8766/.
- `hs view` serves the same page read-only.
- Delete `demo_live.db` before starting the page, because Windows cannot delete a file the page has open.
- Restart a page that was started before an update; it keeps the code it started with.

`OPENAI_API_KEY` comes from `.env`. A live run costs a few cents (two gpt-4o calls per Line at temperature 0).

**Rehearsal and fallback:**
- `.runs/campaign_demo.db` holds both scenarios, fully reviewed and accepted, plus the 29 October launch (judged with rubric v0.1).
- Their reports are `reports/demo_kozmo_email.md` and `reports/demo_kozmo_three_channels.md`.
- To show them, point `hs` at `.runs/campaign_demo.db` and run `hs view`.

## The page: three views and the audit

- **Report:** what the customer finally gets, channel by channel.
  - The headline: *Is this message right for this audience on this channel?*
  - The five channel questions, with quotes, fixes and reviewer corrections.
  - The channel's rules (M13), with sources.
  - With several channels, a side-by-side table.
  - Then the whole-campaign questions, and the open blockers and unknowns.
- **Campaign:** what the customer submitted.
  - Progress: submitted, message and audience checked, readiness checked, report ready.
  - Each channel with who it reaches, its setup and its assets, previewed as the channel shows them.
  - When a Review is validated, the Sponsor's decision appears here.
- **Reviewer desk:** what awaits a decision, and every decision made with its reason.
  - In the console: Accept, Correct… and Reject… on each finding, then Validate.
  - In the read-only page: the exact CLI command for each decision.
- **Audit:** Position versions, Reviews, Lines (the tactic record), Evidence, and Trace (every authority-gate decision and model call).

**Console (constitution XIII, v2.0.0):** "Acting as" in the top bar sets the person and role (sponsor, reviewer,
campaign manager). Every action runs the same governed command as the CLI, so the authority gate refuses a role
without the right, and every decision is traced and audited. The only actions are:
- the Sponsor submits a launch (**+ New launch**) and accepts or rejects a validated Review;
- a reviewer accepts, corrects or rejects findings and validates.

## Flow (email only, live)

| # | Where | Show and say |
|---|---|---|
| 1 | Terminal: `hs lint` | 13 Moves and 5 Lines are config. Channel rules (`config/campaign/channels.yaml`) and the rubric are versioned config with sources |
| 2 | Browser, acting as **sponsor**: **+ New launch**, then **kozmo email us** and **Submit launch** | The customer's interface: a campaign starts from its channel. The form is built from the channel rules: list source, consent, SPF/DKIM, subject line, preview text, footer. The **Campaign** view then shows the email as the inbox shows it |
| 3 | Terminal: `hs lines --launch <L>`, `hs choose --launch <L> --line L02 --reason "core assumptions unverified" --by "Hipstraw CM" --as campaign_manager`, `hs run --line-run lrun_<L>_1 --by "Hipstraw CM" --as campaign_manager` | M06 answers per channel: is this message right for the audience email reaches? Every verdict quotes the copy word for word. Nothing is sent or spent |
| 4 | Browser, acting as **reviewer**: **Reviewer desk** | The model's proposals, each with its quotes. **Correct…** "Same promise as the landing page (Email)" to **Not met**, with the reason "the pages make different offers". **The key moment:** the model said "partly"; the reviewer, with both quotes side by side, says the offers differ |
| 5 | Same: **Accept** the rest, then **Validate Review** | Each decision is audited with its reason (Decisions made) |
| 6 | Browser, acting as **sponsor**: **Campaign**, then **Accept: commit the next Position** | Only the Sponsor's acceptance commits Position v2 |
| 7 | Terminal: `hs choose ... --line L01 --reason "Day Zero in 11 days" ...`, `hs run --line-run lrun_<L>_2 ...`; then steps 5 and 6 in the browser | M13 checks the email against the rules, each with its source. **Unknown:** no postal address (US CAN-SPAM). **Fixes:** no DMARC, link not tagged with `utm_campaign`, success measured by opens (Apple Mail Privacy Protection inflates them) |
| 8 | Browser: **Report**; terminal: `hs report --launch <L> --out reports/demo.md` | The answer for the email channel, then the whole campaign. **No score, no forecast** |
| 9 | Show the gate: act as **reviewer** and try **Submit launch** (disabled), or ask why | The role's rights come from `config/campaign/roles.yaml`; the server refuses and audits even if the page is bypassed |
| 10 | Switch to `.runs/campaign_demo.db` (`hs view`), open the three-channel launch | **Side by side:** the same message fits on email and LinkedIn, but Instagram does not reach Heads of AP at 50 to 2,000 employee companies. LinkedIn has a blocker: the ad copy is ready after the lead-time deadline, and its offer sits behind "see more" |

The terminal works for every step as well (`hs submit --file input/campaign/kozmo_email_us.yaml ...`,
`hs review finding ...`). To accept every remaining finding of a Review from PowerShell:

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
- **"Is it safe to write from the browser?"**
  - Constitution XIII (v2.0.0) allows a governed console: the same governed commands as the CLI, only the approved actions, loopback only, a per-session token and an Origin check.
  - The gate checks every role, and every action is audited.
  - Identity is declared as on the CLI until authentication exists.
- **"Launch orchestrator":** every choice, deviation and correction is in the tactic record, per channel. That is the G0 → G1 evidence.
