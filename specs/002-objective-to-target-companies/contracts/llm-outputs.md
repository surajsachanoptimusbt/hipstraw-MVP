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

**Input**: the first position, the constraints in force, and `maxQueries` (the budget).

```json
{
  "queries": [
    {"query": "string", "purpose": "string"}
  ]
}
```

At most `maxQueries` queries. The system removes any query that targets a denylisted domain.

## Discovery rules (system, applied to every search result)

For each search result, the system decides one of three paths:

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

Duplicates by company key are merged into the first record. A registry-only company whose normalized
name matches a website record in the same run is dropped (merge rule in data-model.md). Both rules
are applied before the `companiesKept` cap and before any record is written. At most `companiesKept`
(≤ 10) companies are kept per run.

## 2. `ListingExtraction` (discover step, once per listing or profile page)

**Input**: the page URL, its visible text, and its outbound links `[{linkId, href, anchorText}]`.

```json
{
  "companies": [
    {"name": "string", "linkId": "string|null", "excerpt": "string"}
  ]
}
```

The system then checks each entry:
- The excerpt must pass the citation check and must contain `name`.
- `linkId` must be one of the provided links, or null. Classifying and following it uses the link
  rules above.

## 3. `HomepageIdentity` (discover step, once per direct-homepage result)

**Input**: the page URL and its visible text.

```json
{
  "isCompanyHomepage": true,
  "name": "string|null",
  "excerpt": "string|null"
}
```

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
      "claimField": "hq|employees|revenue|parent|fit_buyer|fit_problem|fit_trigger|signal_pain|signal_exploration",
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
- keeps conflicting `employees` or `revenue` values as separate signals (FR-010).

Registry-only companies get no `CompanyEvidence` call. They have no website to read.

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
   - Anything else, including a redirect to another company key → `fails`, with the HTTP status.
   - Registry-only companies are not fetched → `no_website`.
2. **Existence evidence (FR-016)**: for a website that resolves, build one `existence` evidence
   document from the homepage text, as defined in data-model.md. Its excerpt is the text around the
   company name, and it passes only if it contains the name.
