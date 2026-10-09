"""T085: buyer roles are kept only with passing cited evidence and never carry a person."""

from __future__ import annotations


def _docs():
    return {
        "e1": {"evidenceId": "e1", "check": {"status": "pass"}},
        "e2": {"evidenceId": "e2", "check": {"status": "fail"}},
    }


def _role(ids):
    return {"pathId": "p1", "role": "Head of Finance", "authority": "approves", "evidenceIds": ids, "rationale": "r"}


def test_kept_when_all_passing() -> None:
    from hipstraw_mm.market.buyers import validate_buyer_role

    r = validate_buyer_role(_role(["e1"]), _docs())
    assert r["kept"] is True and r["role"]["role"] == "Head of Finance"


def test_unknown_when_any_failing() -> None:
    from hipstraw_mm.market.buyers import validate_buyer_role

    r = validate_buyer_role(_role(["e1", "e2"]), _docs())
    assert r["kept"] is False and r["unknown"]["reason"]


def test_unknown_when_evidence_not_of_company() -> None:
    from hipstraw_mm.market.buyers import validate_buyer_role

    assert validate_buyer_role(_role(["zz"]), _docs())["kept"] is False


def test_role_never_carries_person() -> None:
    from hipstraw_mm.market.buyers import validate_buyer_role

    r = validate_buyer_role({**_role(["e1"]), "name": "Jane", "email": "j@x.test"}, _docs())
    assert r["kept"] is True
    assert not {"name", "email", "phone", "person"} & set(r["role"])


def test_batched_per_path() -> None:
    from hipstraw_mm.market.buyers import batch_by_path

    paths = [
        {"pathId": "p1", "companies": [{"d": 1}, {"d": 2}]},
        {"pathId": "p2", "companies": [{"d": 3}]},
        {"pathId": "p3", "companies": []},
    ]
    batches = batch_by_path(paths)
    assert [b[0] for b in batches] == ["p1", "p2"]
    assert len(batches[0][1]) == 2
