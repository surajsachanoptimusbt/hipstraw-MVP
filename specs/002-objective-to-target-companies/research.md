# Research: Find and Review Target Companies for a Micro-Market

**Feature**: 002-objective-to-target-companies | **Date**: 2026-10-07

Each decision resolves an unknown from the plan's Technical Context or a constraint from the planning
input. Facts about the team's existing setup come from the sibling projects under `D:\OptimusBT`
(the V0 market discovery agent and `hipstraw-faculty`). Only key names were read from their
environment files, never values.

## R1. Model provider and client

- **Decision**: OpenAI, through the official `openai` Python SDK, using Structured Outputs
  (`chat.completions.parse` with Pydantic models, strict JSON schema). The model name comes from the
  `LLM_MODEL` environment variable, as in V0. No tool calling, no multi-turn loops: each call is one
  request with explicit inputs and one schema-validated JSON response.
- **Rationale**: This is the team's existing provider. V0 has `OPENAI_API_KEY` and `LLM_MODEL` in its
  `.env.example`, and its `app/tools/llm.py` already calls `chat.completions.create` with
  `response_format`. A single bounded call with a strict schema satisfies Constitution VII.
- **Alternatives considered**:
  - OpenAI Agents SDK: banned by Constitution VII. V0's `app/agents/` imports it (`from agents
    import ...`), so that module must not be ported. Only V0's plain client pattern is reused.
  - LangChain agents, CrewAI, Claude Agent SDK: banned by Constitution VII.
  - Another provider: no evidence the team has keys for one.

## R2. Company discovery search

- **Decision**: Brave Search API (`https://api.search.brave.com/res/v1/web/search`), called by this
  system's own orchestration with queries it controls. The key is `BRAVE_API_KEY`. The search
  adapter is an interface, so Tavily or SerpAPI (V0's other options) can be swapped in later.
- **Rationale**: V0 has a `BRAVE_API_KEY` entry and a `BraveSearch` class in `app/tools/search.py`.
  When the system issues the queries and receives the result URLs, it can prove where every company
  came from (FR-006), cap the effort (FR-003), and record responses for hermetic tests.
- **Alternatives considered**:
  - The model provider's built-in web search: rejected. The model would choose the queries and how
    many searches to run, which moves retrieval control out of the system's orchestration (tension
    with Constitution VII). It also lets a company named from the model's memory appear next to real
    results, which weakens FR-006, and it is harder to cap and record.
  - DuckDuckGo HTML results (V0's free default): rejected, because scraping result pages conflicts
    with the robots and terms rule in FR-002.
- **To confirm**: Only V0's example file was seen. A team member should confirm the Brave key is
  active, and that its plan permits storing result URLs and titles.

## R3. Fetching, robots rules, and terms of use

- **Decision**: Use `httpx` (synchronous) with an identifying User-Agent and a 15-second timeout.
  Accept only `text/html` responses up to 2 MB. Allow at least 1 second between requests to the
  same host. Check `robots.txt` per host with `urllib.robotparser`, cached per run. Never fetch a
  domain on the denylist in `config/source_policy.yaml`, which lists sites whose terms forbid
  automated access (linkedin.com, glassdoor.com, indeed.com, zoominfo.com, crunchbase.com, and
  others). Convert HTML to visible text with BeautifulSoup's built-in `html.parser`.
- **DNS failures (2026-10-07)**: when a request (including the `robots.txt` request) cannot connect,
  the fetcher checks whether the host name resolves. If it does not, the failure is `dns_error`, not
  `network_error` or `robots_disallowed`, because only a missing domain shows that a website is gone
  (R4).
- **Rationale**: FR-002 requires respecting robots rules and terms. Robots rules can be checked
  automatically; terms cannot, so a reviewed denylist is the practical control. `html.parser`
  avoids compiled dependencies on Windows.
- **Alternatives considered**: A headless browser (heavy, and not needed for text evidence). PDF
  parsing (deferred; PDFs are skipped and their claims become unknowns).

## R4. Citation check (exact excerpt match)

- **Decision**: A citation passes only if both checks hold:
  1. The excerpt appears in the retrieved page text after normalizing both sides: curly quotes
     mapped to straight quotes, en and em dashes mapped to hyphens, non-breaking spaces mapped to
     normal spaces, then `casefold()` and collapsing every run of whitespace to a single space.
     Nothing else is normalized.
  2. For structured claims (headquarters city, employee count, revenue, parent company), the claimed
     value appears inside the excerpt. For a headquarters claim, a US state's two-letter code and
     its full name are equal ("Addison, TX" passes against "...Addison, Texas."; added 2026-10-07).
     The same normalization as step 1 applies; nothing else is relaxed.

  Each evidence record stores the URL, the fetch time, and a SHA-256 hash of the page text the check
  ran against. The model is told to copy excerpts verbatim from the text it was given (at most 300
  characters).
- **Rationale**: This implements the 2026-10-06 clarification (spacing, line breaks, and letter case
  are ignored), extended on 2026-10-07 to ignore quote style, dash style, and non-breaking spaces. The second check stops a correct excerpt being attached to a wrong value.
- **Identifier check and existence (FR-008, FR-016)**, revised after the first live run
  (2026-10-07):
  - **resolves**: the company's own website loads (2xx), with redirects only within the same company
    key or its subdomains.
  - **fails** (the website does not exist): HTTP 404 or 410, or `dns_error`. Review excludes.
  - **unreadable** (the website exists but cannot be read): `robots_disallowed`, HTTP 401, 403, or
    429, and every other failure (other HTTP errors, timeouts and connection errors, a redirect to
    another company key, a non-HTML or oversized page). robots.txt is still respected: a disallowed
    page is never fetched. Review dispositions needs verification and records why.
  - Existence also needs a citation whose excerpt contains the company name, from the homepage or,
    if the homepage does not name the company, from an about or contact page of the same website
    that the run already fetched (no extra fetch; 2026-10-07). It is built without a model
    (data-model.md). This catches a company from a list page being matched to the wrong website.
  - **Name–domain mismatch**: when no label of the website's host matches the company name (for
    example Addison Health Systems → writepad.com), that homepage citation is the only link between
    the two. The record stores `nameMatchesDomain: false`, and if the citation fails, the
    needs-verification reason names both the website and the company.
  - A registry-only company, with no website, is dispositioned needs verification.
- **Live-run evidence**: in `run_20261007T140925`, 5Miles, Aavenir, and Acctivate (robots.txt) and
  ActivTrak (HTTP 403) were excluded as if they did not exist. Under this rule they are needs
  verification.
- **Alternatives considered**: Fuzzy or meaning-based matching was rejected in Clarifications.

## R5. Headquarters location matching

- **Decision** (revised 2026-10-07 after the first live run): `config/metros.yaml` defines each
  metro area as its US Census combined statistical area (CSA): name, CSA code, states, and, per
  state, the CSA's counties and **every** Census place (incorporated places and census-designated
  places) in those counties. The model extracts the headquarters as `"City, ST"` with an excerpt; a
  full state name ("Austin, Texas") is read as its two-letter code. The system then decides, per
  passing citation:
  - **met**: the city is on a configured metro's place list for that state;
  - **not met**: any other city and state, including a city in a metro's state that is not on its
    list (Buffalo, NY);
  - **unknown**: the value names no city and no state outside the metros (for example
    "California" or "Bay Area"); a state alone outside every metro ("Texas") is not met.

  Across citations: all met → met; any not met and none met → not met; met and not met together →
  **conflict** (needs verification, both values in the reason); no passing citation → unknown.
- **Rationale**: The 2026-10-07 clarification: a cited headquarters outside all three CSAs excludes,
  the same as Dallas; unknown is kept for a missing or placeless citation. In the live run, ACV
  Auctions (cited "Buffalo, NY") was needs verification under the old rule.
- **Consequence**: An unlisted city now excludes, so a gap in a place list would wrongly exclude an
  in-metro company. The place lists must therefore be complete and keyed by state (a place name can
  exist in two states of the same CSA). They are generated from the Census CSA delineation file and
  the place-to-county relationship file by a one-off script, and committed (T052). Each list
  holds every incorporated place, census-designated place, and county subdivision (town or
  township, as in "Edison, NJ" or "Greenwich, CT") in the CSA's counties, with suffixes such as
  "city", "borough", or "township" removed.
- **Superseded**: until 2026-10-07, an unlisted city in a metro's state was unknown, never not met.
- **Alternatives considered**: Geocoding APIs (an extra dependency and key) and model judgement of
  "is this in the metro" (not verifiable).

## R6. Size, Fortune 500, and subsidiaries

- **Decision**:
  - Thresholds come from config (`max_employees: 500`, `max_revenue_usd: 100000000`, both strict
    "less than").
  - A range such as "51–200 employees" uses its upper bound for the "under" test and its lower bound
    for the "over" test.
  - A company is over the limit if any passing citation's lower bound reaches either threshold.
  - The Fortune 500 list is not scraped (its publisher's terms). Instead, a company with a passing
    size signal under the thresholds cannot itself be a Fortune 500 company, so the remaining risk is
    subsidiaries. The model extracts any "subsidiary of / part of" claim with an excerpt:
    - if the parent is on the optional `largeEnterpriseParents` list in config (compared by
      normalized name), or the parent's size is shown over the thresholds → **exclude**;
    - if the parent's size is unknown → **needs verification**.

    The parent's size comes from claims with `claimField` `parent_employees` or `parent_revenue`,
    cited like any other structured claim and judged against the same thresholds. In the live run,
    Active Network's own site said it was "acquired by Global Payments".
- **Rationale**: Uses only sources the rules allow, and keeps every number configurable.

## R7. Interest signals

- **Decision**: For each company whose website resolves, run at most `signalSearchesPerCompany` (3)
  bounded searches, in this order and with exactly these query strings (they are the replay match
  keys):
  1. `"<name>" accounts payable OR procurement job`
  2. `"<name>" invoice automation OR "AI agents" finance`
  3. `site:<domain> careers`

  From their results, in search order and then result order, fetch at most
  `thirdPartyPagesPerCompany` pages that are not on the company's own site, skipping denylisted and
  already-fetched URLs. Results on the company's own site count toward `ownSitePagesPerCompany`
  instead. These pages follow the own-site pages in the `CompanyEvidence` call. Companies whose
  website does not resolve, and registry-only companies, get no signal searches. Also fetch the
  company's own careers and press pages. Allowed signal sources are the company's own
  site, job-board pages that pass the robots and denylist checks (such as hosted applicant-tracking
  boards), and news or press pages. The model labels each signal with an excerpt:
  - **pain**: AP or procurement hiring, or statements of heavy recurring SaaS or services spend;
  - **exploration**: exploring AI, automation, or agents for invoice, spend, or obligation
    management.
- **Expectation**: AP and procurement hiring will be the most common sourced signal. Spend levels are
  rarely public, so many companies will end up needs verification. That is the intended,
  honest outcome.

## R8. Source reliability and confidence

- **Decision**: Both are computed deterministically; the model produces no numbers.
  - **Reliability by source type** (set in `config/source_policy.yaml`):
    - official registry: high
    - third-party news or press: medium
    - the company's own site: medium
    - job board: medium
    - directory or list article: low
  - **Confidence (0 to 1)**: the mean, over the four minimum-proof items (existence, location, size,
    interest signal), of the weight of the best-reliability passing citation for that item, using
    `reliabilityWeights` (high 1.0, medium 0.7, low 0.4). An item with no passing citation counts 0.
  - **Bands** (feature 001 convention): High ≥ 0.8, Medium 0.5–0.79, Low < 0.5.
- **Rationale**: Constitution VII and VIII. A number the model invents cannot be traced to evidence.

## R9. Review design (Market Manager)

- **Decision**: Review runs as its own step, in two stages.
  1. **Rule gate** (deterministic): applies FR-013 and FR-016 to each record:

     | Condition | Disposition |
     |-----------|-------------|
     | Website does not exist (`fails`: HTTP 404 or 410, or DNS failure) | exclude |
     | Website exists but cannot be read (`unreadable`: robots.txt, HTTP 401, 403, 429, or any other failure) | needs verification, with the reason |
     | Registry-only (no website) | needs verification |
     | Website loads, but the existence citation failed | needs verification (the reason names the website when its domain does not match the name) |
     | Headquarters "not met" (a cited place outside every metro) | exclude |
     | Headquarters "conflict" (cited inside and outside) | needs verification |
     | Headquarters "unknown" (no passing citation, or no city named) | needs verification |
     | Only over-threshold size evidence, or a large-enterprise parent | exclude |
     | A parent of unknown size | needs verification |
     | Conflicting size evidence across a threshold | needs verification |
     | No size signal | needs verification |
     | No interest signal | needs verification |

     The website rows changed on 2026-10-07 (before then, any failure to load excluded), as did the
     headquarters rows (an unlisted city was unknown).

  2. **Judgement** (one bounded model call), only for records that pass every rule. Its inputs are
     the micro-market and the record's passing citations only. Its output is `{falsifierMet,
     fitHolds, citedEvidenceIds, reason}`. The system checks that every cited ID exists and passed
     its check; if not, the disposition becomes needs verification. A met falsifier means exclude,
     and a fit that does not hold means needs verification.
  3. **Evidence on the decision**: the system attaches the IDs of the record's passing evidence
     documents to the decision. An include with none becomes needs verification (2026-10-07).

  The model can keep or downgrade a disposition, never upgrade one. Decisions are stored in
  `reviewDecisions`, which only the Review step writes. The reviewer is recorded as
  `market-manager/rules-v1+<model>`.
- **Rationale**: Covers FR-011 to FR-016 and Constitution VI: findings are input, and only Review
  decides.

## R10. State storage

- **Decision**: Use `google-cloud-firestore` against the local Firestore emulator.
  - Project ID: `demo-hipstraw-mvp`.
  - Emulator ports: 8085 for Firestore and 4005 for the UI. The faculty project uses 8080 and 4000,
    so both emulators can run side by side.
  - The CLI refuses to run unless `FIRESTORE_EMULATOR_HOST` is set and the project ID starts with
    `demo-`, following the faculty project's guard.
  - Baselines are written with `create()`, which fails if the document already exists, and the store
    exposes no update method for them.
  - Collection names follow the faculty project's camelCase style (`programs`, `marketCandidates`,
    `evidence`).
- **Rationale**: Planning input, plus the team's existing emulator setup (`hipstraw-faculty`). It also
  meets the Constitution's reproducibility preference.
- **Addition beyond the planning input**: a `runs` collection for per-run state (constraints in
  force, step status, counts). Without it, the separate steps would have nowhere to share run state.

## R11. Hermetic tests with recorded responses

- **Decision**:
  - The model, search, and fetch adapters (including `robots.txt` fetches) sit behind a record and
    replay layer. Each response is keyed by a SHA-256 of a stable match key, not the full request:
    - fetch: the URL;
    - search: the query;
    - model calls: the schema name plus a stable identifier (candidate ID, listing URL, company
      domain, or company record ID).

    Editing a prompt therefore does not invalidate the recordings. The full request is still saved
    beside each response for audit. Files live under `tests/fixtures/recorded/<scenario>/`.
  - Tests run in replay mode. A missing recording fails the test; it never falls through to the
    network.
  - `pytest-socket` blocks all network access in the default suite.
  - The default suite uses an in-memory store. The same store contract tests also run against the
    emulator when `--emulator` is passed, with sockets allowed only to localhost.
  - Synthetic fixtures use reserved `.test` domains and plainly fictional names, so recorded data can
    never be mistaken for real companies (Constitution IX).
  - **Real recordings for adapter contract tests (Constitution IV)**: a one-off script, run with real
    keys, records exactly:
    - one Brave query;
    - one page fetch and its `robots.txt`;
    - one OpenAI parse per schema (all five).

    The files go to `tests/fixtures/recorded/real/` and are committed. Adapter contract tests replay
    them to prove the adapters parse real response shapes. When a schema changes, its real recording
    is made again with real keys (T085). Record mode never writes secret values:
    the `Authorization` and `X-Subscription-Token` headers and any `api_key` value are replaced with
    `[redacted]` before writing, and the script fails if a key value appears in any file.
- **Rationale**: Planning input (hermetic, recorded responses) and Constitution IV (integration tests
  at service boundaries). Recording at the adapter level is independent of the provider's HTTP
  details.
- **Alternatives considered**: `vcrpy` cassettes, which are tied to HTTP-level details and are
  brittle across SDK versions.

## R12. Configuration

- **Decision**: YAML files validated with Pydantic:
  - `config/programs/invoice_alpha.yaml` (program)
  - `config/run.yaml` (thresholds, budgets, model)
  - `config/metros.yaml`
  - `config/source_policy.yaml`
  - the hand-written first-position file

  Secrets live only in environment variables (`OPENAI_API_KEY`, `BRAVE_API_KEY`).
- **Rationale**: The planning input asks for size and location filters as configuration values. YAML
  allows comments, and Python 3.10 has no built-in TOML reader.

## R13. Effort budgets (deferred from Clarifications)

- **Decision**: Defaults, all set in `config/run.yaml`:

  | Budget | Default |
  |--------|---------|
  | Discovery queries | 6 |
  | Results read per query | 10 |
  | Listing pages fetched (including direct-homepage results) | 12 |
  | Listing pages per site (company key), added 2026-10-07 | 3 |
  | Listing pages per query, added 2026-10-07 | 3 |
  | Profile hops per run | 10 |
  | Companies kept | 10 |
  | Own-site pages per company | 6 |
  | Signal searches per company | 3 |
  | Third-party pages per company | 4 |
  | Verify fetches per run (ceiling) | 110 |
  | Verify model calls per run (ceiling) | 20 |

  Discovery limits end discovery normally. Only running out of a verify ceiling while companies are
  still unverified is an error (exit code 4, contracts/cli.md).

  This gives about 45 model calls and 110 page fetches per run, with a target run time under 20
  minutes.
- **Rationale**: Turns "no broad scanning" (FR-003) into a measurable, testable limit.

## R14. Observability

- **Decision**: JSON-lines logs to stderr and to `.runs/<runId>/run.log`. Each event carries `runId`,
  `step`, and `companyRecordId` where relevant, plus counts for searches, fetches, model calls, and
  check failures.
- **Rationale**: Constitution V.

## R15. Program content

- **Decision**: `config/programs/invoice_alpha.yaml` holds the objective, the six experiment contexts,
  and the six primary interests as given in the 2026-10-07 clarifications, with `sourceUrl` set to
  the Kozmo page.
- **To confirm**: The page itself was not fetched during planning. Before a demo, a team member
  should check the YAML against the page (Constitution IX).

## R16. Candidate micro-markets and first position

- **Decision**:
  - The candidates step creates one candidate document for each of the program's six experiment
    contexts, by plain copying. There is no generation, no model call, and no seed graph; those
    belong to feature 003.
  - The first position is a hand-written YAML micro-market for one chosen candidate. It is stored on
    the run and frozen into the baseline after Review.
- **Rationale**: Keeps the requested slice (intake → candidates → first position → …) within spec
  FR-019 and Constitution X. See the conflict notes in plan.md.

## R17. Packaging and locking

- **Decision**: `pyproject.toml` (hatchling build) with a `hipstraw-mm` console script. Locked
  `requirements.lock` and `requirements-dev.lock` files are generated by `uv pip compile` and can be
  installed with plain `pip`. The code supports Python 3.10 and later. Linting and type checks use
  `ruff` and `mypy`.
- **Rationale**: The Constitution requires locked versions and prefers static typing. The faculty
  project uses pip, and the lock files keep that workflow.

## R18. Discovery link rules

- **Decision**: Every search result follows one of three paths, defined in contracts/llm-outputs.md:
  - **direct homepage**: a root-path URL on an unclassified domain, confirmed by a `HomepageIdentity`
    call;
  - **listing page**: any other result, read with `ListingExtraction`;
  - **skip**: denylisted, robots-disallowed, or over budget.

  On a listing page, only links to another company key count as the company's website. An internal
  link (a directory's own profile page) allows one budgeted hop to find the external website.
  Companies on official registry pages with no website are kept as registry-only records and
  dispositioned needs verification. Everything else without a website link is dropped.
- **Rationale**: Directory and list pages usually link to their own internal profile pages. Without
  these rules, real runs would find few companies, or would key them all to the directory's domain,
  which would put SC-003 (at least 3 included) at risk. A result that is itself a company homepage is
  the most direct origin there is.
- **Alternatives considered**:
  - Guessing a website from the company name: rejected (FR-006).
  - Unlimited hops: rejected (FR-003).
  - Deciding "is this a homepage" with heuristics only: rejected, because a root URL can also be a
    portal or a list site. The bounded `HomepageIdentity` call with an excerpt check decides instead.

## R19. Discovery targeting (added 2026-10-07, after the first live run)

- **Finding**: `run_20261007T140925` kept its first 10 candidates in page order. All 10 came from one
  alphabetical directory page (gregslist.com, reached by the first query), most were headquartered
  around Dallas, and none could be included. Twelve pages were read before the page budget ran out,
  while 40 results, most of them from the other metro queries, were never read.
- **Decision** (FR-022):
  1. **Queries target the metros.** The `QueryPlan` prompt asks for queries that each name one metro
     in force, spread across all of them, preferring local lists of companies (city startup lists,
     local business press, accelerator portfolios) over generic or A–Z directories. The system then
     orders the planned queries round-robin by metro, in the configured metro order. A query's metro
     is the first metro whose name or listed place appears in it as whole words. Queries that name no
     metro come last. Nothing is dropped for this reason.
  2. **Results are read round-robin.** All planned searches run first. Pages are then read in turns:
     the first result of every query, then the second of every query, and so on, skipping repeated
     URLs, until `listingPagesFetched` is reached. A result is skipped when its site (company key)
     already has `listingPagesPerSite` pages, or its query already has `listingPagesPerQuery`.
     Fetch attempts count, including robots-disallowed ones, so one directory or one query can no
     longer use up the page budget (added at the Phase 4 test review). Profile hops keep their own
     budget.
  3. **Candidates are ranked before the cap.** `ListingExtraction` and `HomepageIdentity` return, for
     each company, the `location` the page states for it (or null), `metroMatch` (`in`, `out`, or
     `unknown`), and `positionMatch` (`strong`, `partial`, or `weak`: how well the entry's own text
     matches the position's segment and archetype). The system checks the location:
     - a location that does not appear in the entry's own excerpt (for a listing) or in the page
       text (for a homepage), after the citation-check normalization, makes `metroMatch` `unknown`.
       Another company's location elsewhere on the same page does not count;
     - a location that reads as `"City, ST"` is classified with the R5 rules (met → `in`, not met →
       `out`), overriding the model;
     - otherwise the model's value stands.

     Candidates are sorted by `metroMatch` (in, unknown, out), then `positionMatch` (strong, partial,
     weak), then website before registry-only. Ties are spread across source pages in the order the
     pages were read. Within a page, ties follow a fixed pseudo-random order (the SHA-256 of the
     company key), which is neither page order nor alphabetical. Duplicates keep their best-ranked
     occurrence. The cap applies after ranking, and `origin.match` records the inputs.
- **Rationale**: Ranking uses only what retrieved pages say. The location must be on the page, and
  the model only classifies retrieved text (FR-006). Ranking orders candidates but never decides a
  disposition: an `out` candidate can still be kept when there is room, and Review checks its
  headquarters from cited evidence.
- **Cost**: `ListingExtraction` and `HomepageIdentity` gain three fields and now receive the position
  and the metro names, so their prompts move to v2, the replay scenarios gain the fields, and their
  real recordings are made again (T085). The design adds no model calls.
- **Alternatives considered**:
  - A separate ranking call over all candidates: one more call, and it would see only excerpts, not
    the page context.
  - Keyword overlap only: deterministic, but too crude for segment and archetype.
  - Detecting and skipping alphabetical directories: brittle, and ranking already makes their order
    irrelevant.
