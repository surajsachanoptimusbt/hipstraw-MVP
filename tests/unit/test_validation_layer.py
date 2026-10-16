"""The validation layer: a rubric that matches the checks the code runs, and a log that explains every
failure (which quote, the closest passage in the objective, where it differs, which characters)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from hipstraw_mm.market.router import TaskRouter
from hipstraw_mm.market.schemas import DeliberationItem, DimensionDeliberation
from hipstraw_mm.market.validation_rubric import load_validation_rubric
from hipstraw_mm.market.vichara import explain_grounding_miss, vichara_checks
from tests.unit.test_task_router import OBJECTIVE, Ctx, FakeTier, _config, _deliberate, tracer_store  # noqa: F401

DOC = "[Document: kozmo.pdf]\nFinance teams reconcile vendor invoices by hand every month and lose $40M$50M ARR."
TEXT = "Objective: find mid market finance teams\n" + DOC


def _answer(*bases: str, key: str = "economics") -> DimensionDeliberation:
    return DimensionDeliberation(dimensionKey=key, items=[
        DeliberationItem(question="q", status="answered", answer="a", basis=list(bases))])


# --------------------------------------------------------------------------------------------------
# rubric
# --------------------------------------------------------------------------------------------------


def test_rubric_lists_exactly_the_checks_the_code_runs() -> None:
    rubric = load_validation_rubric()
    assert rubric.version == "validation.v1" and rubric.task == "vichara.v1"
    ids = {c.id for c in rubric.checks}
    assert ids == {"schema", "echo_key", "grounding", "abstention"}
    silent = DimensionDeliberation(dimensionKey="economics", items=[
        DeliberationItem(question="q", status="unresolved", reason="no information in the objective")])
    for tier in ("open_weight", "frontier"):
        emitted = {c.name for c in vichara_checks(silent, tier, dimension_key="economics", objective_text=TEXT,
                                                  max_items=3, has_documents=True)}
        expected = {c.id for c in rubric.checks if tier in c.tiers and c.id != "schema"}
        assert emitted == expected, tier
    assert set(rubric.groundingVerdicts) == {"near_miss", "partial", "not_found"}
    assert all(c.question.endswith("?") and c.method and c.passWhen and c.onFail for c in rubric.checks)


# --------------------------------------------------------------------------------------------------
# grounding diagnosis
# --------------------------------------------------------------------------------------------------


def test_near_miss_names_the_pdf_character() -> None:
    d = explain_grounding_miss("lose $40M-$50M ARR", TEXT)
    assert d["verdict"] == "near_miss"
    assert d["matchedWords"] == d["quoteWords"] == 3
    assert d["location"] == "kozmo.pdf"
    chars = d["characters"]
    assert chars and chars[0]["code"] == "U+E088" and "private-use" in chars[0]["kind"]
    assert "" in d["closest"]
    assert d["differs"]["kind"] == "characters" and d["differs"]["document"] == "$40M$50M"


def test_a_dropped_word_is_reported_where_it_happens() -> None:
    d = explain_grounding_miss("Finance teams reconcile invoices by hand every month", TEXT)
    assert d["verdict"] == "partial"
    assert d["differs"]["kind"] == "only in document" and d["differs"]["document"] == "vendor"
    assert d["differs"]["position"] == 4


def test_ascii_punctuation_near_miss_names_the_word() -> None:
    d = explain_grounding_miss("every month and lose", TEXT.replace("month and", "month, and"))
    assert d["verdict"] == "near_miss" and d["characters"] == []
    assert d["differs"]["document"] == "month," and "'month,'" in d["explanation"]


def test_partial_shows_the_first_word_that_differs() -> None:
    d = explain_grounding_miss("Finance teams reconcile vendor invoices automatically", TEXT)
    assert d["verdict"] == "partial"
    assert (d["matchedWords"], d["quoteWords"]) == (5, 6)
    assert {k: d["differs"][k] for k in ("position", "kind", "quote", "document")} == {
        "position": 6, "kind": "replaced", "quote": "automatically", "document": "by"}
    assert d["differs"]["passageWord"] == 6
    assert d["closest"].startswith("Finance teams reconcile vendor invoices")


def test_not_found_says_the_quote_is_not_in_the_text() -> None:
    d = explain_grounding_miss("the moon is made of green cheese", TEXT)
    assert d["verdict"] == "not_found"
    assert d["matchedWords"] <= 1


def test_location_can_be_the_program_objective() -> None:
    d = explain_grounding_miss("find mid market finance managers", TEXT)
    assert d["location"] == "program objective"


# --------------------------------------------------------------------------------------------------
# per-check details
# --------------------------------------------------------------------------------------------------


def test_grounding_details_list_every_quote() -> None:
    checks = {c.name: c for c in vichara_checks(
        _answer("reconcile vendor invoices by hand", "a sentence nobody wrote"), "open_weight",
        dimension_key="economics", objective_text=TEXT, max_items=3, has_documents=True)}
    g = checks["grounding"].details
    assert (g["checked"], g["failed"]) == (2, 1)
    found, missing = g["quotes"]
    assert found["found"] is True and "diagnosis" not in found
    assert missing["found"] is False and missing["diagnosis"]["verdict"] == "not_found"
    assert checks["echo_key"].details == {"asked": "economics", "answered": "economics"}


def test_echo_and_abstention_details() -> None:
    silent = DimensionDeliberation(dimensionKey="timing", items=[
        DeliberationItem(question="q", status="unresolved", reason="no information in the objective")])
    checks = {c.name: c for c in vichara_checks(silent, "open_weight", dimension_key="economics",
                                                objective_text=TEXT, max_items=3, has_documents=True)}
    assert checks["echo_key"].details == {"asked": "economics", "answered": "timing"}
    a = checks["abstention"].details
    assert a == {"documentsAttached": True, "itemsKept": 1, "unresolved": 1,
                 "reasons": ["no information in the objective"]}


# --------------------------------------------------------------------------------------------------
# the router keeps the whole log
# --------------------------------------------------------------------------------------------------


def test_router_saves_the_validation_log_for_both_tiers(tracer_store: Any) -> None:  # noqa: F811
    tracer, _ = tracer_store
    router = TaskRouter(Ctx(FakeTier("gpt-4o"), FakeTier("qwen-test", {"segment_fit": "bad_basis"})),
                        tracer, _config(), run_id="mrun_t")
    _, routing = _deliberate(router, tracer, "segment_fit")
    ow = {c["id"]: c for c in routing["validation"]["open_weight"]}
    assert ow["schema"]["passed"] is True
    assert ow["grounding"]["passed"] is False and ow["grounding"]["blocking"] is True
    assert ow["grounding"]["details"]["quotes"][0]["quote"] == "a sentence the objective never says"
    fr = {c["id"]: c for c in routing["validation"]["frontier"]}
    assert fr["grounding"]["passed"] is True and "abstention" not in fr
    json.dumps(routing)


def test_schema_failure_is_logged_with_its_reason(tracer_store: Any) -> None:  # noqa: F811
    tracer, _ = tracer_store
    router = TaskRouter(Ctx(FakeTier("gpt-4o"), FakeTier("qwen-test", {"segment_fit": "schema_error"})),
                        tracer, _config(), run_id="mrun_t")
    _, routing = _deliberate(router, tracer, "segment_fit")
    schema = routing["validation"]["open_weight"][0]
    assert schema["id"] == "schema" and schema["passed"] is False
    assert "schema validation failed" in schema["reason"]


def test_schema_error_message_names_the_fields(tmp_path: Any) -> None:
    from hipstraw_mm.adapters.llm import LLMClient, LLMSchemaError
    from hipstraw_mm.adapters.replay import ReplayStore

    client = LLMClient(model="m", replay=ReplayStore(tmp_path, mode="record"), schema_attempts=1)
    bad = {"content": json.dumps({"dimensionKey": "x", "items": [{"question": "q", "status": "answered"}]}),
           "model": "m"}
    client._live = lambda schema, messages: bad  # type: ignore[method-assign]
    with pytest.raises(LLMSchemaError, match="items.0"):
        client.parse(DimensionDeliberation, [{"role": "user", "content": "x"}], "k", "vichara.v1")


def test_existing_quote_check_is_unchanged() -> None:
    """Diagnosis explains a failure; it never turns one into a pass."""
    checks = {c.name: c for c in vichara_checks(_answer("lose $40M-$50M ARR"), "open_weight",
                                                dimension_key="economics", objective_text=TEXT,
                                                max_items=3, has_documents=True)}
    assert checks["grounding"].passed is False
    assert checks["grounding"].details["quotes"][0]["diagnosis"]["verdict"] == "near_miss"
    assert OBJECTIVE
