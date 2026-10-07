"""T041 verify (thin): website load, existence evidence, cited claims, and their checks.

- The company's own website must load, following redirects only within its company key (FR-008).
- Existence evidence is built from the homepage without a model (FR-016).
- One `CompanyEvidence` call per loading website; every claim becomes an evidence document with its
  check, and a claim without a passing citation is an explicit unknown (FR-007, FR-009).
- Registry-only companies are never fetched and get no evidence call (FR-005).

Writes evidence and completed `companyRecords`; it never writes a disposition (FR-011).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urldefrag, urlparse

from hipstraw_mm import prompts
from hipstraw_mm.adapters.fetch import FetchResult
from hipstraw_mm.adapters.llm import LLMSchemaError
from hipstraw_mm.config import Metro
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.evidence.excerpt_check import MAX_EXCERPT_CHARS, WITHHELD_EXCERPT, CheckResult, check_excerpt
from hipstraw_mm.evidence.existence import existence_excerpt, website_status
from hipstraw_mm.evidence.location import evaluate_hq
from hipstraw_mm.evidence.size import evaluate_size
from hipstraw_mm.llm_schemas import CompanyEvidence
from hipstraw_mm.models import CompanyRecord, Evidence, same_company_or_subdomain
from hipstraw_mm.steps.common import (
    UNKNOWN_FIELD_FOR_CLAIM,
    EvidenceIds,
    merge_counts,
    reliability_for,
    require_run,
    run_step,
    website_problem,
)
from hipstraw_mm.store.base import Doc

STEP = "verify"
OWN_SITE_KEYWORDS = ("about", "company", "careers", "jobs", "contact", "locations", "press", "news")
STRUCTURED_FIELDS = {"hq", "employees", "revenue", "parent"}
CLAIM_ITEMS = ("hq", "size", "fit", "interestSignal")
EMPTY_HQ: dict[str, Any] = {"city": None, "state": None, "status": "unknown", "evidenceIds": []}
EMPTY_SIZE: dict[str, Any] = {"signals": [], "status": "unknown"}


def verify(ctx: Context, run_id: str) -> CommandResult:
    run = require_run(ctx.store, run_id, "discovered")
    return run_step(ctx, run_id, STEP, lambda: _Verification(ctx, run).execute())


def _unknown(item: str, reason: str) -> dict[str, str]:
    return {"field": item, "reason": reason}


@dataclass
class _Extraction:
    """The outcome of one CompanyEvidence call, after every claim's citation check."""

    result: CompanyEvidence | None = None
    claims: dict[str, tuple[str, str, bool]] = field(default_factory=dict)  # evidenceId -> (field, value, passed)
    evidence_by_claim: dict[str, str] = field(default_factory=dict)  # the model's claimId -> evidenceId
    failed: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))  # unknowns field -> reasons

    def passing(self, *claim_fields: str) -> list[tuple[str, str, str]]:
        """(claimField, claimValue, evidenceId) for each passing claim of these fields."""
        return [(f, value, eid) for eid, (f, value, ok) in self.claims.items() if ok and f in claim_fields]

    def passing_ids(self, claim_ids: list[str], field_prefix: str = "") -> list[str]:
        ids = dict.fromkeys(self.evidence_by_claim[c] for c in claim_ids if c in self.evidence_by_claim)
        return [i for i in ids if self.claims[i][2] and self.claims[i][0].startswith(field_prefix)]

    def missing_reason(self, item: str) -> str:
        reasons = sorted(self.failed.get(item, set()))
        return f"citation failed: {', '.join(reasons)}" if reasons else "no passing citation found"


class _Verification:
    def __init__(self, ctx: Context, run: Doc) -> None:
        self.ctx = ctx
        self.run = run
        self.run_id: str = run["runId"]
        self.budgets: dict[str, int] = run["budgets"]
        self.policy = ctx.config.source_policy
        self.max_chars = ctx.config.run.fetch.maxPageChars
        self.fetcher = ctx.new_fetcher()
        self.ids = EvidenceIds(ctx.store, self.run_id)
        self.counts: Counter[str] = Counter()
        self.model_calls_before = ctx.llm.calls
        in_force = {m["id"] for m in run["constraintsInForce"]["metros"]}
        self.metros: list[Metro] = [m for m in ctx.config.metros.metros if m.id in in_force]
        program = ctx.store.get_program(run["programId"]) or {}
        self.primary_interests: list[dict[str, str]] = program.get("primaryInterests", [])

    # -- budgets -------------------------------------------------------------------

    def _fetches_left(self) -> int:
        return self.budgets["verifyFetchesPerRun"] - self.fetcher.fetches

    def _model_calls_left(self) -> int:
        return self.budgets["verifyModelCallsPerRun"] - (self.ctx.llm.calls - self.model_calls_before)

    # -- orchestration -------------------------------------------------------------

    def execute(self) -> CommandResult:
        ctx = self.ctx
        for record in ctx.store.list_company_records(self.run_id):
            if record["domain"] is None:
                updates = self._registry_only()
            elif self._fetches_left() <= 0:
                updates = self._unverified("the verify fetch budget ran out")
            else:
                updates = self._website(record)
            self._save(record, updates)
        warnings = []
        if self.counts["unverified"]:
            # T055 (after the demo) turns this into exit code 4 with the run marked failed.
            warnings.append(f"verify budget ran out: {self.counts['unverified']} companies not verified")

        step_counts = {
            "fetches": self.fetcher.fetches,
            "modelCalls": ctx.llm.calls - self.model_calls_before,
            "companiesVerified": self.counts["companiesVerified"],
            "registryOnly": self.counts["registryOnly"],
            "websitesFailed": self.counts["websitesFailed"],
            "websitesUnreadable": self.counts["websitesUnreadable"],
            "unverified": self.counts["unverified"],
            "citationsPassed": self.counts["citationsPassed"],
            "citationsFailed": self.counts["citationsFailed"],
        }
        run_counts = merge_counts(
            self.run.get("counts"), {"fetches": step_counts["fetches"], "modelCalls": step_counts["modelCalls"]}
        )
        ctx.store.transition_run(
            self.run_id,
            "discovered",
            "verified",
            {"counts": run_counts, "stepTimes": {**(self.run.get("stepTimes") or {}), "verifiedAt": ctx.now_iso()}},
        )
        ctx.log.step_end(self.run_id, STEP, step_counts)
        return CommandResult(
            STEP,
            message=f"run {self.run_id}: {self.counts['companiesVerified']} websites loaded and read",
            runId=self.run_id,
            status="verified",
            counts={k: v for k, v in step_counts.items() if k not in ("fetches", "modelCalls")},
            warnings=warnings,
        )

    def _save(self, record: Doc, updates: dict[str, Any]) -> None:
        merged = {k: v for k, v in record.items() if k != "createdAt"} | updates
        validated = CompanyRecord.model_validate(merged).model_dump()
        self.ctx.store.upsert_company_record(record["companyRecordId"], validated)

    # -- registry-only and unverified records ---------------------------------------

    def _registry_only(self) -> dict[str, Any]:
        self.counts["registryOnly"] += 1
        reason = "registry-only: no website to read"
        return {
            "identifierCheck": {"status": "no_website", "checkedAt": self.ctx.now_iso()},
            "existenceEvidenceId": None,
            "hq": EMPTY_HQ,
            "size": EMPTY_SIZE,
            "fitClaims": [],
            "interestSignals": [],
            "falsifier": None,
            "unknowns": [
                _unknown("existence", "registry-only: no website to check"),
                *(_unknown(item, reason) for item in (*CLAIM_ITEMS, "falsifier")),
            ],
        }

    def _unverified(self, reason: str) -> dict[str, Any]:
        self.counts["unverified"] += 1
        return {
            "identifierCheck": None,
            "hq": EMPTY_HQ,
            "size": EMPTY_SIZE,
            "unknowns": [_unknown(item, reason) for item in ("existence", *CLAIM_ITEMS, "falsifier")],
        }

    # -- companies with a website ----------------------------------------------------

    def _website(self, record: Doc) -> dict[str, Any]:
        record_id, domain, name = record["companyRecordId"], record["domain"], record["name"]
        home = self.fetcher.fetch(f"https://{domain}/", same_company_only=True)
        status = website_status(home.fail_reason, home.status) if not home.ok else "resolves"
        identifier = {
            "status": status,
            "httpStatus": home.status,
            "finalUrl": home.final_url,
            "failReason": home.fail_reason,
            "checkedAt": self.ctx.now_iso(),
        }
        if status != "resolves":
            # Nothing more is fetched or extracted for a website that does not exist or cannot be read.
            self.counts["websitesFailed" if status == "fails" else "websitesUnreadable"] += 1
            reason = website_problem(status, home.fail_reason, home.status, home.final_url)
            return {
                "identifierCheck": identifier,
                "existenceEvidenceId": None,
                "hq": EMPTY_HQ,
                "size": EMPTY_SIZE,
                "fitClaims": [],
                "interestSignals": [],
                "falsifier": None,
                "unknowns": [_unknown(item, reason) for item in ("existence", *CLAIM_ITEMS, "falsifier")],
            }

        self.counts["companiesVerified"] += 1
        existence_id, existence_check = self._existence_evidence(record_id, name, home)
        extraction = self._extract(record_id, name, domain, [home, *self._own_site_pages(home)])

        constraints = self.run["constraintsInForce"]
        hq = evaluate_hq([(value, eid) for _, value, eid in extraction.passing("hq")], self.metros)
        size = evaluate_size(
            extraction.passing("employees", "revenue"),
            constraints["maxEmployees"],
            constraints["maxRevenueUsd"],
        )
        fit_claims, interest_signals = self._fit_and_signals(extraction)
        falsifier = (extraction.result.falsifier.strip() or None) if extraction.result else None

        unknowns = []
        if existence_check.status != "pass":
            unknowns.append(_unknown("existence", f"existence citation failed: {existence_check.reason}"))
        if not hq["evidenceIds"]:
            unknowns.append(_unknown("hq", extraction.missing_reason("hq")))
        if not size["signals"]:
            unknowns.append(_unknown("size", extraction.missing_reason("size")))
        if extraction.failed.get("parent") and not extraction.passing("parent"):
            unknowns.append(_unknown("parent", extraction.missing_reason("parent")))
        if not fit_claims:
            unknowns.append(_unknown("fit", extraction.missing_reason("fit")))
        if not interest_signals:
            unknowns.append(_unknown("interestSignal", extraction.missing_reason("interestSignal")))
        if not falsifier:
            unknowns.append(_unknown("falsifier", "no falsifier was extracted"))

        return {
            "identifierCheck": identifier,
            "existenceEvidenceId": existence_id,
            "hq": hq,
            "size": size,
            "parent": None,  # parent evaluation comes with T053
            "fitClaims": fit_claims,
            "interestSignals": interest_signals,
            "unknowns": unknowns,
            "falsifier": falsifier,
            "confidence": None,  # T054 computes confidence
        }

    def _existence_evidence(self, record_id: str, name: str, home: FetchResult) -> tuple[str, CheckResult]:
        text = home.text or ""
        excerpt = existence_excerpt(text, name)
        check = check_excerpt(excerpt, text, claim_value=name) if excerpt else CheckResult("fail", "excerpt_not_found")
        return self._store_evidence(record_id, "existence", name, home, excerpt, check), check

    def _own_site_pages(self, home: FetchResult) -> list[FetchResult]:
        """Own-site pages linked from the homepage whose path names an about, careers, ... page."""
        home_url = urldefrag(home.final_url or home.url)[0]
        limit = min(self.budgets["ownSitePagesPerCompany"], max(0, self._fetches_left()))
        pages: list[FetchResult] = []
        seen = {home_url}
        for link in home.links or []:
            if len(pages) >= limit:
                break
            href = urldefrag(link["href"])[0]
            path = urlparse(href).path.casefold()
            if href in seen or not same_company_or_subdomain(home_url, href):
                continue
            if not any(keyword in path for keyword in OWN_SITE_KEYWORDS):
                continue
            seen.add(href)
            page = self.fetcher.fetch(href, same_company_only=True)
            if page.ok:
                pages.append(page)
        return pages

    def _extract(self, record_id: str, name: str, domain: str, pages: list[FetchResult]) -> _Extraction:
        """One CompanyEvidence call; every claim becomes an evidence document with its check."""
        extraction = _Extraction()
        if self._model_calls_left() <= 0:
            for item in CLAIM_ITEMS:
                extraction.failed[item].add("verify model-call budget ran out")
            return extraction

        # Source IDs follow page order: the homepage is s1, then own-site pages in homepage link order.
        by_source = {f"s{i}": page for i, page in enumerate(pages, start=1)}
        payload = {
            "company": name,
            "domain": domain,
            "position": self.run["position"],
            "primaryInterests": self.primary_interests,
            "pages": [
                {
                    "sourceId": source_id,
                    "url": page.final_url or page.url,
                    "sourceType": "company_site",
                    "text": (page.text or "")[: self.max_chars],
                }
                for source_id, page in by_source.items()
            ],
        }
        try:
            result = self.ctx.llm.parse(
                CompanyEvidence,
                prompts.messages(prompts.COMPANY_EVIDENCE, payload),
                domain,
                prompts.COMPANY_EVIDENCE,
                run_id=self.run_id,
                step=STEP,
                company_record_id=record_id,
            )
        except LLMSchemaError as exc:
            self.ctx.log.event(
                "model_failed", run_id=self.run_id, step=STEP, company_record_id=record_id, error=str(exc)
            )
            for item in CLAIM_ITEMS:
                extraction.failed[item].add("evidence extraction failed")
            return extraction

        extraction.result = result
        for claim in result.claims:
            item = UNKNOWN_FIELD_FOR_CLAIM[claim.claimField]
            page = by_source.get(claim.sourceId)
            if page is None:  # the model cited a page it was not given
                extraction.failed[item].add("not_retrievable")
                self.counts["citationsFailed"] += 1
                continue
            value = claim.claimValue if claim.claimField in STRUCTURED_FIELDS else None
            check = check_excerpt(claim.excerpt, page.text or "", value)
            evidence_id = self._store_evidence(
                record_id, claim.claimField, claim.claimValue, page, claim.excerpt, check
            )
            extraction.claims[evidence_id] = (claim.claimField, claim.claimValue, check.status == "pass")
            extraction.evidence_by_claim[claim.claimId] = evidence_id
            if check.status == "pass":
                self.counts["citationsPassed"] += 1
            else:
                extraction.failed[item].add(str(check.reason))
                self.counts["citationsFailed"] += 1
        return extraction

    def _fit_and_signals(self, extraction: _Extraction) -> tuple[list[Doc], list[Doc]]:
        """Keep a fit claim or interest signal only if at least one of its claims passed (FR-007, FR-020)."""
        if extraction.result is None:
            return [], []
        known = {i["id"] for i in self.primary_interests}
        fit_claims = []
        for fit in extraction.result.fitClaims:
            evidence_ids = extraction.passing_ids(fit.claimIds)
            interests = [i for i in fit.primaryInterestIds if i in known]
            if evidence_ids and interests:
                fit_claims.append(
                    {
                        "aspect": fit.aspect,
                        "statement": fit.statement,
                        "primaryInterestIds": interests,
                        "evidenceIds": evidence_ids,
                    }
                )
        signals = []
        for signal in extraction.result.interestSignals:
            # An interest signal must rest on a passing signal citation, never on another kind of claim.
            evidence_ids = extraction.passing_ids(signal.claimIds, "signal_")
            if evidence_ids:
                signals.append({"kind": signal.kind, "statement": signal.statement, "evidenceIds": evidence_ids})
        return fit_claims, signals

    def _store_evidence(
        self, record_id: str, claim_field: str, claim_value: str, page: FetchResult, excerpt: str, check: CheckResult
    ) -> str:
        evidence_id = self.ids.next()
        if check.reason == "contains_contact_data":
            excerpt = WITHHELD_EXCERPT  # FR-018: never store contact data
        evidence = Evidence.model_validate(
            {
                "evidenceId": evidence_id,
                "runId": self.run_id,
                "companyRecordId": record_id,
                "claimField": claim_field,
                "claimValue": claim_value,
                "url": page.final_url or page.url,
                "sourceType": "company_site",
                "reliability": reliability_for("company_site", self.policy),
                "publishedAt": None,
                "fetchedAt": page.fetched_at or self.ctx.now_iso(),
                "excerpt": excerpt[:MAX_EXCERPT_CHARS],
                "contentSha256": page.content_sha256 or "",
                "check": check.to_dict(),
            }
        )
        self.ctx.store.create_evidence(evidence.model_dump())
        return evidence_id
