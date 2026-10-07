"""T040/T082 discover: bounded searches, the discovery rules (contracts/llm-outputs.md), and targeting.

Every company comes from a page retrieved in this run, with an excerpt that passed the citation check
and names it (FR-006). Websites come only from links on those pages, never from guessing.

Targeting (FR-022, research R19): queries are ordered round-robin by metro, every search runs before
any page is read, pages are read round-robin across queries within the run total and the per-site and
per-query caps, and candidates are ranked by their match to the first position before the cap.

Writes origin evidence and `companyRecords` with `status: finding`; it never writes a disposition
(FR-011).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urldefrag, urlparse

from pydantic import BaseModel

from hipstraw_mm import prompts
from hipstraw_mm.adapters.fetch import Fetcher, FetchResult
from hipstraw_mm.adapters.llm import LLMSchemaError
from hipstraw_mm.config import Metro
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.evidence.excerpt_check import check_excerpt
from hipstraw_mm.llm_schemas import HomepageIdentity, ListedCompany, ListingExtraction, QueryPlan
from hipstraw_mm.models import (
    CompanyRecord,
    Evidence,
    EvidenceCheck,
    OriginKind,
    OriginMatch,
    SourceType,
    company_record_id,
    domain_key,
    is_denylisted,
    normalize_company_name,
    registry_key,
    site_host,
)
from hipstraw_mm.models import Origin as OriginModel
from hipstraw_mm.steps.common import EvidenceIds, reliability_for, require_run, run_step
from hipstraw_mm.steps.targeting import (
    CandidateMatch,
    MetroMatch,
    PositionMatch,
    classify_metro,
    location_on_page,
    order_queries,
    rank_candidates,
    select_pages,
)
from hipstraw_mm.store.base import Doc

STEP = "discover"
M = TypeVar("M", bound=BaseModel)
POSITION_FIELDS = ("segment", "companyArchetype", "buyer", "problem", "trigger")


@dataclass
class Found:
    """A company found on a retrieved page, before dedupe, merge, ranking, and the cap."""

    name: str
    domain: str | None  # None only for registry-only companies
    kind: OriginKind
    query: str
    result_url: str
    profile_url: str | None
    page: FetchResult  # the page the origin excerpt is on
    excerpt: str
    source_type: SourceType
    page_index: int  # position of the search result's page in reading order
    location: str | None  # only when it appears in the excerpt or homepage text
    metro: MetroMatch
    position: PositionMatch

    @property
    def key(self) -> str:
        return domain_key(self.domain) if self.domain else registry_key(self.name)

    def match(self) -> CandidateMatch:
        return CandidateMatch(self.key, self.page_index, self.domain is not None, self.metro, self.position)


def discover(ctx: Context, run_id: str) -> CommandResult:
    run = require_run(ctx.store, run_id, "created")
    return run_step(ctx, run_id, STEP, lambda: _Discovery(ctx, run).execute())


class _Discovery:
    def __init__(self, ctx: Context, run: Doc) -> None:
        self.ctx = ctx
        self.run = run
        self.run_id: str = run["runId"]
        self.budgets: dict[str, int] = run["budgets"]
        self.policy = ctx.config.source_policy
        self.max_chars = ctx.config.run.fetch.maxPageChars
        self.fetcher: Fetcher = ctx.new_fetcher()
        self.counts: Counter[str] = Counter()
        self.found: list[Found] = []
        in_force = [m["id"] for m in run["constraintsInForce"]["metros"]]
        by_id = {m.id: m for m in ctx.config.metros.metros}
        self.metros: list[Metro] = [by_id[i] for i in in_force if i in by_id]
        self.metro_names = [m["name"] for m in run["constraintsInForce"]["metros"]]
        self.position = {k: run["position"][k] for k in POSITION_FIELDS}

    # -- orchestration -------------------------------------------------------

    def execute(self) -> CommandResult:
        ctx, budgets = self.ctx, self.budgets
        searches_before, model_calls_before = ctx.search.calls, ctx.llm.calls

        queries = self._plan_queries()
        results_per_query: list[list[str]] = []
        for query in queries:
            urls: list[str] = []
            for result in ctx.search.search(query, count=budgets["resultsPerQuery"]):
                url = urldefrag(result.url)[0]
                if url not in urls:
                    urls.append(url)
            results_per_query.append(urls)

        selection = select_pages(
            results_per_query,
            total=budgets["listingPagesFetched"],
            per_query=budgets["listingPagesPerQuery"],
            per_site=budgets["listingPagesPerSite"],
        )
        self.counts["resultsOverBudget"] = selection.over_total
        self.counts["resultsOverSiteCap"] = selection.over_site
        self.counts["resultsOverQueryCap"] = selection.over_query
        for page_index, (query_index, url) in enumerate(selection.pages):
            self.counts["pagesRead"] += 1
            if self._is_direct_homepage(url):
                self._read_homepage(queries[query_index], url, page_index)
            else:
                self._read_listing(queries[query_index], url, page_index)

        kept = self._dedupe_merge_rank_and_cap()
        self._write(kept)

        target = budgets["companiesKept"]
        shortfall = max(0, target - len(kept))
        step_counts = {
            "searches": ctx.search.calls - searches_before,
            "fetches": self.fetcher.fetches,
            "modelCalls": ctx.llm.calls - model_calls_before,
            "candidatesFound": self.counts["candidatesFound"],
            "kept": len(kept),
            **{k: v for k, v in sorted(self.counts.items()) if k != "candidatesFound"},
        }
        run_counts = {
            "searches": step_counts["searches"],
            "fetches": step_counts["fetches"],
            "modelCalls": step_counts["modelCalls"],
            "candidatesFound": step_counts["candidatesFound"],
            "returned": len(kept),
            "shortfall": shortfall,
        }
        shortfall_reason = self._shortfall_reason(len(kept), target, step_counts["searches"]) if shortfall else None
        ctx.store.transition_run(
            self.run_id,
            "created",
            "discovered",
            {
                "counts": run_counts,
                "shortfallReason": shortfall_reason,
                "stepTimes": {**(self.run.get("stepTimes") or {}), "discoveredAt": ctx.now_iso()},
            },
        )
        ctx.log.step_end(self.run_id, STEP, step_counts)
        return CommandResult(
            STEP,
            message=f"run {self.run_id}: {len(kept)} companies found",
            runId=self.run_id,
            status="discovered",
            counts={"returned": len(kept), "shortfall": shortfall},
            warnings=[f"shortfall: {len(kept)} of {target} companies found"] if shortfall else [],
        )

    def _plan_queries(self) -> list[str]:
        run, budgets = self.run, self.budgets
        constraints = run["constraintsInForce"]
        payload = {
            "position": run["position"],
            "constraints": {
                "maxEmployees": constraints["maxEmployees"],
                "maxRevenueUsd": constraints["maxRevenueUsd"],
                "metros": self.metro_names,
            },
            "maxQueries": budgets["discoveryQueries"],
        }
        plan = self.ctx.llm.parse(
            QueryPlan,
            prompts.messages(prompts.QUERY_PLAN, payload),
            run["candidateId"],
            prompts.QUERY_PLAN,
            run_id=self.run_id,
            step=STEP,
        )
        queries: list[str] = []
        for planned in plan.queries:
            query = " ".join(planned.query.split())
            lowered = query.casefold()
            if not query or query in queries or any(d in lowered for d in self.policy.denylistDomains):
                self.counts["queriesDropped"] += 1
                continue
            queries.append(query)
        self.counts["queriesDropped"] += max(0, len(queries) - budgets["discoveryQueries"])
        return order_queries(queries[: budgets["discoveryQueries"]], self.metros)

    # -- the three paths for a search result --------------------------------

    def _is_direct_homepage(self, url: str) -> bool:
        return urlparse(url).path in ("", "/") and self.policy.category_for(url) is None

    def _read_homepage(self, query: str, url: str, page_index: int) -> None:
        page = self.fetcher.fetch(url, same_company_only=True)
        if not page.ok:
            self.counts["pagesFailed"] += 1
            return
        text = page.text or ""
        payload = {"url": url, "text": text[: self.max_chars], "position": self.position, "metros": self.metro_names}
        identity = self._parse(HomepageIdentity, prompts.HOMEPAGE_IDENTITY, payload, url)
        if identity is None or not identity.isCompanyHomepage:
            return
        self.counts["candidatesFound"] += 1
        name = (identity.name or "").strip()
        if not name or not identity.excerpt or not self._cited(identity.excerpt, page, name):
            self.counts["droppedFailedExcerpt"] += 1
            return
        self.found.append(
            Found(
                name,
                site_host(url),
                "direct_homepage",
                query,
                url,
                None,
                page,
                identity.excerpt,
                "company_site",
                page_index,
                identity.location if location_on_page(identity.location, text) else None,
                classify_metro(identity.location, text, identity.metroMatch, self.metros),
                identity.positionMatch,
            )
        )

    def _read_listing(self, query: str, url: str, page_index: int) -> None:
        page = self.fetcher.fetch(url)
        if not page.ok:
            self.counts["pagesFailed"] += 1
            return
        extraction = self._extract(page)
        if extraction is None:
            return
        page_url = page.final_url or url
        listing_key = domain_key(page_url)
        category = self.policy.category_for(page_url)
        source_type: SourceType = category or "directory"
        links = {link["linkId"]: link for link in page.links or []}

        for entry in extraction.companies:
            self.counts["candidatesFound"] += 1
            name = entry.name.strip()
            if not name or not self._cited(entry.excerpt, page, name):
                self.counts["droppedFailedExcerpt"] += 1
                continue
            link = links.get(entry.linkId) if entry.linkId else None
            href = link["href"] if link else None
            if href and self._is_website(href, listing_key):
                self.found.append(
                    self._found(
                        entry, name, site_host(href), "listing_link", query, url, None, page, source_type, page_index
                    )
                )
            elif href and domain_key(href) == listing_key and (hop := self._profile_hop(href, name)) is not None:
                website, profile, profile_entry = hop
                profile_type: SourceType = self.policy.category_for(href) or "directory"
                profile_url = profile.final_url or href
                self.found.append(
                    self._found(
                        profile_entry,
                        name,
                        site_host(website),
                        "profile_hop",
                        query,
                        url,
                        profile_url,
                        profile,
                        profile_type,
                        page_index,
                    )
                )
            elif category == "registry":
                self.found.append(
                    self._found(entry, name, None, "registry_only", query, url, None, page, "registry", page_index)
                )
            else:
                self.counts["droppedNoWebsite"] += 1

    def _found(
        self,
        entry: ListedCompany,
        name: str,
        domain: str | None,
        kind: OriginKind,
        query: str,
        result_url: str,
        profile_url: str | None,
        page: FetchResult,
        source_type: SourceType,
        page_index: int,
    ) -> Found:
        """A candidate from a listing entry; its location counts only if it is in the entry's excerpt."""
        return Found(
            name,
            domain,
            kind,
            query,
            result_url,
            profile_url,
            page,
            entry.excerpt,
            source_type,
            page_index,
            entry.location if location_on_page(entry.location, entry.excerpt) else None,
            classify_metro(entry.location, entry.excerpt, entry.metroMatch, self.metros),
            entry.positionMatch,
        )

    def _profile_hop(self, profile_url: str, name: str) -> tuple[str, FetchResult, ListedCompany] | None:
        """One budgeted hop to a directory's own profile page, looking for the company's external link."""
        if self.counts["profileHops"] >= self.budgets["profileHopsPerRun"]:
            self.counts["hopsOverBudget"] += 1
            return None
        self.counts["profileHops"] += 1
        page = self.fetcher.fetch(profile_url)
        if not page.ok:
            self.counts["pagesFailed"] += 1
            return None
        extraction = self._extract(page)
        if extraction is None:
            return None
        profile_key = domain_key(page.final_url or profile_url)
        links = {link["linkId"]: link for link in page.links or []}
        wanted = normalize_company_name(name)
        for entry in extraction.companies:
            link = links.get(entry.linkId) if entry.linkId else None
            if (
                normalize_company_name(entry.name) == wanted
                and link is not None
                and self._is_website(link["href"], profile_key)
                and self._cited(entry.excerpt, page, entry.name)
            ):
                return link["href"], page, entry
        return None

    # -- checks ----------------------------------------------------------------

    def _is_website(self, href: str, page_key: str) -> bool:
        """An external link to a site that is not denylisted and is not a directory, registry, or news site."""
        return (
            urlparse(href).scheme in ("http", "https")
            and domain_key(href) != page_key
            and not is_denylisted(href, self.policy.denylistDomains)
            and self.policy.category_for(href) is None
        )

    @staticmethod
    def _cited(excerpt: str, page: FetchResult, name: str) -> bool:
        """The excerpt passes the citation check against the page and contains the company name."""
        return check_excerpt(excerpt, page.text or "", claim_value=name).status == "pass"

    def _extract(self, page: FetchResult) -> ListingExtraction | None:
        payload = {
            "url": page.final_url or page.url,
            "text": (page.text or "")[: self.max_chars],
            "links": page.links,
            "position": self.position,
            "metros": self.metro_names,
        }
        return self._parse(ListingExtraction, prompts.LISTING_EXTRACTION, payload, page.url)

    def _parse(self, schema: type[M], version: str, payload: dict[str, Any], match_key: str) -> M | None:
        try:
            return self.ctx.llm.parse(
                schema, prompts.messages(version, payload), match_key, version, run_id=self.run_id, step=STEP
            )
        except LLMSchemaError as exc:
            # A second schema failure leaves that page unread (contracts/llm-outputs.md).
            self.counts["modelFailures"] += 1
            self.ctx.log.event("model_failed", run_id=self.run_id, step=STEP, error=str(exc))
            return None

    # -- dedupe, merge, rank, cap, write ----------------------------------------

    def _dedupe_merge_rank_and_cap(self) -> list[Found]:
        by_key: dict[str, Found] = {}
        for found in self.found:
            kept = by_key.get(found.key)
            if kept is None:
                by_key[found.key] = found
                continue
            self.counts["droppedDuplicates"] += 1
            if (found.match().tier(), found.page_index) < (kept.match().tier(), kept.page_index):
                by_key[found.key] = found  # keep the best-ranked occurrence
        website_names = {normalize_company_name(f.name) for f in by_key.values() if f.domain}
        merged: dict[str, Found] = {}
        for key, found in by_key.items():
            if found.domain is None and normalize_company_name(found.name) in website_names:
                self.counts["droppedByMerge"] += 1  # the same company, found through its website
            else:
                merged[key] = found
        ranked = [merged[match.key] for match in rank_candidates([f.match() for f in merged.values()])]
        cap = self.budgets["companiesKept"]
        self.counts["droppedOverCap"] += max(0, len(ranked) - cap)
        return ranked[:cap]

    def _write(self, kept: list[Found]) -> None:
        store, policy = self.ctx.store, self.policy
        ids = EvidenceIds(store, self.run_id)
        for found in kept:
            evidence_id = ids.next()
            page = found.page
            evidence = Evidence(
                evidenceId=evidence_id,
                runId=self.run_id,
                companyRecordId=None,  # listing-page evidence used at discovery (data-model.md)
                claimField="origin",
                claimValue=found.name,
                url=page.final_url or page.url,
                sourceType=found.source_type,
                reliability=reliability_for(found.source_type, policy),
                publishedAt=None,
                fetchedAt=page.fetched_at or self.ctx.now_iso(),
                excerpt=found.excerpt,
                contentSha256=page.content_sha256 or "",
                check=EvidenceCheck(status="pass"),
            )
            store.create_evidence(evidence.model_dump())
            record_id = company_record_id(self.run_id, found.key)
            record = CompanyRecord(
                companyRecordId=record_id,
                runId=self.run_id,
                candidateId=self.run["candidateId"],
                name=found.name,
                domain=found.domain,
                origin=OriginModel(
                    kind=found.kind,
                    searchQuery=found.query,
                    resultUrl=found.result_url,
                    listingEvidenceId=evidence_id,
                    profileUrl=found.profile_url,
                    match=OriginMatch(location=found.location, metroMatch=found.metro, positionMatch=found.position),
                ),
            )
            store.upsert_company_record(record_id, record.model_dump())

    def _shortfall_reason(self, kept: int, target: int, searches: int) -> str:
        c = self.counts
        dropped = c["droppedNoWebsite"] + c["droppedFailedExcerpt"] + c["droppedDuplicates"] + c["droppedByMerge"]
        skipped = c["resultsOverBudget"] + c["resultsOverSiteCap"] + c["resultsOverQueryCap"]
        return (
            f"{kept} of {target} companies found within the discovery budgets "
            f"(searches: {searches}, pages read: {c['pagesRead']}, profile hops: {c['profileHops']}, "
            f"results not read: {skipped}, of them {c['resultsOverSiteCap']} for the per-site cap and "
            f"{c['resultsOverQueryCap']} for the per-query cap). "
            f"Candidates dropped: {dropped} (no website link, failed excerpt, duplicate, or merged)."
        )
