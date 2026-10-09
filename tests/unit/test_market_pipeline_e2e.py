"""The whole market pipeline, start to report, against MemoryStore.

The model and search are scripted, and feature 002's discover/verify/review are replaced by fakes that
write the same kinds of records (company records, evidence, review decisions), so the test checks the
market side: objective PDF, vichara proposals, graph, beam, child runs, real company mapping, buyer
roles, decisions, report, and the viewer shapes.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pytest

from hipstraw_mm.adapters.search import SearchResult
from hipstraw_mm.cli import MARKET_HANDLERS
from hipstraw_mm.config import load_config
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.logging_setup import EventLog
from hipstraw_mm.market import schemas, stages
from hipstraw_mm.steps.intake import intake
from hipstraw_mm.store.memory import MemoryStore
from hipstraw_mm.viewer import api

CONFIG_DIR = Path("config")
BAD_DIMENSION = "market_scope"
SILENT_DIMENSION = "economics"
PDF_PHRASE = "Mid market finance teams reconcile vendor invoices by hand"


def make_pdf(text: str) -> bytes:
    """A one-page PDF whose page shows `text` in Helvetica (enough for pypdf to extract)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


class ScriptedLLM:
    """Answers each schema from the prompt payload, like a well-behaved model would."""

    model = "gpt-4o"

    def __init__(self) -> None:
        self.calls = 0
        self.keys: list[str] = []
        self.payloads: dict[str, dict[str, Any]] = {}
        self.last_usage = {"inputTokens": 1000, "outputTokens": 200}

    def parse(self, schema: Any, messages: list[dict[str, str]], match_key: str, prompt_version: str, **_: Any) -> Any:
        self.calls += 1
        self.keys.append(match_key)
        payload = json.loads(messages[1]["content"])
        self.payloads[match_key] = payload
        handler = "_" + re.sub(r"(?<!^)(?=[A-Z])", "_", schema.__name__).lower()
        return getattr(self, handler)(payload)

    def _dimension_deliberation(self, p: dict[str, Any]) -> Any:
        if p["dimensionKey"] == SILENT_DIMENSION:
            item = schemas.DeliberationItem(question="q", status="unresolved", reason="no information in the objective")
        else:
            basis = "text that is not in the objective" if p["dimensionKey"] == BAD_DIMENSION else PDF_PHRASE
            item = schemas.DeliberationItem(question="q", status="answered", answer="a", basis=[basis])
        return schemas.DimensionDeliberation(dimensionKey=p["dimensionKey"], items=[item])

    def _dimension_repair(self, p: dict[str, Any]) -> Any:
        return schemas.DimensionRepair(dimensions=[
            schemas.DimensionRepairEntry(
                dimensionKey=f["dimensionKey"],
                items=[schemas.DeliberationItem(question="q", status="answered", answer="a", basis=[PDF_PHRASE])],
            )
            for f in p["failingDimensions"]
        ])

    def _coverage_judgement(self, p: dict[str, Any]) -> Any:
        return schemas.CoverageJudgement(dimensions=[
            schemas.CoverageDimension(dimensionKey=d["dimensionKey"], addressesDimension=True, reason="ok")
            for d in p["dimensions"]
        ])

    def _vichara_proposals(self, p: dict[str, Any]) -> Any:
        return schemas.VicharaProposals(dimensions=[
            schemas.ProposedDimension(dimensionKey=d["dimensionKey"], items=[schemas.ProposedItem(
                question=d["question"], answer="Mid-market firms recover 1-2% of vendor spend",
                rationale="typical leakage rates", confidence=0.4,
            )])
            for d in p["dimensions"]
        ])

    def _graph_level_proposal(self, p: dict[str, Any]) -> Any:
        level = p["level"]
        allowed = p.get("allowedParentLabels", [])
        nodes = [
            schemas.GraphNode(
                label=f"{level} {i}",
                description=f"{level} node {i}",
                parentLabels=[allowed[i]] if allowed else [],
                metroIds=p["metros"][:1] if level == "segment" else [],
                sizeBand="small" if level == "archetype" else None,
            )
            for i in range(2)
        ]
        if level == "archetype":
            nodes.append(schemas.GraphNode(
                label="big co", description="enterprise", parentLabels=[allowed[0]], sizeBand="enterprise"
            ))
        return schemas.GraphLevelProposal(level=level, nodes=nodes)

    def _link_verification(self, p: dict[str, Any]) -> Any:
        return schemas.LinkVerification(links=[
            schemas.LinkEntry(
                fromNodeId=link["fromNodeId"], toNodeId=link["toNodeId"], rationale="holds",
                linkConfidence=0.3 if link["toLabel"] == "useCase 1" else 0.9,
            )
            for link in p["links"]
        ])

    def _beam_scoring(self, p: dict[str, Any]) -> Any:
        def factor(v: float) -> schemas.ScoredFactor:
            return schemas.ScoredFactor(value=v, rationale="r")

        return schemas.BeamScoring(candidates=[
            schemas.BeamCandidateScore(
                pathId=c["pathId"], relevance=factor(0.9 - 0.1 * i), feasibility=factor(0.6),
                timing=factor(0.5), cost=factor(0.7),
            )
            for i, c in enumerate(p["candidates"])
        ])

    def _path_assessment(self, p: dict[str, Any]) -> Any:
        return schemas.PathAssessment(dimensions=[
            schemas.DimensionAssessment(dimensionKey=k, state=states[0], rationale="r", label="hypothesis")
            for k, states in p["allowedStates"].items()
        ])

    def _buyer_roles(self, p: dict[str, Any]) -> Any:
        roles = []
        for c in p["companies"]:
            if c["evidence"]:
                roles.append(schemas.BuyerRole(
                    pathId=p["pathId"], role="Accounts Payable", authority="approves",
                    evidenceIds=[c["evidence"][0]["evidenceId"]], rationale="the careers page names AP",
                ))
        return schemas.BuyerRoles(roles=roles)


class ScriptedSearch:
    calls = 0

    def search(self, query: str, count: int) -> list[SearchResult]:
        self.calls += 1
        return []


# Feature 002's three steps, faked: same records and transitions, no web access.
COMPANIES = {  # child run suffix -> [(name, domain, disposition)]
    "_p1": [("Acme Ledger", "acme-ledger.com", "include"), ("Brightbooks", "brightbooks.io", "needs_verification"),
            ("Megacorp", "megacorp.com", "exclude")],
    "_p2": [("Acme Ledger", "acme-ledger.com", "needs_verification"), ("Clearpay", "clearpay.co", "include")],
}


def _disposition(child_id: str, record_id: str) -> str:
    return next(d for _, dom, d in COMPANIES[child_id[child_id.rindex("_"):]] if record_id.endswith(dom))


def fake_discover(ctx: Context, child_id: str) -> CommandResult:
    for name, domain, _ in COMPANIES.get(child_id[child_id.rindex("_"):], []):
        ctx.store.upsert_company_record(f"{child_id}__{domain}", {
            "companyRecordId": f"{child_id}__{domain}", "runId": child_id, "candidateId": "c", "name": name,
            "domain": domain, "origin": {"kind": "listing_link", "resultUrl": f"https://list.test/{domain}"},
            "unknowns": [], "confidence": None,
        })
    ctx.store.transition_run(child_id, "created", "discovered")
    return CommandResult("discover", message="found", runId=child_id, counts={"returned": 2})


def fake_verify(ctx: Context, child_id: str) -> CommandResult:
    for rec in ctx.store.list_company_records(child_id):
        rid = rec["companyRecordId"]
        disposition = _disposition(child_id, rid)
        for i, claim in enumerate(("existence", "hq", "signal_pain")):
            ctx.store.create_evidence({
                "evidenceId": f"ev_{rid}_{i}", "runId": child_id, "companyRecordId": rid, "claimField": claim,
                "claimValue": "Atlanta, GA" if claim == "hq" else "yes", "url": f"https://{rec['domain']}/",
                "excerpt": f"{rec['name']} {claim} excerpt", "check": {"status": "pass"},
            })
        rec.update({
            "hq": {"city": "Atlanta", "state": "GA", "status": "met"},
            "size": {"status": "under" if disposition != "exclude" else "over"},
            "confidence": {"value": 0.85 if disposition == "include" else 0.55, "band": "High"},
            "unknowns": [] if disposition == "include" else [{"field": "interestSignal", "reason": "none cited"}],
        })
        ctx.store.upsert_company_record(rid, rec)
    ctx.store.transition_run(child_id, "discovered", "verified", {"counts": {"fetches": 7}})
    return CommandResult("verify", message="verified", runId=child_id)


def fake_review(ctx: Context, child_id: str) -> CommandResult:
    for rec in ctx.store.list_company_records(child_id):
        rid = rec["companyRecordId"]
        disposition = _disposition(child_id, rid)
        signal = {"include": "pass", "needs_verification": "unknown", "exclude": "pass"}[disposition]
        ctx.store.create_review_decision(rid, {
            "companyRecordId": rid, "disposition": disposition, "reason": f"{disposition} reason",
            "ruleResults": [
                {"rule": "existence", "outcome": "pass"}, {"rule": "hq", "outcome": "pass"},
                {"rule": "size", "outcome": "fail" if disposition == "exclude" else "pass"},
                {"rule": "large_enterprise", "outcome": "pass"},
                {"rule": "interest_signal", "outcome": signal},
            ],
            "evidenceIds": [f"ev_{rid}_{i}" for i in range(3)], "reviewer": "test", "reviewedAt": "now",
        })
    ctx.store.transition_run(child_id, "verified", "reviewed")
    return CommandResult("review", message="reviewed", runId=child_id)


def _context(tmp_path: Path) -> Context:
    return Context(
        config=load_config(CONFIG_DIR),
        store=MemoryStore(),
        log=EventLog(runs_dir=tmp_path / ".runs", stream=None),
        llm=ScriptedLLM(),  # type: ignore[arg-type]
        search=ScriptedSearch(),  # type: ignore[arg-type]
        new_fetcher=lambda: None,  # type: ignore[arg-type, return-value]
    )


def _run(ctx: Context, pdfs: list[str]) -> str:
    intake(ctx, "invoice_alpha")
    args = argparse.Namespace(
        program="invoice_alpha_genesis", config_dir=str(CONFIG_DIR), serve=False, port=0, objective_pdf=pdfs
    )
    return str(MARKET_HANDLERS["run"](ctx, args).runId)


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(stages, "_child_steps", lambda: (
        ("discover_companies", "search_research", "company_search", "discover_companies", fake_discover),
        ("verify_companies", "search_research", "company_search", "discover_companies", fake_verify),
        ("review_companies", "market_manager", "review", "record_disposition", fake_review),
    ))
    pdf = tmp_path / "objective.pdf"
    pdf.write_bytes(make_pdf(PDF_PHRASE))
    ctx = _context(tmp_path)
    run_id = _run(ctx, [str(pdf)])
    yield ctx, run_id
    Path("reports", f"{run_id}.md").unlink(missing_ok=True)


def test_run_reaches_reported_and_progresses(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    run = ctx.store.get_market_run(run_id)
    assert run is not None
    assert run["status"] == "reported"
    assert run["marketStatus"]["state"] == "progressing"
    assert run["counts"]["modelCalls"] == ctx.llm.calls
    assert run["counts"]["fetches"] == 14


def test_objective_pdf_reaches_vichara(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    docs = ctx.store.list_objective_documents(run_id)
    assert [d["fileName"] for d in docs] == ["objective.pdf"]
    assert PDF_PHRASE in docs[0]["pages"][0]
    assert PDF_PHRASE in ctx.llm.payloads["vichara:segment_fit"]["objectiveText"]  # type: ignore[attr-defined]


def test_vichara_repairs_then_proposes_labelled_hypotheses(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    llm: Any = ctx.llm
    by_key = {d["dimensionKey"]: d for d in ctx.store.list_deliberations(run_id)}
    assert "vichara_repair:1" in llm.keys
    assert by_key[BAD_DIMENSION]["items"][0]["status"] == "answered"
    proposed = [i for i in by_key[SILENT_DIMENSION]["items"] if i["status"] == "proposed"]
    assert proposed and proposed[0]["label"] == "hypothesis" and proposed[0]["source"] == "model"
    asked = {d["dimensionKey"] for d in llm.payloads["vichara_propose"]["dimensions"]}
    assert SILENT_DIMENSION in asked and "trajectory" not in asked and "evidence_quality" not in asked
    run = ctx.store.get_market_run(run_id)
    reasons = [u["reason"] for u in run["unresolved"] if u["ref"] == SILENT_DIMENSION]
    assert reasons and "model-proposed" in reasons[0]


def test_graph_is_valid_and_filtered(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    graph = ctx.store.list_seed_graphs(run_id)[0]
    assert {n["level"] for n in graph["nodes"]} == set(schemas.GRAPH_LEVELS)
    assert "big co" not in {n["label"] for n in graph["nodes"]}
    assert ctx.llm.payloads["graph:segment:1"]["minNodes"] == 4  # type: ignore[attr-defined]


def test_each_final_path_gets_a_feature_002_child_run(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    finals = [p for p in ctx.store.list_paths(run_id) if p["isFinal"]]
    assert [p["childRunId"] for p in finals] == [f"{run_id}_p1", f"{run_id}_p2"]
    for p in finals:
        child = ctx.store.get_run(p["childRunId"])
        assert child["parentMarketRunId"] == run_id and child["pathId"] == p["pathId"]
        assert child["budgets"]["companiesKept"] == 5
        assert child["position"]["buyer"].startswith("buyerRole")
        candidate = ctx.store.get_candidate(child["candidateId"])
        assert candidate["origin"] == "traced_path" and candidate["experimentContextId"] == p["pathId"]


def test_real_companies_are_mapped_with_dispositions(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    companies = {c["name"]: c for c in ctx.store.list_market_companies(run_id)}
    assert set(companies) == {"Acme Ledger", "Brightbooks", "Megacorp", "Clearpay"}
    acme = companies["Acme Ledger"]
    assert acme["conflict"] is True
    assert {link["disposition"] for link in acme["links"]} == {"include", "needs_verification"}
    assert acme["hq"]["city"] == "Atlanta" and acme["url"] == "https://acme-ledger.com"
    p1 = next(p for p in ctx.store.list_paths(run_id) if p.get("childRunId") == f"{run_id}_p1")
    assert p1["status"] == "has_evidence"
    assert p1["evidenceStates"]["sufficiency"] == "sufficient"
    assert p1["researchPacket"]["included"] == 1 and p1["researchPacket"]["excluded"] == 1


def test_decisions_pursue_paths_with_included_companies(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    assert {d["decision"] for d in ctx.store.list_path_decisions(run_id)} == {"pursue"}


def test_buyer_roles_cite_the_company_own_evidence(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    docs = ctx.store.list_buyer_roles(run_id)
    assert docs and all("megacorp" not in d["domainKey"] for d in docs)
    for d in docs:
        for role in d["roles"]:
            assert all(e.startswith(f"ev_{d['companyRecordId']}") for e in role["evidenceIds"])
            assert set(role).isdisjoint({"name", "email", "phone"})


def test_report_names_target_companies(pipeline: tuple[Context, str]) -> None:
    _, run_id = pipeline
    report = Path("reports", f"{run_id}.md").read_text(encoding="utf-8")
    assert "## Target Companies by Path" in report
    assert "**Acme Ledger** (acme-ledger.com), Atlanta, GA" in report
    assert "Clearpay" in report


def test_every_model_call_is_traced_with_blobs(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    steps = ctx.store.list_trace_steps_after(run_id, 0)
    assert [s["seq"] for s in steps] == list(range(1, len(steps) + 1))
    assert all(s["status"] == "ok" for s in steps)
    model_steps = [s for s in steps if s["operation"] == "call_model"]
    assert len(model_steps) == ctx.llm.calls
    for s in model_steps:
        assert s["parentStepId"] is not None
        assert ctx.store.get_trace_blob(s["promptBlobId"]) is not None
        assert s["cost"]["usd"] == pytest.approx(0.0045)
    ops = {s["operation"] for s in steps}
    assert {"ingest_objective", "propose_hypotheses", "discover_companies", "review_companies"} <= ops


def test_viewer_shapes_read_the_run(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    assert api.shape_documents(ctx.store, run_id)[0]["excerpt"].startswith(PDF_PHRASE)
    assert any(c["buyerRoles"] for c in api.shape_companies(ctx.store, run_id))
    assert api.shape_decisions(ctx.store, run_id)["marketStatus"]["state"] == "progressing"


def test_a_failed_child_run_is_recorded_not_fatal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def broken_discover(ctx: Context, child_id: str) -> CommandResult:
        raise RuntimeError("search provider down")

    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(stages, "_child_steps", lambda: (
        ("discover_companies", "search_research", "company_search", "discover_companies", broken_discover),
    ))
    ctx = _context(tmp_path)
    run_id = _run(ctx, [])
    Path("reports", f"{run_id}.md").unlink(missing_ok=True)
    run = ctx.store.get_market_run(run_id)
    assert run["status"] == "reported"
    assert run["marketStatus"]["state"] == "awaiting-evidence"
    failed = [u for u in run["unresolved"] if u["kind"] == "company_research"]
    assert failed and "search provider down" in failed[0]["reason"]
