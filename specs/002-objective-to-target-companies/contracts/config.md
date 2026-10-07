# Contract: configuration files

All files are YAML and are validated with Pydantic when a command starts (exit code 1 on error).
Size and location filters are configuration values only; the code holds no thresholds or place names.
Secrets never appear in these files.

## `config/programs/invoice_alpha.yaml`

```yaml
programId: invoice_alpha_genesis
name: Kozmo Invoice Alpha Genesis Cohort
sourceUrl: https://kozmo.ai/invoice-alpha-genesis.html
objective: >-
  Find companies whose procurement, AP, finance, and commercial teams would benefit from continuous
  obligation intelligence: catching invoice divergence before payment, protecting entitlements, and
  preventing leakage.
experimentContexts:            # exactly 6
  - {id: saas_recurring_fees, label: SaaS / recurring fees}
  - {id: professional_services, label: Professional services}
  - {id: managed_services, label: Managed services}
  - {id: consulting_services, label: Consulting + services}
  - {id: mixed_obligations, label: Mixed obligations}
  - {id: strategic_suppliers, label: Strategic suppliers}
primaryInterests:              # exactly 6
  - {id: continuous_obligation_intelligence, label: Continuous obligation intelligence}
  - {id: invoice_accuracy_entitlement, label: Invoice accuracy / entitlement}
  - {id: scope_drift_prevention, label: Scope drift / prevention}
  - {id: payment_timing_working_capital, label: Payment timing / working capital}
  - {id: supplier_commercial_position, label: Supplier commercial position}
  - {id: agent_governance_autonomy, label: Agent governance / autonomy}
```

The content was transcribed from the 2026-10-07 clarifications. Check it against `sourceUrl` before a
demo (research R15).

## `config/run.yaml`

```yaml
projectId: demo-hipstraw-mvp     # must start with "demo-"
constraints:
  maxEmployees: 500              # strict "less than"
  maxRevenueUsd: 100000000       # strict "less than"
  metroIds: [atlanta, san_francisco, new_york]
  largeEnterpriseParents: []     # optional parent names to treat as large, compared by normalized name
budgets:                         # research R13
  discoveryQueries: 6
  resultsPerQuery: 10
  listingPagesFetched: 12        # listing pages and direct-homepage results
  listingPagesPerSite: 3         # per company key; fetch attempts count (2026-10-07)
  listingPagesPerQuery: 3        # per planned query (2026-10-07)
  profileHopsPerRun: 10          # one hop per company at most (contracts/llm-outputs.md)
  companiesKept: 10              # FR-004 cap; must be <= 10
  ownSitePagesPerCompany: 6
  signalSearchesPerCompany: 3
  thirdPartyPagesPerCompany: 4
  verifyFetchesPerRun: 110       # run-level ceiling for verify; running out with companies left → exit 4
  verifyModelCallsPerRun: 20     # run-level ceiling for verify (one call per company plus retries)
fetch:
  timeoutSeconds: 15
  maxBytes: 2000000
  perHostDelaySeconds: 1.0
  maxPageChars: 20000            # text passed to the model per page
model:
  name: ${LLM_MODEL}             # resolved from the environment
```

## `config/metros.yaml`

```yaml
metros:
  - id: atlanta
    name: Atlanta–Athens-Clarke County–Sandy Springs, GA-AL CSA
    csaCode: "122"
    states: [GA, AL]
    counties:                    # per state: every county in the CSA
      GA: [Fulton, DeKalb, Cobb, Gwinnett, ...]
      AL: [Chambers]
    places:                      # per state: EVERY Census place in those counties
      GA: [Atlanta, Sandy Springs, Alpharetta, Marietta, Roswell, Norcross, ...]
      AL: [Lanett, Valley, ...]
  - id: san_francisco
    name: San Jose–San Francisco–Oakland, CA CSA
    csaCode: "488"
    states: [CA]
    counties: {CA: [San Francisco, San Mateo, Santa Clara, Alameda, ...]}
    places: {CA: [San Francisco, Oakland, San Jose, Palo Alto, Mountain View, ...]}
  - id: new_york
    name: New York–Newark, NY-NJ-CT-PA CSA
    csaCode: "408"
    states: [NY, NJ, CT, PA]
    counties: {NY: [New York, Kings, ...], NJ: [Hudson, Essex, ...], CT: [Fairfield, ...], PA: [Pike, ...]}
    places: {NY: [New York, Brooklyn, Yonkers, ...], NJ: [Jersey City, Newark, Hoboken, ...], CT: [Stamford, ...], PA: [...]}
```

The CSA names, codes, and states above are illustrative and must be checked against the current
Census CSA delineation file. **Since 2026-10-07 a cited city that is not on its state's place list
makes the location `not_met`** (research R5), so the place lists must be complete: every incorporated
place, census-designated place, and county subdivision (town or township) in the CSA's counties,
keyed by state, because the same place name can exist in two states of one CSA. They are generated from the Census CSA delineation file and the
place-to-county relationship file by `scripts/build_metro_places.py` and committed, with the source
files and their dates recorded in the YAML header (T052). Every key of `counties` and `places` must
be one of the metro's `states`.

## `config/source_policy.yaml`

```yaml
userAgent: "HipStrawMM/0.1 (+https://hipstraw.example/bot)"   # replace the contact URL before live runs
denylistDomains:          # terms forbid automated access; never fetched (FR-002)
  - linkedin.com
  - glassdoor.com
  - indeed.com
  - zoominfo.com
  - crunchbase.com
  - pitchbook.com
  - fortune.com
reliabilityBySourceType:  # research R8
  registry: high
  news: medium
  company_site: medium
  job_board: medium
  directory: low
reliabilityWeights:       # confidence weights per reliability level (research R8)
  high: 1.0
  medium: 0.7
  low: 0.4
sourceTypeDomains:        # classifies pages by domain; matches the domain or any subdomain
  registry: [sos.ga.gov, sos.ca.gov, dos.ny.gov]   # official state registries only
  job_board: [greenhouse.io, lever.co, ashbyhq.com, workable.com]
  directory: [builtin.com, clutch.co, g2.com]
  news: [businesswire.com, prnewswire.com, techcrunch.com]
```

**Source type rules**:
- A page on the company's own domain is `company_site`.
- A page matching a `sourceTypeDomains` entry gets that type.
- Any other listing page is `directory`, and any other page found by a signal search is `news`.

Each domain on the denylist must be reviewed against that site's terms. The `sourceTypeDomains`
entries are starting examples to review the same way. Adding a domain needs no code change.
`reliabilityWeights` must have exactly the keys `high`, `medium`, and `low`, each in (0, 1].

## First-position file (passed to `position --file`)

```yaml
candidateId: invoice_alpha_genesis__saas_recurring_fees
segment: "string"
companyArchetype: "string"
buyer: "string"
problem: "string"
trigger: "string"
primaryInterestIds: [invoice_accuracy_entitlement]    # at least 1, known IDs only
searchHints: ["optional keyword", "..."]             # optional
```

A HipStraw team member writes this file by hand (spec Assumptions). `positions/first_position.example.yaml`
ships as a template.

## Environment variables

| Variable | Required for | Notes |
|----------|--------------|-------|
| `FIRESTORE_EMULATOR_HOST` | every command | `127.0.0.1:8085` |
| `HIPSTRAW_PROJECT_ID` | optional | Defaults to `run.yaml` `projectId` |
| `OPENAI_API_KEY`, `LLM_MODEL` | `discover`, `verify`, `review` | Same names as V0 |
| `BRAVE_API_KEY` | `discover`, `verify` | Same name as V0 |
| `HIPSTRAW_REPLAY` | tests | `replay` (default in tests) or `record` |
