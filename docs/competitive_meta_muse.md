# Meta Muse: what it is and what it means for Hipstraw

Researched 2 November 2026 for the Nov 2 meeting. Facts first, each with its source and date; our reasoning is
separate and marked as such.

## Facts

- **Launch:** Meta launched **Muse**, a personal AI agent, on **8 September 2026** on iOS, Android, the web
  (muse.ai) and WhatsApp. It runs on **Muse Spark**, a model from Meta's Superintelligence Labs.
  [about.fb.com, 2026-09-08](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)
- **Regions:** the **US** first, then **Canada** (18 September) and **Singapore** (27 October). We found no Meta
  announcement for India. Only third-party blogs mention a waitlist.
  [iphoneincanada.ca](https://www.iphoneincanada.ca/2026/09/18/metas-muse-ai-agent-is-now-available-in-canada/),
  [about.fb.com, 2026-10-27](https://about.fb.com/news/2026/10/muse-is-now-available-in-singapore-the-worlds-first-personal-ai-agent-built-for-everyone/)
- **Price:** "free for most of what people need", but not entirely free. TechCrunch reports paid tiers, **Power at
  $20/month and Maximum at $100/month**, with a usage meter and a card required at sign-up.
  [TechCrunch, 2026-09-08](https://techcrunch.com/2026/09/08/meta-debuts-its-muse-ai-agent-will-consumers-trust-it/)
- **It keeps working:**
  - It "keeps working after people close the app" and comes back "when something changes or needs approval". It browses, fills in forms and checks out with a one-time card ([Meta launch post](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)).
  - Tasks can repeat **daily, weekly or on a custom interval** ([Meta Help](https://www.meta.com/help/artificial-intelligence/1484325780075655/)).
- **Muse for Small Business** (29 September 2026, US and Canada):
  - **Connections:** Instagram professional analytics, Facebook Pages and **Meta ad accounts**, plus Shopify, Klaviyo, HighLevel, QuickBooks, Canva, Slack and Notion.
  - **Example tasks:** "How do I improve my ads and content?", which campaigns are working, a draft campaign for next week, and a monthly performance review.
  - **Drafts:** it drafts posts and "a new ad campaign for the user to review".
  - Sources: [about.fb.com, 2026-09-29](https://about.fb.com/news/2026/09/introducing-muse-small-business/), [Fox Business](https://www.foxbusiness.com/technology/meta-puts-popular-new-tool-hands-small-businesses).
- **Ad-account access is undefined:** Meta has not said whether Muse can only read the ad account or can also create, edit or launch campaigns. [PPC Land, 2026-10-11](https://ppc.land/metas-muse-agent-gains-access-to-ad-accounts-and-15-business-tools/)
- **Controls:**
  - "Nothing publishes, sends, or spends without your approval." It asks before every write action, and users can set "Always allow" per connector ([Meta Help](https://www.meta.com/help/artificial-intelligence/1385290430137537/)).
  - It runs in an isolated VM with a separate approval agent.
  - Interactions train Meta's models **by default**, with an opt-out ([Meta Help](https://www.meta.com/help/superintelligence/2225571704857152/)).
- **Uptake:** about 2.5M downloads in its first 13 days. ChatGPT had 3.1M and Claude 0.4M in the same window.
  [CNBC, 2026-09-21](https://www.cnbc.com/2026/09/21/meta-muse-personal-ai-agent-downloads.html)

**Not verified:**
- that Muse does market discovery, competitor research or pre-launch "campaign readiness" checks; Meta describes none of these;
- an official India waitlist;
- whether it has moved to Meta's newer models.

## What it means for Hipstraw (our reasoning)

- **Ashish is right on the core point.** A free-to-start agent that works on a schedule and can read a
  business's Meta ad account sets the bar at *daily*. A weekly or manual review will not compete. That is why
  the daily review (L06) and the simulation were built this week (`docs/campaign_live_simulation.md`).
- **Where Hipstraw is different:**
  - **Pre-launch readiness across channels:** email, LinkedIn and Instagram, each against its own rules with sources. Muse looks back at performance and forward at drafting.
  - **Independent of the ad seller:** Meta sells the ads Muse advises on. Hipstraw has no stake in where the budget goes; in the simulation its first direction moved budget *off* Instagram.
  - **Evidence and review:** every verdict quotes the campaign, every Delta names what else changed, a reviewer checks it, and everything is audited. That suits B2B buyers who answer to a CFO.
  - **B2B and India:** Muse for Small Business targets small businesses in the US and Canada, and trains on user data by default. Mid-market B2B buyers, and India, are open.
- **What to watch:** whether Muse's ad-account access becomes write access, whether it adds LinkedIn or email platforms, and when it reaches India.
