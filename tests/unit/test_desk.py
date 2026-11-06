"""The reviewer desk (Nov 6 meeting): a request becomes a case; the agent works it through ingest, review,
position, recommend and workflow with rules only; a reviewer approves the plan, bound to its payload hash. Each
step is one transaction on an append-only, hash-chained ledger; the API and CLI call the same operations."""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hipstraw_mm import cli
from hipstraw_mm.desk.api import create_app
from hipstraw_mm.desk.service import AuthorityError, Desk, StaleError
from hipstraw_mm.desk.store import DeskStore
from hipstraw_mm.errors import UsageError
from hipstraw_mm.foundry.walkthrough import load_thesis

THESES = Path("input/demand/theses")
ZIMPLII = THESES / "zimplii_technical_assurance.yaml"
REVIEWER = {"X-Hipstraw-Actor": "Desk reviewer", "X-Hipstraw-Role": "reviewer"}
CUSTOMER = {"X-Hipstraw-Actor": "Zimplii founder", "X-Hipstraw-Role": "customer"}
REQUEST: dict[str, Any] = {
    "product": "Acme Books", "market": "Bookkeeping for dental practices", "geography": "Texas",
    "statement": "Dental practices lose hours to bookkeeping and would pay for it done for them.",
    "buyer": "b2b", "motion": "sales_led",
    "hypotheses": [{"name": "Monthly bookkeeping", "demand": "Practice owners will pay monthly for bookkeeping",
                    "segment": "Independent dental practices, 1-5 dentists", "offering": "Managed bookkeeping",
                    "recurring": True, "priceFloor": {"amount": 400, "currency": "USD", "per": "month"},
                    "triggers": ["tax season", "a new practice manager"], "buyerRole": "the practice owner"}],
}


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return Desk(DeskStore(tmp_path / "desk.db"))


def test_the_agent_works_a_request_through_the_pipeline_with_rules_only(desk: Desk) -> None:
    case = desk.submit(load_thesis(ZIMPLII, desk.rubric), actor="Zimplii founder", role="customer")
    assert (case.id, case.state, case.waitingOn) == ("HS-1001", "agent_working", "agent")
    case = desk.run(case.id)
    assert (case.state, case.waitingOn, case.stage) == ("waiting_review", "reviewer", "approval")
    events = desk.store.events(case.id)
    assert [e.stage for e in events][:2] == ["ingest", "ingest"] and events[0].kind == "request"
    stages = [e.stage for e in events]
    assert stages == sorted(stages, key=["ingest", "review", "position", "recommend", "workflow", "approval"].index)
    picks = [e.title for e in events if e.kind == "pick"]
    assert len(picks) == 12 and "H2 · T2 Test purchase → LD3 Shadow offer" in picks
    assert "LD2 Paid pilot: not eligible, motion is self_serve, needs sales_led" in next(
        e.detail for e in events if e.title.startswith("H2 · T2"))
    assert any("Jev" in e.detail for e in events if e.title == "Opened the playbook")
    assert events[-1].kind == "gate" and events[-1].data["payloadHash"] == case.payloadHash
    assert case.recommendation and case.recommendation["hypotheses"][0]["tasks"][1]["lineId"] == "LD2"


def test_approval_is_bound_to_the_plan_and_to_the_reviewer_role(desk: Desk) -> None:
    case = desk.run(desk.submit(load_thesis(ZIMPLII, desk.rubric), actor="c", role="customer").id)
    assert case.payloadHash
    with pytest.raises(AuthorityError, match="'customer' may not approve plan"):
        desk.decide(case.id, action="approve", payload_hash=case.payloadHash, actor="c", role="customer")
    with pytest.raises(AuthorityError):
        desk.decide(case.id, action="approve", payload_hash=case.payloadHash, actor="x", role="")
    with pytest.raises(StaleError, match="the plan changed"):
        desk.decide(case.id, action="approve", payload_hash="0" * 64, actor="r", role="reviewer")
    with pytest.raises(UsageError, match="needs a note"):
        desk.decide(case.id, action="return", payload_hash=case.payloadHash, actor="r", role="reviewer")
    done = desk.decide(case.id, action="approve", payload_hash=case.payloadHash, actor="r", role="reviewer",
                       note="Start with the account map")
    assert (done.state, done.waitingOn) == ("approved", "people") and done.approval
    assert done.approval.payloadHash == case.payloadHash
    with pytest.raises(StaleError, match="not waiting for review"):
        desk.decide(case.id, action="approve", payload_hash=case.payloadHash, actor="r", role="reviewer")
    assert desk.store.events(case.id)[-1].kind == "decision"


def test_the_ledger_is_append_only_and_its_chain_verifies(desk: Desk, tmp_path: Path) -> None:
    desk.seed(THESES)
    result = desk.store.verify()
    assert result["ok"] and result["checked"] == len(desk.store.events()) > 40
    conn = sqlite3.connect(tmp_path / "desk.db")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE events SET doc = '{}' WHERE seq = 3")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM events WHERE seq = 3")
    conn.execute("DROP TRIGGER events_no_update")  # someone bypasses the guard: the chain still shows it
    conn.execute("UPDATE events SET doc = replace(doc, 'Read the request', 'Read nothing') WHERE seq = 2")
    conn.commit()
    assert desk.store.verify() == {**desk.store.verify(), "ok": False, "brokenAt": 2}


def test_seeding_opens_each_thesis_once(desk: Desk) -> None:
    assert len(desk.seed(THESES)) == 2 and desk.seed(THESES) == []
    assert {c.company for c in desk.store.cases()} == {"Zimplii", "Hipstraw"}


@pytest.mark.api
def test_the_api_runs_a_customer_request_and_takes_the_reviewers_decision(tmp_path: Path) -> None:
    desk = Desk(DeskStore(tmp_path / "desk.db"))
    with TestClient(create_app(desk)) as client:  # seeds the sample requests
        assert len(client.get("/api/cases").json()) == 2
        assert client.post("/api/requests", json=REQUEST).status_code == 403  # no actor or role
        bad = client.post("/api/requests", json={**REQUEST, "hypotheses": []}, headers=CUSTOMER)
        assert bad.status_code == 422
        made = client.post("/api/requests", json=REQUEST, headers=CUSTOMER)
        assert made.status_code == 201
        case_id = made.json()["id"]
        detail = client.get(f"/api/cases/{case_id}").json()  # the agent ran after the response
        assert detail["case"]["state"] == "waiting_review" and detail["case"]["company"] == "Acme Books"
        assert [s["status"] for s in detail["stages"]] == ["done"] * 5 + ["active"]
        tasks = detail["recommendation"]["hypotheses"][0]["tasks"]
        assert [t["lineId"] for t in tasks] == ["LD1", "LD2", "LD4", "LD5"]
        events = client.get(f"/api/cases/{case_id}/events", params={"after": detail["events"][3]["seq"]}).json()
        assert len(events) == len(detail["events"]) - 4
        payload = detail["payloadHash"]
        assert client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "payloadHash": payload},
                           headers=CUSTOMER).status_code == 403
        assert client.post(f"/api/cases/{case_id}/decision", json={"action": "approve", "payloadHash": "x"},
                           headers=REVIEWER).status_code == 409
        ok = client.post(f"/api/cases/{case_id}/decision",
                         json={"action": "approve", "payloadHash": payload, "note": "go"}, headers=REVIEWER)
        assert ok.status_code == 200 and ok.json()["case"]["state"] == "approved"
        assert ok.json()["stages"][-1]["status"] == "done"
        assert client.get("/api/cases/HS-9999").status_code == 404
        assert client.get("/api/nothing").status_code == 404
        library = client.get("/api/library").json()
        assert [t["lines"] for t in library["tasks"]] == [["LD0", "LD1"], ["LD2", "LD3"], ["LD4"], ["LD5"]]
        ledger = client.get("/api/ledger").json()
        assert ledger["verify"]["ok"] and ledger["events"][0]["kind"] == "decision"
        assert [o["status"] for o in client.get("/api/offerings").json()] == ["live", "preview", "preview"]


def test_cli_submit_list_decide_verify(tmp_path: Path) -> None:
    db = str(tmp_path / "d.db")

    def run(*argv: str) -> dict[str, Any]:
        out = io.StringIO()
        assert cli.main(["desk", *argv, "--db", db, "--json"], stdout=out, stderr=io.StringIO()) == 0
        result: dict[str, Any] = json.loads(out.getvalue())
        return result

    made = run("submit", "--thesis", str(ZIMPLII), "--as", "customer", "--actor", "Zimplii founder")
    assert made["status"] == "waiting_review"
    shown = run("show", made["runId"])
    run("decide", made["runId"], "--action", "approve", "--payload", shown["payloadHash"], "--as", "reviewer",
        "--actor", "Desk reviewer")
    assert run("list")["cases"][0]["state"] == "approved"
    assert run("verify")["status"] == "ok"
