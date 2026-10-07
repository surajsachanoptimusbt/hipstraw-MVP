# Feature Specification: Find and Review Target Companies for a Micro-Market

**Feature Branch**: `002-objective-to-target-companies`

**Created**: 2026-10-05

**Status**: Draft

**Input**: User description: "Market objective to target companies (Market Manager MVP, smallest unit).
Given the Kozmo Genesis program objective, find real companies in the most promising candidate
micro-markets and prepare them as a reviewed list ready to hand off to the campaign side. This
tests the core hypothesis: from a market objective, HipStraw can identify the respective companies
for that market." Narrowed to its smallest testable unit: company finding and Review for one
supplied micro-market. Program updated on 2026-10-07 to the Kozmo Invoice Alpha Genesis Cohort
(see Clarifications).

## Clarifications

### Session 2026-10-05

- Q: Which sources may real company information come from? → A: Public web (company websites,
  press, job postings, public directories) plus official company registries. No licensed
  company-data providers. (FR-002)
- Q: What is the minimum proof that a company is real and in scope? → A: Existence, an office in a
  target location, and IT professional-services type must be sourced. Size needs at least one sourced
  signal under the limit and no source above it. Time-and-materials needs a sourced indicator.
  Revenue may remain unknown. (FR-016) *Superseded on 2026-10-07: company type and
  time-and-materials removed, headquarters location and interest signal added.*
- Q: What caps should the MVP use? → A: Up to 10 companies per micro-market (FR-004). The caps of 5
  candidates generated and 2 selected apply to the later candidate-selection feature.
- Q: Is the original scope the smallest testable unit? → A: No. This feature covers company finding
  and Review for one supplied micro-market only. Turning the objective into candidate micro-markets,
  selecting them, and building the campaign handoff move to later features (see Assumptions).
- Q: How is hallucination of companies and sources prevented? → A: Companies come only from sources
  actually retrieved during the run. Every citation is checked to exist and to contain the claim.
  The company's identifier must resolve. (FR-006 to FR-008)

### Session 2026-10-06

- Q: Who performs Review, i.e. who sets include / exclude / needs verification on each company
  record? → A: The system's manager layer (the Market Manager), applying the written rules plus
  bounded reasoning steps and recording its reasons. A HipStraw team member spot-checks the results
  afterwards. (FR-012)
- Q: How strictly must a retrieved source match the excerpt recorded for a citation before the
  citation passes its check? → A: Exact text match: the excerpt must appear word for word in the
  retrieved source, ignoring only spacing, line breaks, and letter case. (FR-007)
- Q: Must automated retrieval respect each site's robots rules and terms of use, excluding sites
  that forbid automated access? → A: Yes. Sites that forbid automated access (for example, LinkedIn)
  are not used as sources. (FR-002)
- Q: What result from one run should count as proving the core hypothesis? → A: At least 3
  companies included, and at least 80% of the included companies confirmed by a HipStraw team member
  to meet the Genesis constraints. (SC-003)

### Session 2026-10-07

- Q: Which program and objective does this feature serve? → A: The Kozmo Invoice Alpha Genesis
  Cohort (source: https://kozmo.ai/invoice-alpha-genesis.html), replacing the earlier IT
  professional-services intake. Objective: find companies whose procurement, AP, finance, and
  commercial teams would benefit from continuous obligation intelligence: catching invoice
  divergence before payment, protecting entitlements, and preventing leakage. (FR-001)
- Q: Which companies are in scope? → A: Startups, small businesses, and mid-market companies only.
  Fortune 500 companies and other large enterprises are excluded. The size threshold is configurable,
  with a default of fewer than 500 employees and less than $100M revenue. Headquarters must be in the
  Atlanta, San Francisco, or New York metro area (US only), each drawn as the wider official region,
  so the San Francisco area includes Silicon Valley. (FR-001, FR-016)
- Q: Where do micro-markets come from? → A: From the program's six experiment contexts: SaaS /
  recurring fees, professional services, managed services, consulting + services, mixed obligations,
  and strategic suppliers. (FR-001; later feature 003)
- Q: What else must each company record show? → A: An interest signal: sourced evidence of the pain
  (for example, heavy recurring SaaS or services spend, or AP or procurement hiring) or of exploring
  AI, automation, or agents for invoice, spend, or obligation management, with its kind recorded.
  Inclusion requires at least one; otherwise the disposition is needs verification. (FR-020, FR-016)
- Q: What context do fit reasons draw on? → A: The program's six primary interests: continuous
  obligation intelligence, invoice accuracy / entitlement, scope drift / prevention, payment timing /
  working capital, supplier commercial position, and agent governance / autonomy. (FR-005)
- Q: What does this iteration deliver? → A: One micro-market (the first position) and about 10
  companies (the cap stays at 10), a readable demo report, the stored records, and a baseline
  snapshot of the first position. (FR-004, FR-017, FR-021)
- Q: What stays out of scope? → A: Individual people, contacts, emails, enrichment services (for
  example, Crunchbase), the Campaign Manager, Jev, and a user interface. (FR-018, FR-019)
- Q: What does the existence check require? → A: The company's own website must load, and a
  citation from its homepage must contain the company name. A company known only from a registry
  entry, with no website, is dispositioned needs verification. (FR-008, FR-016) *Extended later on
  2026-10-07: an about or contact page already fetched in the run may also supply the citation.*
- Q: May stored excerpts mention individual people? → A: Yes, incidentally, inside verbatim excerpts
  only. There are no person fields or person entities, and no email addresses or phone numbers.
  (FR-018)
- Q: Is "heavy recurring spend" a criterion for a pain signal? → A: No, it is an example only. Every
  interest signal, of either kind, must cite a source. (FR-020)
- Q: How are registry-only companies recorded and checked? → A: Their fit, interest signals, and
  falsifier are explicit unknowns, with an empty falsifier. The spot-check confirms that their
  registry page opens and that none is included. If the same company is also found through its
  website, the registry-only record is dropped. (FR-005, SC-001)
- Q: Should typographic differences fail the exact excerpt match? → A: No. Before comparing, curly
  quotes become straight quotes, en and em dashes become hyphens, and non-breaking spaces become
  normal spaces, on both the excerpt and the page text. This extends the 2026-10-06 answer, which
  ignored only spacing, line breaks, and letter case. Paraphrases still fail. (FR-007)
- Q: Must the judgement model cite evidence for an include? → A: No. The system attaches the IDs of
  the record's passing evidence documents to every decision itself. An include needs at least one
  passing evidence document; without one, the disposition becomes needs verification. (FR-012)

### Session 2026-10-07 (after the first live run, `run_20261007T140925`)

The first live run on Invoice Alpha returned 10 companies and included none. All 10 came from one
alphabetical directory page, kept in page order (5Miles to Addison Health Systems), and most were
headquartered around Dallas. Four websites were excluded only because they blocked automated reading.

- Q: How should discovery choose which candidates to keep? → A: Rank every candidate by how well it
  matches the first position (segment, company archetype, and headquarters metro) before applying
  the cap of 10. Never keep listing entries in the order the page shows them. Searches target
  companies in the three metros; generic or alphabetical (A–Z) directories come after them.
  (FR-022)
- Q: What does a website that blocks automated reading mean for the existence check? → A: robots.txt
  is still respected, and a disallowed page is never fetched. A site blocked by robots.txt, or
  answering HTTP 401, 403, or 429, exists but cannot be read: the company is dispositioned needs
  verification, with the reason recorded. Only HTTP 404 or 410, or a domain that does not resolve
  (DNS failure), fails the existence check and excludes the company. Any other failure (a server
  error, a timeout, a redirect to another domain) is also needs verification, because it does not
  show that the website is gone. (FR-008, FR-013)
- Q: Is a cited headquarters in a metro's state but outside the metro area unknown, or a failure?
  → A: A failure. A passing headquarters citation that places the company outside all three metro
  areas excludes it: Buffalo, NY (in New York State, outside the New York CSA) is treated the same
  as Dallas, TX. The location is unknown only when there is no passing headquarters citation, or
  when the cited value names no city and only a state with some part in one of the three CSAs (CA,
  GA, AL, NY, NJ, CT, PA; so "California" or "New York" alone is unknown). A state with no part in
  any of them ("Texas") excludes. Citations that disagree, one
  inside and one outside, are a conflict: needs verification, with both values in the reason. This
  replaces research R5's rule that an unlisted city only makes the location unknown, so each metro's
  place list must name every place in its CSA. (FR-016)
- Q: What if the website's domain does not match the company name (for example Addison Health
  Systems → writepad.com)? → A: The existence citation must show the company name on that website's
  homepage; otherwise the company is needs verification, and the reason names both the website and
  the company. (FR-016)

Added at the review of the Phase 4 tests (same day):

- Q: Is "Addison, TX" in a headquarters claim the same as "Addison, Texas" in its excerpt? → A: Yes.
  When checking that a headquarters claim's value appears in its excerpt, a US state's two-letter
  code and its full name are equal (TX = Texas, NY = New York). Nothing else about the exact match
  changes. (FR-007)
- Q: Can one directory use up the page budget? → A: No. Listing pages are also capped per site and
  per query, so the other queries' results are still read. (FR-022)
- Q: Must the existence citation come from the homepage? → A: The homepage first. If the homepage
  does not name the company, an about or contact page of the same website that the run already
  fetched may supply it. No page is fetched only for this. (FR-016)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find real, evidenced companies for one micro-market (Priority: P1)

As the Market Manager, given one micro-market (the first position, drawn from one of the program's
experiment contexts) and the cohort constraints, I want a bounded list of real companies whose
procurement, AP, finance, or commercial teams would benefit from continuous obligation intelligence,
where every company comes from a retrieved source and every claim about it is backed by a checked
citation, so that I have trustworthy material to review instead of a plausible-looking list.

**Why this priority**: This is the core hypothesis: from the Invoice Alpha objective, HipStraw can
identify the real companies in a micro-market. It is also where fabricated companies and false
citations would enter, so it carries the anti-hallucination rules.

**Independent Test**: A HipStraw team member writes one micro-market by hand and runs company
finding. Then they open each returned company's identifier and each cited source and confirm that
the company exists and that each source contains the quoted excerpt.

**Acceptance Scenarios**:

1. **Given** one micro-market and the cohort constraints, **When** company finding runs, **Then** it
   returns at most 10 company records, each containing: company name, a verifiable identifier, why
   it fits (buyer, problem, trigger, and the primary interests it relates to), its interest signals,
   a citation for each claim, a confidence level, explicit unknowns, and a falsifier.
2. **Given** any returned company, **When** its origin is checked, **Then** it traces to a source
   that was retrieved during the run, not to general knowledge.
3. **Given** a claim whose cited source cannot be retrieved, or does not contain the cited excerpt,
   **When** the record is produced, **Then** that claim is recorded as an explicit unknown, not as
   a fact.
4. **Given** a company whose own website does not exist (HTTP 404 or 410, or its domain does not
   resolve), **When** the record is produced, **Then** the record is marked as failing the existence
   check. A website that exists but cannot be read (blocked by robots.txt, or HTTP 401, 403, or 429)
   is marked unreadable, with its reason, instead.
5. **Given** two sources that disagree about a company fact (for example, two employee counts),
   **When** the record is produced, **Then** both values are kept with their own citations, and
   neither is averaged or dropped.
6. **Given** a micro-market where fewer than 10 real companies are found, **When** finding
   completes, **Then** only those companies are returned and the shortfall is recorded, with no
   padding.
7. **Given** the output of company finding, **When** it is inspected, **Then** every record is
   marked as a finding awaiting Review, and none is marked as included.
8. **Given** a company for which no interest signal can be found, **When** the record is produced,
   **Then** the interest signal is shown as an explicit unknown.
9. **Given** a listing page that names more companies than the cap, in alphabetical order, **When**
   finding applies the cap, **Then** the companies kept are those that best match the first position
   (metro, segment, archetype), not the first ones on the page.

---

### User Story 2 - Market Manager reviews every company record (Priority: P2)

As the Market Manager, I want to give every company record a disposition (include, exclude, or
needs verification) with a reason, so that only companies that pass Review count as included, and
findings never become canonical on their own.

**Why this priority**: Under the Faculty Systems principle, Review is the interface to reality.
Without it, Story 1's output is only input.

**Independent Test**: Supply a fixed set of company records: some fully proven, one with a failed
citation check, one with conflicting size evidence, one Fortune 500 company, one with no interest
signal, and one whose falsifier is met. Run Review and check that every record gets exactly one
disposition with a reason, and that only the fully proven records are included.

**Acceptance Scenarios**:

1. **Given** a set of company records, **When** Review completes, **Then** every record has exactly
   one disposition and a non-empty reason.
2. **Given** a record that fails the existence check, or that relies on a citation that failed its
   check, **When** it is reviewed, **Then** it is not included.
3. **Given** a record that does not meet the minimum proof (FR-016), **When** it is reviewed,
   **Then** it is dispositioned needs verification or exclude.
4. **Given** a record that meets every other part of the minimum proof but has no sourced interest
   signal, **When** it is reviewed, **Then** it is dispositioned needs verification.
5. **Given** a Fortune 500 company or other large enterprise, **When** it is reviewed, **Then** it
   is not included.
6. **Given** a record whose falsifier is shown to be true by its evidence, **When** it is reviewed,
   **Then** it is not included.
7. **Given** a record that finding marked as a strong fit, **When** no Review disposition exists,
   **Then** it does not appear as included.
8. **Given** a company known only from a registry entry, with no website, **When** it is reviewed,
   **Then** it is dispositioned needs verification.
9. **Given** a company whose website exists but cannot be read, **When** it is reviewed, **Then** it
   is dispositioned needs verification, and the reason says why the website could not be read.
10. **Given** a passing headquarters citation outside all three metro areas, **When** the record is
    reviewed, **Then** it is excluded, even when the city is in one of the metros' states.

---

### User Story 3 - Demo report, stored records, and baseline snapshot (Priority: P3)

As a HipStraw team member, I want a readable demo report of the run, with every record stored and a
baseline snapshot of the first position, so that I can show and assess the result, and later
iterations have a fixed starting point to compare against.

**Why this priority**: It packages Stories 1 and 2 for people and for future iterations. It adds no
new finding or Review logic.

**Independent Test**: From a fixed set of reviewed records, produce the report and the snapshot.
Check the report's contents, retrieve the stored records after the run, and confirm the snapshot is
unchanged after a second run.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the demo report is opened, **Then** it shows the micro-market
   and its experiment context, the constraints in force, every company with its disposition and
   reason, and for each included company its fit, primary interests, interest signals, and
   citations.
2. **Given** a completed run, **When** its records are requested later, **Then** every company
   record, citation (with its check result), and Review disposition can be retrieved.
3. **Given** a completed run, **When** its outputs are inspected, **Then** a baseline snapshot of the
   first position exists, holding its date, the micro-market, the constraints in force, and each
   company's identifier and disposition.
4. **Given** a stored baseline snapshot, **When** a later run happens, **Then** the baseline is
   unchanged.
5. **Given** the demo report and stored records, **When** they are inspected, **Then** they contain
   no person fields or person entities, no email addresses, and no phone numbers. Person names appear
   only incidentally, inside verbatim excerpts.

---

### Edge Cases

- **Same company found twice** (for example, under a trading name and a legal name): records with
  the same identifier are one company and appear once.
- **Size conflict across a threshold** (for example, 450 employees in one source and 620 in another):
  both values are kept. Because one source shows the company over the threshold, it cannot be
  included (FR-016).
- **Revenue not public** (common for private companies): revenue is an explicit unknown. The company
  can still be included if a sourced employee count under the threshold meets the size rule.
- **Office in a target metro, headquarters elsewhere**: does not qualify. Headquarters must be in a
  target metro area (FR-016).
- **Headquarters in Silicon Valley** (for example, Palo Alto or San Jose): qualifies, because the
  San Francisco area is drawn as the wider region (FR-001).
- **Subsidiary of a Fortune 500 company or other large enterprise**: treated as a large enterprise
  and not included.
- **Company known only from a registry entry, with no website**: it is not included. It is
  dispositioned needs verification (FR-008).
- **Source exists but does not say what is claimed**: the claim becomes an explicit unknown (FR-007).
- **Source says it in different words, or only in an image or table the text check cannot read**: the
  exact-match check fails, so the claim becomes an explicit unknown (FR-007).
- **No companies found**: the run returns an empty list with the reason recorded, not invented
  results.
- **Website blocked by robots.txt, or answering HTTP 401, 403, or 429**: the company exists but its
  website cannot be read. It is dispositioned needs verification with the reason (FR-008).
- **Headquarters in a metro's state but outside the metro area** (for example Buffalo, NY): excluded,
  like any headquarters outside the metros (FR-016).
- **Website domain unlike the company name** (for example a product's domain): the homepage must name
  the company; otherwise needs verification (FR-016).
- **Alphabetical directory**: its first entries are not kept because they come first. Candidates are
  ranked by their match to the first position (FR-022).

## Requirements *(mandatory)*

### Functional Requirements

**Input and bounds**

- **FR-001**: System MUST accept one micro-market (the first position) and the constraints of the
  Kozmo Invoice Alpha Genesis Cohort as input. The micro-market MUST be drawn from one of the
  program's experiment contexts (SaaS / recurring fees, professional services, managed services,
  consulting + services, mixed obligations, strategic suppliers) and MUST state its segment, company
  archetype, buyer, problem, and trigger. The cohort constraints are:
  - **Size**: startups, small businesses, and mid-market companies only. Fortune 500 companies and
    other large enterprises are excluded. The size threshold MUST be configurable, with a default of
    fewer than 500 employees and less than $100M annual revenue. The threshold in force MUST be
    recorded with each run.
  - **Location**: headquarters in the Atlanta, San Francisco, or New York metro area (US only). Each
    metro area is the official US combined statistical area, so the San Francisco area includes
    Silicon Valley.
- **FR-002**: System MUST use only these source types: public web (company websites, press releases
  and news, job postings, public business directories) and official company registries (for example,
  US state business filings). Licensed company-data providers and enrichment services (for example,
  Crunchbase) MUST NOT be used. Automated retrieval MUST respect each site's robots rules and terms of
  use. A site that forbids automated access (for example, LinkedIn) MUST NOT be used as a source.
- **FR-003**: Company finding MUST stay within the supplied micro-market and constraints, and MUST
  NOT scan broadly beyond them.
- **FR-004**: Company finding MUST return at most 10 companies. If fewer are found, it MUST record
  the shortfall and MUST NOT pad the list.
- **FR-022**: Company finding MUST rank candidates by their match to the first position (segment,
  company archetype, and headquarters metro, as stated on the retrieved page) before applying the
  cap in FR-004, and MUST NOT keep candidates in the order a page lists them. Searches MUST target
  companies in the metro areas in force, spread across all of them; generic or alphabetical
  directories come after metro-targeted results, and no single site or query may use more than
  its configured share of the listing pages. A location used for ranking MUST appear on the
  retrieved page. Ranking never decides a disposition.

**Company records**

- **FR-005**: Each company record MUST contain: company name; a verifiable identifier (for example,
  its website); why it fits, covering buyer, problem, and trigger, and naming which of the program's
  primary interests it relates to (continuous obligation intelligence; invoice accuracy /
  entitlement; scope drift / prevention; payment timing / working capital; supplier commercial
  position; agent governance / autonomy); its interest signals (FR-020); a citation for each claim;
  a confidence level; explicit unknowns; and a falsifier (what evidence would show it does not fit).
  Each company MUST appear only once. For a company known only from a registry entry, the fit,
  interest signals, and falsifier MUST be recorded as explicit unknowns, and the falsifier is left
  empty.
- **FR-020**: Each company record MUST list its interest signals, each backed by a passing citation
  and labeled with its kind:
  - **Pain signal**: evidence of the pain. Heavy recurring SaaS or services spend, and AP or
    procurement hiring, are examples only, not criteria.
  - **Exploration signal**: evidence of exploring AI, automation, or agents for invoice, spend, or
    obligation management.

  No interest signal of either kind may be recorded without a passing citation. If no interest
  signal is found, the record MUST show the interest signal as an explicit unknown.

**Anti-hallucination**

- **FR-006**: Every company MUST originate from a source retrieved during the run. A company MUST NOT
  be proposed from general knowledge, memory, or reasoning about what companies typically exist.
  Reasoning steps may only summarize or classify what retrieved sources say.
- **FR-007**: Every citation MUST record the source's location, its date, its reliability, and the
  excerpt that supports the claim. Each citation MUST be checked during the run to confirm that the
  source can be retrieved and contains that excerpt word for word. Only differences in spacing, line
  breaks, letter case, quote style (curly or straight), dash style (en or em dash or hyphen), and
  non-breaking spaces are ignored. Paraphrase or meaning-based matches MUST NOT pass. For a
  headquarters claim, a US state's two-letter code and its full name are equal when checking that
  the claimed value appears in the excerpt. A claim whose citation fails the check MUST be recorded
  as an explicit unknown.
- **FR-008**: Each company's own website MUST be checked during the run to confirm that it loads,
  without fetching anything its robots rules disallow. A website that does not exist (HTTP 404 or
  410, or a domain that does not resolve) MUST be marked as failing the existence check. A website
  that exists but cannot be read (blocked by robots.txt, HTTP 401, 403, or 429, or any other
  failure) MUST be marked unreadable, with the reason recorded; the company is dispositioned needs
  verification. A company known only from an official registry entry, with no website, MUST be
  dispositioned needs verification.

**Evidence handling**

- **FR-009**: A claim without a passing citation MUST be recorded as an explicit unknown and MUST
  NOT be stated as fact.
- **FR-010**: When sources conflict, the system MUST keep every value with its citation and MUST NOT
  average, merge, or silently choose between them.
- **FR-011**: Company finding output MUST be marked as findings awaiting Review. Only Review may
  mark a company as included.

**Review**

- **FR-012**: The Market Manager (the system's manager layer, not a person) MUST give every company
  record exactly one disposition (include, exclude, or needs verification) with a non-empty reason,
  and MUST record who reviewed it and when. Review MUST apply the written rules in FR-013 to FR-016.
  Any judgement step MUST be a bounded reasoning step with explicit inputs and a structured output,
  and MUST rely only on the record's passing citations. Every include decision MUST carry the IDs of
  at least one passing evidence document, attached by the system; otherwise it becomes needs
  verification.
- **FR-013**: A company that fails the existence check MUST NOT be included. A company whose website
  does not exist MUST be excluded; one whose website cannot be read MUST be dispositioned needs
  verification.
- **FR-014**: A company whose falsifier is shown to be true MUST NOT be included.
- **FR-015**: Review MUST address any conflicting evidence on a constraint in its reason.
- **FR-016**: A company MUST NOT be included unless all of the following minimum proof is met, each
  backed by a passing citation:
  - **Existence**: the company's own website loads (FR-008), and a citation from its homepage (or,
    when the homepage does not name the company, from an about or contact page of that website
    already fetched in the run) has an excerpt containing the company name. When the website's
    domain does not match the company name, this citation is what links the two; without it, the
    company is needs verification.
  - **Location**: headquarters in one of the three metro areas (FR-001). A passing headquarters
    citation outside all three excludes the company. The location is unknown only when there is no
    passing headquarters citation, or the cited value names no city inside a metro's state;
    disagreeing citations are a conflict.
  - **Size**: at least one signal (employee count or revenue) under the configured threshold, no
    source showing the company over either threshold, and not a Fortune 500 company or other large
    enterprise. Revenue may remain an explicit unknown.
  - **Interest signal**: at least one (FR-020).

  A company that meets every other item but has no interest signal MUST be dispositioned needs
  verification. A company that fails any other item MUST be dispositioned needs verification or
  exclude.

**Output and scope**

- **FR-017**: Each run MUST produce a demo report that a HipStraw team member can read without
  operating the system. It MUST show the micro-market and its experiment context, the constraints in
  force, every company with its disposition and reason, the shortfall if any, and for each included
  company its fit, primary interests, interest signals, and citations. Each run MUST also store every
  company record, citation (with its check result), and Review disposition so they can be retrieved
  after the run, with every included company traceable from micro-market to citations to Review
  disposition.
- **FR-021**: Each run MUST store a baseline snapshot of the first position: its date, the
  micro-market definition, the constraints in force, and each company's identifier and disposition.
  The baseline MUST NOT be changed after it is stored.
- **FR-018**: The demo report and stored records MUST NOT have person fields or person entities, and
  MUST NOT contain email addresses or phone numbers. Person names are allowed only incidentally,
  inside verbatim excerpts.
- **FR-019**: This feature MUST NOT include: turning the objective into candidate micro-markets or
  selecting them; the campaign handoff package; the Campaign Manager or any outreach; enrichment
  services; updating or comparing positions over time beyond storing the baseline; Jev; a user
  interface; or any agent SDK or agent framework.

### Key Entities *(include if feature involves data)*

- **Micro-Market (input)**: The first position: segment, company archetype, buyer, problem, and
  trigger, drawn from one of the program's experiment contexts. In this feature it is supplied by
  hand.
- **Cohort Constraints**: The size threshold in force (configurable) and the three headquarters
  metro areas, recorded with each run.
- **Company**: A real organization. A company with a website is identified by that website, which is
  checked to load and to show the company name. A registry-only company is identified by its registry
  entry, and it is never included.
- **Company Record**: The finding for one company: fit claims with their primary interests, interest
  signals, confidence, unknowns, falsifier, and check results. It is input to Review until a
  disposition is recorded.
- **Interest Signal**: Sourced evidence that a company has the pain or is exploring AI, automation,
  or agents for invoice, spend, or obligation management, labeled as a pain signal or an exploration
  signal.
- **Citation**: The source behind a claim: location, date, reliability, the supporting excerpt, and
  whether it passed its check. Conflicting citations are all kept.
- **Unknown**: A recorded gap where evidence is missing or a citation failed its check.
- **Review Disposition**: Include, exclude, or needs verification, with a reason, a reviewer, and a
  date.
- **Demo Report**: The readable summary of one run for HipStraw team members.
- **Baseline Snapshot**: A dated, unchangeable record of the first position and its Review outcome,
  which later iterations compare against.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero fabricated companies: in an independent spot-check, every returned company with a
  website loads and shows its name; every registry-only company's registry page opens; and no
  registry-only company is included.
- **SC-002**: Zero false citations: in an independent spot-check, 100% of citations marked as
  passing can be retrieved and contain their recorded excerpt.
- **SC-003**: The core hypothesis is supported when a run includes at least 3 companies and a
  HipStraw team member confirms that at least 80% of the included companies meet the cohort
  constraints and have a genuine interest signal.
- **SC-004**: 100% of claims on included companies have a passing citation; every other claim
  appears as an explicit unknown.
- **SC-005**: 100% of runs return at most 10 companies, and 100% of returned records have a
  disposition and a reason.
- **SC-006**: 100% of runs produce a demo report and a baseline snapshot, and the stored records can
  be retrieved after the run.

## Assumptions

- **Market Manager**: The Market Manager is the manager layer of the HipStraw Faculty System, not a
  person (confirmed in Clarifications). It owns Review. HipStraw team members read the demo report
  and run the spot-checks.
- **Program**: The objective, experiment contexts, and primary interests come from the Kozmo Invoice
  Alpha Genesis Cohort (https://kozmo.ai/invoice-alpha-genesis.html). This spec does not define
  Kozmo's product beyond that objective.
- **First position**: For this feature, a HipStraw team member writes the first position by hand,
  choosing one of the six experiment contexts. A later feature will produce positions from the
  program objective.
- **Subsidiaries**: A subsidiary of a Fortune 500 company or other large enterprise counts as a large
  enterprise.
- **Evidence scales**: Source reliability uses a simple scale (high, medium, low). Confidence uses the
  same convention as feature 001 (a 0 to 1 value with High, Medium, and Low bands). Exact thresholds
  are set during planning.
- **Later features** (not part of this spec):
  - **Feature 003, objective to selected micro-markets**: candidate micro-markets seeded from the
    program's six experiment contexts, using the seed graph capability from feature 001 (in the
    HipStraw Market Discovery Agent project), and selection with reasons. Caps: 5 candidates
    generated, 2 selected.
  - **Feature 004, campaign handoff package**: open questions carried forward: the exact fields the
    campaign side needs, and whether needs-verification companies appear in the handoff.
