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

        # High enough that the top paths clear the 0.75 search-score threshold.
        return schemas.BeamScoring(candidates=[
            schemas.BeamCandidateScore(
                pathId=c["pathId"], relevance=factor(0.95 - 0.05 * i), feasibility=factor(0.85),
                timing=factor(0.8), cost=factor(0.8),
            )
            for i, c in enumerate(p["candidates"])
        ])

    def _path_assessment(self, p: dict[str, Any]) -> Any:
        return schemas.PathAssessment(dimensions=[
            schemas.DimensionAssessment(dimensionKey=k, state=states[0], rationale="r", label="hypothesis")
            for k, states in p["allowedStates"].items()
        ])

    def _economic_screening(self, p: dict[str, Any]) -> Any:
        return schemas.EconomicScreening(estimates=[
            schemas.EconomicEstimate(
                pathId=c["pathId"], valuePoolUsdLow=1_000_000.0 * (i + 1), valuePoolUsdHigh=3_000_000.0 * (i + 1),
                unit="annual recoverable invoice leakage", targetCompanyEstimate=40 + i,
                assumptions=["40 target companies", "1% leakage"],
                sensitivities=[schemas.Sensitivity(factor="leakage rate", impact="medium")],
                timeToValueMonths=3, rationale="sizing hypothesis",
            )
            for i, c in enumerate(p["candidates"])
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


def fake_verify(ctx: Context, child_id: str, evidence_status: str = "pass") -> CommandResult:
    for rec in ctx.store.list_company_records(child_id):
        rid = rec["companyRecordId"]
        disposition = _disposition(child_id, rid)
        for i, claim in enumerate(("existence", "hq", "signal_pain")):
            ctx.store.create_evidence({
                "evidenceId": f"ev_{rid}_{i}", "runId": child_id, "companyRecordId": rid, "claimField": claim,
                "claimValue": "Atlanta, GA" if claim == "hq" else "yes", "url": f"https://{rec['domain']}/",
                "excerpt": f"{rec['name']} {claim} excerpt", "check": {"status": evidence_status},
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
    assert run["marketStatus"]["state"] == "awaiting-evidence"
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


def test_review_follows_the_playbook_chain(pipeline: tuple[Context, str]) -> None:
    """Desk research leaves MP1 at Hypothesis, so the playbook gives Probe -> S03 -> P04 -> L03 and TEST."""
    ctx, run_id = pipeline
    decisions = ctx.store.list_path_decisions(run_id)
    assert {d["disposition"] for d in decisions} == {"TEST"}
    pos = decisions[0]["marketPosition"]
    assert [a["axis"] for a in pos["axes"]] == ["MP1", "MP2", "MP3", "MP4", "MP5", "MP6", "MP7"]
    assert pos["bindingConstraint"]["axis"] == "MP1" and pos["stance"]["stance"] == "Probe"
    assert (pos["strategy"], pos["play"], pos["line"]["current"]) == ("S03", "P04", "L03")
    assert [s["status"] for s in pos["line"]["steps"]] == ["done", "done", "done", "done", "to do"]
    assert pos["nextStep"]["id"] == "A16" and pos["nextStep"]["allowedInMode"]
    assert pos["gambits"][0]["id"] == "G02" and pos["gambits"][0]["needsStance"] == "Co-create"
    review = next(s for s in ctx.store.list_trace_steps_after(run_id, 0) if s["operation"] == "market_review")
    assert review["decision"] == "TEST"


def test_market_position_is_built_for_each_final_path(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    decisions = ctx.store.list_path_decisions(run_id)
    assert decisions and all("marketPosition" in d for d in decisions)
    pos = decisions[0]["marketPosition"]
    assert pos["disposition"] == "TEST"
    assert pos["pathLabels"] and pos["headline"].startswith("TEST:")
    assert len(pos["narrative"]) == 7
    assert pos["evidence"]["sufficiency"] == "sufficient"
    assert any(c["disposition"] == "include" for c in pos["targetCompanies"])
    # the stored path carries the same position, so the viewer can read it from either place
    path = next(p for p in ctx.store.list_paths(run_id) if p["pathId"] == decisions[0]["pathId"])
    assert path["marketPosition"]["disposition"] == "TEST"


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
    assert "## Target Companies by Market Unit" in report
    assert "**Recommended next step:** A16 Route decision or approval" in report
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
    assert api.shape_decisions(ctx.store, run_id)["marketStatus"]["state"] == "awaiting-evidence"


def test_position_and_evaluation_opens_a_case_per_final_path(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    docs = ctx.store.list_evaluation_cases(run_id)
    cases = [d for d in docs if d["kind"] == "evaluation_case"]
    finals = [p for p in ctx.store.list_paths(run_id) if p["isFinal"]]
    assert len(cases) == len(finals)
    for c in cases:
        assert [h["state"] for h in c["history"]][:3] == ["RECEIVED", "QUEUED", "EVALUATING"]
        assert c["recommendation"]["recommendation"] == "Recommend Transition"
        assert c["recommendation"]["rubric"] == "position_transition.v1"
        assert c["confidence"]["band"] == "Medium" and c["confidence"]["limitingFactors"]
        assert c["economics"]["label"] == "hypothesis"
        assert c["researchRequirements"], "open interest-signal gaps must become research requirements"
    assert any(d["kind"] == "comparison" for d in docs)
    screening = next(d for d in docs if d["kind"] == "economic_screening")
    assert len(screening["estimates"]) >= len(finals)


def test_market_manager_commits_versioned_canonical_positions(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    positions = ctx.store.list_market_positions("invoice_alpha_genesis")
    assert positions and all(p["version"] == 1 and p["trajectory"] == "new" for p in positions)
    assert all(p["recommendationAccepted"] is True for p in positions)
    assert all(p["evidenceLineage"]["evaluationCaseId"].startswith(run_id) for p in positions)
    view = api.shape_positions(ctx.store, run_id)
    assert len(view) == len(positions) and all(v["history"] == [] for v in view)


def test_market_map_has_a_tile_per_screened_micro_market(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    market_map = api.shape_market_map(ctx.store, run_id)
    assert market_map is not None and market_map["tiles"]
    researched = [t for t in market_map["tiles"] if t["researched"]]
    assert len(researched) == len([p for p in ctx.store.list_paths(run_id) if p["isFinal"]])
    assert all(t["position"]["disposition"] == "TEST" and t["valueMid"] for t in researched)
    assert all(t["change"]["direction"] == "new" for t in market_map["tiles"])
    assert {g["group"] for g in market_map["groups"]} == {t["group"] for t in market_map["tiles"]}


def test_every_traced_operation_belongs_to_a_capability_or_skill(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    agents = api.shape_agents(ctx.store, run_id)
    assert agents is not None
    assert agents["unclaimedOperations"] == []
    pe = next(a for a in agents["agents"] if a["id"] == "position_evaluation")
    econ = next(sk for sk in pe["skills"] if sk["id"] == "economic_evaluation")
    assert econ["usage"]["modelCalls"] >= 1
    assert [a["title"] for a in agents["simple"]["agents"]] == [
        "Market Manager", "Market Development", "Research", "Evaluation"]


def test_a_second_run_versions_positions_and_shows_change(pipeline: tuple[Context, str], tmp_path: Path) -> None:
    from datetime import timedelta

    ctx, first = pipeline
    first_time = ctx.now()
    ctx.now = lambda: first_time + timedelta(minutes=5)  # type: ignore[method-assign]
    second = _run(ctx, [])
    Path("reports", f"{second}.md").unlink(missing_ok=True)
    assert second != first
    cases = [d for d in ctx.store.list_evaluation_cases(second) if d["kind"] == "evaluation_case"]
    assert cases and all(c["priorPosition"] and c["recommendation"]["recommendation"] == "Maintain" for c in cases)
    positions = [p for p in ctx.store.list_market_positions("invoice_alpha_genesis") if p["marketRunId"] == second]
    assert positions and all(p["version"] == 2 and p["trajectory"] == "flat" for p in positions)
    market_map = api.shape_market_map(ctx.store, second)
    assert market_map["previousRunId"] == first
    assert all(t["change"]["direction"] in ("flat", "up", "down") for t in market_map["tiles"])
    view = api.shape_positions(ctx.store, second)
    assert all(len(v["history"]) == 1 for v in view)


def test_low_search_scores_are_held_below_the_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every candidate scores well under 0.75, so no path becomes final and the market is blocked."""
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(stages, "_child_steps", lambda: ())

    class LowLLM(ScriptedLLM):
        def _beam_scoring(self, p: dict[str, Any]) -> Any:
            f = schemas.ScoredFactor(value=0.5, rationale="r")
            return schemas.BeamScoring(candidates=[
                schemas.BeamCandidateScore(pathId=c["pathId"], relevance=f, feasibility=f, timing=f, cost=f)
                for c in p["candidates"]
            ])

    ctx = Context(
        config=load_config(CONFIG_DIR), store=MemoryStore(), log=EventLog(runs_dir=tmp_path, stream=None),
        llm=LowLLM(), search=ScriptedSearch(), new_fetcher=lambda: None,  # type: ignore[arg-type, return-value]
    )
    run_id = _run(ctx, [])
    Path("reports", f"{run_id}.md").unlink(missing_ok=True)
    run = ctx.store.get_market_run(run_id)
    assert run["status"] == "reported"
    assert [p for p in ctx.store.list_paths(run_id) if p.get("isFinal")] == []
    assert "75% search-score threshold" in run["finalPathShortfall"]["reason"]
    assert run["marketStatus"]["state"] == "blocked"


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


def test_vichara_dark_routing_keeps_todays_frontier_calls(pipeline: tuple[Context, str]) -> None:
    ctx, run_id = pipeline
    llm: Any = ctx.llm
    from hipstraw_mm.market.grammar import load_grammar

    expected = [f"vichara:{d.key}" for d in load_grammar(CONFIG_DIR).dimensions]
    assert llm.keys[: len(expected)] == expected
    for d in ctx.store.list_deliberations(run_id):
        assert d["deliberatedBy"]["servedBy"] == "frontier" and d["deliberatedBy"]["ruleId"] == "R4"


def test_vichara_open_weight_tier_escalates_only_failing_dimensions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An open-weight tier answers well except on two dimensions: one cites text that is not in the
    objective, one abstains although a PDF is attached. Only those two go to frontier."""
    from hipstraw_mm.market.router import RoutingConfig, load_routing

    raw = load_routing(CONFIG_DIR).model_dump(by_alias=True)
    raw["openWeight"]["enabled"] = True
    monkeypatch.setattr(stages, "load_routing", lambda _dir: RoutingConfig.model_validate(raw))
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(stages, "_child_steps", lambda: ())

    class OpenWeight(ScriptedLLM):
        model = "qwen-test"

        def __init__(self) -> None:
            super().__init__()
            self.last_raw = {"model": "qwen-test-served"}

        def _dimension_deliberation(self, p: dict[str, Any]) -> Any:
            key = p["dimensionKey"]
            if key == SILENT_DIMENSION:
                item = schemas.DeliberationItem(
                    question="q", status="unresolved", reason="no information in the objective"
                )
            else:
                basis = "text that is not in the objective" if key == BAD_DIMENSION else PDF_PHRASE
                item = schemas.DeliberationItem(question="q", status="answered", answer="a", basis=[basis])
            return schemas.DimensionDeliberation(dimensionKey=key, items=[item])

    pdf = tmp_path / "objective.pdf"
    pdf.write_bytes(make_pdf(PDF_PHRASE))
    ctx = _context(tmp_path)
    ow = OpenWeight()
    ctx.open_llm = ow  # type: ignore[assignment]
    run_id = _run(ctx, [str(pdf)])
    Path("reports", f"{run_id}.md").unlink(missing_ok=True)

    llm: Any = ctx.llm
    from hipstraw_mm.market.grammar import load_grammar

    dims = [d.key for d in load_grammar(CONFIG_DIR).dimensions]
    assert [k for k in ow.keys if k.startswith("ow:qwen-test:vichara:")] == [f"ow:qwen-test:vichara:{k}" for k in dims]
    # links go open-weight first too; the scripted one-word reasons ("holds") fail the reason check
    assert "ow:qwen-test:links:0:1" in ow.keys and "links:0:1" in llm.keys
    assert sorted(k for k in llm.keys if k.startswith("vichara:")) == sorted(
        [f"vichara:{BAD_DIMENSION}", f"vichara:{SILENT_DIMENSION}"]
    )
    assert "vichara_coverage" in llm.keys and "vichara_propose" in llm.keys
    by_key = {d["dimensionKey"]: d["deliberatedBy"] for d in ctx.store.list_deliberations(run_id)}
    assert by_key["segment_fit"] == {"routerVersion": "router.v1", "ruleId": "R8",
                                     "servedBy": "open_weight", "model": "qwen-test"}
    assert by_key[BAD_DIMENSION]["servedBy"] == "frontier" and by_key[SILENT_DIMENSION]["servedBy"] == "frontier"
    run = ctx.store.get_market_run(run_id)
    assert run["status"] == "reported"
    assert run["counts"]["modelCalls"] == llm.calls + ow.calls


def test_slice2_routes_links_buyers_and_complex_tasks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """With the open-weight route on: links are kept on open-weight, buyer roles go open-weight where
    there is passing evidence and to the no-evidence rule where there is none, and every complex task
    goes to frontier through the router with its lineage."""
    from hipstraw_mm.market.router import RoutingConfig, load_routing

    raw = load_routing(CONFIG_DIR).model_dump(by_alias=True)
    raw["openWeight"]["enabled"] = True
    monkeypatch.setattr(stages, "load_routing", lambda _dir: RoutingConfig.model_validate(raw))
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")

    def verify_p2_fails(ctx: Context, child_id: str) -> CommandResult:
        return fake_verify(ctx, child_id, "fail" if child_id.endswith("_p2") else "pass")

    monkeypatch.setattr(stages, "_child_steps", lambda: (
        ("discover_companies", "search_research", "company_search", "discover_companies", fake_discover),
        ("verify_companies", "search_research", "company_search", "discover_companies", verify_p2_fails),
        ("review_companies", "market_manager", "review", "record_disposition", fake_review),
    ))

    class OpenWeight(ScriptedLLM):
        model = "qwen-test"

        def __init__(self) -> None:
            super().__init__()
            self.last_raw = {"model": "qwen-test-served"}

        def _link_verification(self, p: dict[str, Any]) -> Any:
            return schemas.LinkVerification(links=[
                schemas.LinkEntry(fromNodeId=x["fromNodeId"], toNodeId=x["toNodeId"],
                                  rationale="the segment has this buyer", linkConfidence=0.8)
                for x in p["links"]
            ])

    pdf = tmp_path / "objective.pdf"
    pdf.write_bytes(make_pdf(PDF_PHRASE))
    ctx = _context(tmp_path)
    ow = OpenWeight()
    ctx.open_llm = ow  # type: ignore[assignment]
    run_id = _run(ctx, [str(pdf)])
    Path("reports", f"{run_id}.md").unlink(missing_ok=True)
    llm: Any = ctx.llm

    assert not [k for k in llm.keys if k.startswith("links:")]
    assert len(ctx.store.list_link_checks(run_id)) == 10

    paths = {p["childRunId"][-3:]: p["pathId"] for p in ctx.store.list_paths(run_id) if p.get("childRunId")}
    assert f"ow:qwen-test:buyers:{paths['_p1']}" in ow.keys and f"buyers:{paths['_p1']}" not in llm.keys
    assert not [k for k in [*ow.keys, *llm.keys] if k.endswith(f"buyers:{paths['_p2']}")]
    p2_roles = [r for r in ctx.store.list_buyer_roles(run_id) if r["pathId"] == paths["_p2"]]
    assert p2_roles and all(r["unknown"]["reason"] == "no stored evidence names a buying function" for r in p2_roles)

    steps = ctx.store.list_trace_steps_after(run_id, 0)
    routing = {(s["operation"], s["inputs"].get("pathId")): s["outputs"]["routing"]
               for s in steps if (s.get("outputs") or {}).get("routing")}
    rule = routing[("identify_buyer_roles", paths["_p2"])]
    assert (rule["route"], rule["ruleId"], rule["servedBy"]) == ("rules", "R2", "rules")
    assert routing[("identify_buyer_roles", paths["_p1"])]["servedBy"] == "open_weight"
    for op in ("build_level", "score_candidates", "assess_path", "screen_economics"):
        found = [r for (o, _), r in routing.items() if o == op]
        assert found and all((r["ruleId"], r["servedBy"]) == ("R3", "frontier") for r in found), op

    from hipstraw_mm.market.routing_report import build_simulation

    sim = build_simulation(ctx.store, run_id, CONFIG_DIR)
    assert sim is not None
    by_stage = sim["summary"]["byStage"]
    assert set(by_stage) == {"vichara", "graph", "links", "beam", "assess", "buyers", "evaluate"}
    assert by_stage["buyers"] == {"kept": 1, "rules": 1} and sim["summary"]["byRules"] == 1
    ruled = [e for e in sim["walkthrough"] if e["router"] and e["router"]["route"] == "rules"]
    assert [e["rule"] for e in ruled] == ["no_passing_evidence"] and ruled[0]["attempts"] == []

    run = ctx.store.get_market_run(run_id)
    assert run["status"] == "reported"
    assert run["counts"]["modelCalls"] == llm.calls + ow.calls
