"""T007 role checks and T038 effect-class gate (HA C7): fails closed, every decision traced."""

from __future__ import annotations

from pathlib import Path

import pytest

from hipstraw_mm.campaign.config import load_roles
from hipstraw_mm.campaign.gate import check_move, check_read, check_role, gate_move
from hipstraw_mm.campaign.repertoire import load_repertoire
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.campaign.tracing import campaign_tracer
from hipstraw_mm.errors import PreconditionError
from tests.unit.campaign_factories import mandate

ROLES = load_roles(Path("config"))
REP = load_repertoire(Path("config"))


# -- roles (T007) --------------------------------------------------------------------------------------


def test_sponsor_may_accept_a_review() -> None:
    check_role(ROLES, "sponsor", "accept_review")


def test_reviewer_may_not_accept_a_review() -> None:
    with pytest.raises(PreconditionError, match="reviewer.*accept_review"):
        check_role(ROLES, "reviewer", "accept_review")


def test_unknown_role_is_refused() -> None:
    with pytest.raises(PreconditionError, match="unknown role"):
        check_role(ROLES, "intern", "accept_review")


# -- effect classes (T038) -----------------------------------------------------------------------------


def test_internal_moves_are_allowed() -> None:
    assert check_move(REP.moves["M04"])[0] is True


def test_read_and_inference_moves_are_allowed_within_scope() -> None:
    allowed, reason = check_move(REP.moves["M02"])
    assert allowed is True and "mandate" in reason and "campaign_source_summary.v1" in reason


def test_external_effect_is_always_refused_in_g0() -> None:
    allowed, reason = check_move(REP.moves["M10"])
    assert allowed is False and "no approved Test Plan" in reason


def test_reads_only_addresses_named_in_the_mandate() -> None:
    m = mandate()
    m = m.model_copy(update={"product": m.product.model_copy(update={"website": "https://a.example"})})
    assert check_read("https://a.example", m)[0] is True
    allowed, reason = check_read("https://elsewhere.example", m)
    assert allowed is False and "not named in the mandate" in reason


def test_gate_decisions_are_traced() -> None:
    store = SqliteCampaignStore(":memory:")
    tracer = campaign_tracer(store, Path("config"), "lch_gate")
    assert gate_move(tracer, REP.moves["M10"])[0] is False
    step = store.list_trace_steps("lch_gate")[0]
    assert (step["layer"], step["actor"], step["operation"], step["right"]) == (
        "authority_gate", "authority_gate", "check_authority", "check_authority")
    assert step["decision"] == "refused" and step["inputs"]["effectClasses"] == ["E3"]
