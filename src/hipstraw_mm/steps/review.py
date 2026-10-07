"""T042 review: the Market Manager's rule gate, then one bounded judgement call (research R9).

Only this step writes `reviewDecisions` and the `positionBaselines` snapshot (FR-011, FR-021). The
judgement runs only for records that pass every rule, sees only passing evidence, and can keep or
downgrade a disposition, never upgrade one. The system attaches the record's passing evidence IDs to
each decision; an include needs at least one.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from hipstraw_mm import prompts
from hipstraw_mm.adapters.llm import LLMSchemaError
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.llm_schemas import ReviewJudgement
from hipstraw_mm.models import Disposition, PositionBaseline, ReviewDecision
from hipstraw_mm.steps.common import require_run, run_step, website_problem
from hipstraw_mm.store.base import Doc

STEP = "review"
RULES_VERSION = "rules-v1"


@dataclass
class GateResult:
    rule_results: list[Doc]
    disposition: Disposition | None  # None: every rule passed, so the judgement decides
    reason: str


def _passed(evidence: Doc | None) -> bool:
    return evidence is not None and evidence.get("check", {}).get("status") == "pass"


def _size_values(record: Doc, evidence_by_id: dict[str, Doc]) -> str:
    """The cited size values, for example "450 employees and 620 employees" (FR-015)."""
    values = []
    for signal in (record.get("size") or {}).get("signals", []):
        evidence = evidence_by_id.get(signal["evidenceId"], {})
        values.append(f"{evidence.get('claimValue', '?')} {signal['kind']}")
    return " and ".join(values) or "no figures"


def rule_gate(record: Doc, evidence_by_id: dict[str, Doc]) -> GateResult:
    """Research R9 rules: a failed rule excludes; an unknown or conflicting one needs verification."""
    results: list[tuple[Doc, str]] = []

    identifier = record.get("identifierCheck") or {}
    existence_ids = [record["existenceEvidenceId"]] if record.get("existenceEvidenceId") else []
    status = identifier.get("status")
    if status in ("fails", "unreadable"):
        problem = website_problem(
            status, identifier.get("failReason"), identifier.get("httpStatus"), identifier.get("finalUrl")
        )
        existence = ("fail" if status == "fails" else "unknown", problem)
    elif status == "no_website":
        existence = ("unknown", "registry-only: no website, so existence cannot be checked")
    elif status == "resolves" and _passed(evidence_by_id.get(record.get("existenceEvidenceId") or "")):
        existence = ("pass", "")
    elif status == "resolves" and identifier.get("nameMatchesDomain") is False:
        existence = (
            "unknown",
            f"the website {record.get('domain')} does not carry the company's name, and neither its homepage "
            f"nor its about or contact pages name {record.get('name')}",
        )
    elif status == "resolves":
        existence = ("unknown", "no page read on the website names the company")
    else:
        existence = ("unknown", "the website was not checked")
    results.append(({"rule": "existence", "outcome": existence[0], "evidenceIds": existence_ids}, existence[1]))

    hq = record.get("hq") or {}
    hq_ids = hq.get("evidenceIds", [])
    cited = " and ".join(dict.fromkeys(evidence_by_id[i]["claimValue"] for i in hq_ids if i in evidence_by_id))
    place = cited or ", ".join(p for p in (hq.get("city"), hq.get("state")) if p)
    hq_outcome = {"met": "pass", "not_met": "fail", "conflict": "conflict"}.get(hq.get("status", ""), "unknown")
    if hq_outcome == "fail":
        hq_detail = f"headquarters {place} is outside the metros in force"
    elif hq_outcome == "conflict":
        hq_detail = f"headquarters citations disagree, inside and outside the metros ({place})"
    elif hq_outcome == "unknown":
        hq_detail = f"headquarters {place} names no city" if hq_ids else "no passing headquarters citation"
    else:
        hq_detail = ""
    results.append(({"rule": "hq", "outcome": hq_outcome, "evidenceIds": hq.get("evidenceIds", [])}, hq_detail))

    size = record.get("size") or {}
    size_ids = [s["evidenceId"] for s in size.get("signals", [])]
    size_outcome = {"under": "pass", "over": "fail", "conflict": "conflict"}.get(size.get("status", ""), "unknown")
    size_detail = {
        "fail": f"size is over the thresholds ({_size_values(record, evidence_by_id)})",
        "conflict": f"size evidence conflicts across a threshold ({_size_values(record, evidence_by_id)})",
        "unknown": "no passing size citation",
    }.get(size_outcome, "")
    results.append(({"rule": "size", "outcome": size_outcome, "evidenceIds": size_ids}, size_detail))

    signals = record.get("interestSignals") or []
    signal_ids = list(dict.fromkeys(i for s in signals for i in s["evidenceIds"]))
    signal_outcome = "pass" if signals else "unknown"
    signal_detail = "" if signals else "no interest signal with a passing citation"
    results.append(({"rule": "interest_signal", "outcome": signal_outcome, "evidenceIds": signal_ids}, signal_detail))

    rule_results = [r for r, _ in results]
    failed = [detail for r, detail in results if r["outcome"] == "fail"]
    open_items = [detail for r, detail in results if r["outcome"] in ("unknown", "conflict")]
    if failed:
        return GateResult(rule_results, "exclude", "Excluded: " + "; ".join(failed) + ".")
    if open_items:
        return GateResult(rule_results, "needs_verification", "Needs verification: " + "; ".join(open_items) + ".")
    return GateResult(rule_results, None, "")


def judged_disposition(judgement: ReviewJudgement, passing_evidence_ids: list[str]) -> tuple[Disposition, str]:
    """The disposition for a record that passed every rule (contracts/llm-outputs.md §5)."""
    if judgement.falsifierMet:
        return "exclude", f"Excluded: the falsifier is met. {judgement.reason}".strip()
    if not judgement.fitHolds:
        return "needs_verification", f"Needs verification: the fit is not shown. {judgement.reason}".strip()
    if not passing_evidence_ids:
        return "needs_verification", "Needs verification: no passing evidence documents back an include."
    return "include", f"Included: every rule passed. {judgement.reason}".strip()


def passing_evidence_ids(record: Doc, evidence_by_id: dict[str, Doc]) -> list[str]:
    """The record's origin citation and its own evidence documents that passed their checks."""
    ids = []
    origin_id = (record.get("origin") or {}).get("listingEvidenceId")
    if origin_id and _passed(evidence_by_id.get(origin_id)):
        ids.append(origin_id)
    ids += sorted(
        evidence_id
        for evidence_id, evidence in evidence_by_id.items()
        if evidence.get("companyRecordId") == record["companyRecordId"] and _passed(evidence)
    )
    return ids


def review(ctx: Context, run_id: str) -> CommandResult:
    run = require_run(ctx.store, run_id, "verified")
    if ctx.store.list_review_decisions(run_id):
        raise PreconditionError(f"run {run_id} already has review decisions; Review runs once per run")
    return run_step(ctx, run_id, STEP, lambda: _review(ctx, run))


def _review(ctx: Context, run: Doc) -> CommandResult:
    store, run_id = ctx.store, run["runId"]
    model = ctx.llm.model or run.get("model") or "unknown-model"
    reviewer = f"market-manager/{RULES_VERSION}+{model}"
    evidence_by_id = {e["evidenceId"]: e for e in store.list_evidence(run_id)}
    counts: Counter[str] = Counter()
    baseline_companies = []

    for record in store.list_company_records(run_id):
        record_id = record["companyRecordId"]
        gate = rule_gate(record, evidence_by_id)
        passing = passing_evidence_ids(record, evidence_by_id)
        judgement_doc: dict[str, Any] | None = None
        if gate.disposition is not None:
            disposition, reason = gate.disposition, gate.reason
        else:
            counts["judgementCalls"] += 1
            payload = {
                "position": run["position"],
                "company": record["name"],
                "falsifier": record.get("falsifier"),
                "evidence": [
                    {k: evidence_by_id[i][k] for k in ("evidenceId", "claimField", "claimValue", "excerpt", "url")}
                    for i in passing
                ],
            }
            try:
                judgement = ctx.llm.parse(
                    ReviewJudgement,
                    prompts.messages(prompts.REVIEW_JUDGEMENT, payload),
                    record_id,
                    prompts.REVIEW_JUDGEMENT,
                    run_id=run_id,
                    step=STEP,
                    company_record_id=record_id,
                )
            except LLMSchemaError:
                disposition, reason = "needs_verification", "Needs verification: the judgement call failed twice."
            else:
                disposition, reason = judged_disposition(judgement, passing)
                judgement_doc = {**judgement.model_dump(), "model": model}

        decision = ReviewDecision.model_validate(
            {
                "companyRecordId": record_id,
                "disposition": disposition,
                "reason": reason,
                "ruleResults": gate.rule_results,
                "judgement": judgement_doc,
                "evidenceIds": passing,
                "reviewer": reviewer,
                "reviewedAt": ctx.now_iso(),
            }
        )
        store.create_review_decision(record_id, decision.model_dump())
        counts[disposition] += 1
        baseline_companies.append(
            {
                "companyRecordId": record_id,
                "name": record["name"],
                "domain": record["domain"],
                "disposition": disposition,
            }
        )

    baseline = PositionBaseline.model_validate(
        {
            "runId": run_id,
            "programId": run["programId"],
            "candidateId": run["candidateId"],
            "position": run["position"],
            "constraintsInForce": run["constraintsInForce"],
            "companies": baseline_companies,
            "baselineAt": ctx.now_iso(),
        }
    )
    store.create_position_baseline(run_id, baseline.model_dump())

    store.transition_run(
        run_id,
        "verified",
        "reviewed",
        {"stepTimes": {**(run.get("stepTimes") or {}), "reviewedAt": ctx.now_iso()}},
    )
    step_counts = {
        "reviewed": len(baseline_companies),
        "include": counts["include"],
        "exclude": counts["exclude"],
        "needsVerification": counts["needs_verification"],
        "judgementCalls": counts["judgementCalls"],
    }
    ctx.log.step_end(run_id, STEP, step_counts)
    return CommandResult(
        STEP,
        message=(
            f"run {run_id}: {counts['include']} included, {counts['exclude']} excluded, "
            f"{counts['needs_verification']} need verification"
        ),
        runId=run_id,
        status="reviewed",
        counts={
            "returned": len(baseline_companies),
            "included": counts["include"],
            "excluded": counts["exclude"],
            "needsVerification": counts["needs_verification"],
        },
    )
