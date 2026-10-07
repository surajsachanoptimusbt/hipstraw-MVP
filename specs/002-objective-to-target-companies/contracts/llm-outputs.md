# Contract: model calls, discovery rules, and the identifier check

There are five kinds of model call. Each is a single request with explicit inputs and a strict JSON
schema response (OpenAI Structured Outputs, `strict: true`, `additionalProperties: false`). There is
no tool calling and no multi-turn loop (Constitution VII). The schemas are defined as Pydantic models
in `src/hipstraw_mm/llm_schemas.py`. Prompt templates live in `src/hipstraw_mm/prompts/`, and each
call logs its prompt version.

**Rules that apply to every call**:
- The model only sees text the system retrieved during the run. Prompts tell it to use nothing else
  (FR-006).
- Every excerpt must be copied verbatim from the provided text, at most 300 characters. The system
  checks each excerpt (research R4). A failed check makes the claim an unknown. It is never retried
  with a looser match.
- No schema has a person field or person entity, and none has a field for an email address or phone
  number (FR-018). An excerpt that contains an email address or phone number fails its check with
  `contains_contact_data` (data-model.md). Person names may appear only incidentally, inside verbatim
  excerpts.
- The system enforces every count limit after parsing. Extra items are dropped and logged.
- A response that fails schema validation is retried once. A second failure leaves that item
  unknown and is logged.

## 1. `QueryPlan` (discover step)

**Input**: the first position, the constraints in force (with the metro names), and `maxQueries`
(the budget). Prompt `query_plan.v2`: each query names one metro in force, the queries are spread
across all of them, and local lists of companies (city startup lists, local business press,
accelerator portfolios) are preferred over generic or A–Z directories (FR-022).

```json
{
  "queries": [
    {"query": "string", "purpose": "string"}
  ]
}
```

At most `maxQueries` queries. The system removes any query that targets a denylisted domain, then
orders the rest round-robin by metro in the configured metro order. A query's metro is the first
metro whose name or listed place appears in it as whole words. Queries that name no metro come last
(research R19).

## Discovery rules (system, applied to every search result)

All planned searches run first. Their results are then read round-robin: the first result of every
query, then the second, and so on, skipping repeated URLs, until `listingPagesFetched` is reached
(research R19). A result is skipped when its site (company key) already has `listingPagesPerSite`
pages or its query already has `listingPagesPerQuery`; fetch attempts count. For each result read, the system decides one of three paths:

1. **Direct homepage**: the result URL's path is empty or `/` (ignoring the query string), and its
   domain is not listed under any `sourceTypeDomains` category in the source policy. The system
   fetches the page and makes a `HomepageIdentity` call (§3). If the page is a single company's own
   homepage and the name excerpt passes, the company becomes a candidate directly, with
   `origin.kind = direct_homepage`.
2. **Listing page**: any other result. The system fetches it and makes a `ListingExtraction` call
   (§2).
3. **Skip**: denylisted domains, robots-disallowed URLs, or results beyond the budget.

**Link rules for listing pages**:
- **External link**: the link's company key differs from the listing page's company key. The link
  is taken as the company's website (`origin.kind = listing_link`).
- **Internal link**: the link's company key equals the listing page's (for example, a directory's
  own profile page for the company). The system may make **one hop**: fetch that profile page, run
  `ListingExtraction` on it, and take the entry whose normalized name equals the company's
  normalized name and whose link is external (`origin.kind = profile_hop`). Hops count against the
  `profileHopsPerRun` budget. If the hop finds no external link, or the budget is spent, the company
  is dropped.
- **Registry page with no website**: if the listing page's domain is under `sourceTypeDomains.registry`
  and neither a direct link nor the hop yields an external website, the company is kept as a
  registry-only record (`origin.kind = registry_only`, `domain = null`). Review dispositions it
  needs verification (FR-008).
- **No link at all** on a non-registry page: the company is dropped. A company is never matched to a
  website by guessing.

**Ranking before the cap (FR-022, research R19)**. Each candidate carries `location`, `metroMatch`,
and `positionMatch` from §2 or §3. The system first checks the location:
- a `location` that does not appear in the entry's excerpt (§2) or in the homepage text (§3), after
  the citation-check normalization, makes `metroMatch` `unknown`;
- a `location` that reads as `"City, ST"` (or a full state name) is classified with the headquarters
  rules (research R5): met → `in`, not met → `out`. This overrides the model;
- otherwise the model's `metroMatch` stands.

Candidates are then sorted by `metroMatch` (`in`, `unknown`, `out`), then `positionMatch` (`strong`,
`partial`, `weak`), then website before registry-only. Ties are spread across source pages in the
order the pages were read, and within one page they follow the SHA-256 of the company key. Page order
is never used. `origin.match` stores the checked values.

Duplicates by company key keep their best-ranked occurrence. A registry-only company whose
normalized name matches a website record in the same run is dropped (merge rule in data-model.md).
Both rules, and the ranking, are applied before the `companiesKept` cap and before any record is
written. At most `companiesKept` (≤ 10) companies are kept per run. Ranking never sets a disposition.

## 2. `ListingExtraction` (discover step, once per listing or profile page)

**Input**: the page URL, its visible text, its outbound links `[{linkId, href, anchorText}]`, the
first position (segment, company archetype, buyer, problem, trigger), and the names of the metros in
force. Prompt `listing_extraction.v2`.

```json
{
  "companies": [
    {
      "name": "string",
      "linkId": "string|null",
      "excerpt": "string",
      "location": "string|null",
      "metroMatch": "in|out|unknown",
      "positionMatch": "strong|partial|weak"
    }
  ]
}
```

- `location`: the company's location exactly as this page states it, or null. Never inferred. When
  it is not null, the `excerpt` must include it.
- `metroMatch`: whether that stated location is inside one of the metros in force; `unknown` when
  `location` is null.
- `positionMatch`: how well the page's own text about the company matches the position's segment and
  archetype.

The system then checks each entry:
- The excerpt must pass the citation check and must contain `name`.
- `linkId` must be one of the provided links, or null. Classifying and following it uses the link
  rules above.

## 3. `HomepageIdentity` (discover step, once per direct-homepage result)

**Input**: the page URL, its visible text, the first position, and the names of the metros in force.
Prompt `homepage_identity.v2`.

```json
{
  "isCompanyHomepage": true,
  "name": "string|null",
  "excerpt": "string|null",
  "location": "string|null",
  "metroMatch": "in|out|unknown",
  "positionMatch": "strong|partial|weak"
}
```

The three ranking fields mean the same as in §2.

The page becomes a direct candidate only if `isCompanyHomepage` is true, `name` is non-empty, and
`excerpt` passes the citation check and contains `name`. Otherwise the result is ignored. It is not
treated as a listing page.

## 4. `CompanyEvidence` (verify step, once per company with a website)

**Input**: the company name and domain, the first position, the six primary interests, and the
fetched pages `[{sourceId, url, sourceType, text}]` (own-site pages plus the signal-search pages).

```json
{
  "claims": [
    {
      "claimId": "c1",
      "claimField": "hq|employees|revenue|parent|parent_employees|parent_revenue|fit_buyer|fit_problem|fit_trigger|signal_pain|signal_exploration",
      "claimValue": "string",
      "sourceId": "string",
      "excerpt": "string"
    }
  ],
  "fitClaims": [
    {"aspect": "buyer|problem|trigger", "statement": "string", "primaryInterestIds": ["string"], "claimIds": ["c1"]}
  ],
  "interestSignals": [
    {"kind": "pain|exploration", "statement": "string", "claimIds": ["c2"]}
  ],
  "falsifier": "string"
}
```

The system then:
- turns every claim into an `evidence` document and runs its check;
- keeps a fit claim or interest signal only if at least one of its claims passed;
- keeps no interest signal of either kind without a passing citation (FR-020). Phrases such as
  "heavy spend" are examples in the prompt, not criteria;
- records everything else under `unknowns`;
- requires `primaryInterestIds` to be non-empty and to contain only known interest IDs (FR-005);
- keeps conflicting `employees` or `revenue` values as separate signals (FR-010);
- treats `parent_employees` and `parent_revenue` as structured claims about the parent's size
  (research R6; prompt `company_evidence.v2`).

Registry-only companies, and companies whose website did not resolve, get no `CompanyEvidence` call.

## Signal searches (verify step, no model)

For each company whose website resolves, the system runs up to `signalSearchesPerCompany` searches
with exactly these query strings, in this order (research R7):

1. `"<name>" accounts payable OR procurement job`
2. `"<name>" invoice automation OR "AI agents" finance`
3. `site:<domain> careers`

From the results, in search order and then result order, it fetches up to
`thirdPartyPagesPerCompany` pages that are not on the company's own site, skipping denylisted and
already-fetched URLs. Results on the company's own site count toward `ownSitePagesPerCompany`.
Third-party pages follow the own-site pages in the `CompanyEvidence` input, with `sourceType` from
the source type rules (contracts/config.md).

## 5. `ReviewJudgement` (review step, only for records that pass every rule)

**Input**: the first position, the company name, the falsifier, and only the passing evidence
`[{evidenceId, claimField, claimValue, excerpt, url}]`.

```json
{
  "falsifierMet": true,
  "fitHolds": false,
  "citedEvidenceIds": ["ev_..."],
  "reason": "string"
}
```

The system then decides the disposition:
- if any cited ID is not in the provided passing evidence → `needs_verification`, with the reason
  "judgement cited unknown evidence";
- if `falsifierMet` → `exclude`;
- if not `fitHolds` → `needs_verification`;
- if the record has no passing evidence document → `needs_verification`;
- otherwise → `include`, with the IDs of the record's passing evidence documents attached to the
  decision by the system. The model does not need to cite them.

The judgement can never turn a rule-gate failure into `include` (research R9).

## Identifier check and existence evidence (verify step, no model involved)

1. **Website load (FR-008)**: fetch `https://<domain>/`, following redirects only while they stay
   within the same company key or its subdomains (for example, `acme.test` → `www.acme.test` or
   `app.acme.test`).
   - A 2xx response after redirects → `identifierCheck.status = resolves`.
   - The website does not exist: HTTP 404 or 410, or a host name that does not resolve
     (`dns_error`) → `fails`. Review excludes.
   - Anything else → `unreadable`, with the HTTP status and the fetcher's reason. This covers a
     robots.txt disallow (the page is not fetched), HTTP 401, 403, and 429, other HTTP errors,
     timeouts and connection errors, a redirect to another company key, and a non-HTML or oversized
     page. Review dispositions needs verification and records why (revised 2026-10-07).
   - Registry-only companies are not fetched → `no_website`.
   - `nameMatchesDomain`: true when some label of the website's host (hyphens removed) contains the
     company's compact normalized name, or is contained in it, or contains the name's first word of
     three or more characters. Otherwise false (for example Addison Health Systems → writepad.com).
2. **Existence evidence (FR-016)**: for a website that resolves, build one `existence` evidence
   document from the homepage text, or, if the homepage does not name the company, from the first
   already-fetched about or contact page that does, as defined in data-model.md. Its excerpt is the text around the
   company name, and it passes only if it contains the name. When `nameMatchesDomain` is false, this
   citation is the only link between the company and the website; if it fails, the
   needs-verification reason names both.
