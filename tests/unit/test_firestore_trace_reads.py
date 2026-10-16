"""Trace-step reads fetch documents by ID, so a viewer poll reads only what it needs (cloud reads are billed)."""

from __future__ import annotations

from typing import Any

import pytest

from hipstraw_mm.store.firestore import FirestoreStore


class _Snap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _Ref:
    def __init__(self, db: _FakeDb, path: str) -> None:
        self._db, self.path = db, path

    def get(self, **_: Any) -> _Snap:
        self._db.reads += 1
        return _Snap(self._db.docs.get(self.path))


class _Collection:
    def __init__(self, db: _FakeDb, name: str) -> None:
        self._db, self._name = db, name

    def document(self, doc_id: str) -> _Ref:
        return _Ref(self._db, f"{self._name}/{doc_id}")


class _FakeDb:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.reads = 0

    def collection(self, name: str) -> _Collection:
        return _Collection(self, name)

    def get_all(self, refs: list[_Ref]) -> list[_Snap]:
        self.reads += len(refs)
        return [_Snap(self.docs.get(r.path)) for r in refs]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> tuple[FirestoreStore, _FakeDb]:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    db = _FakeDb()
    db.docs["marketRuns/mrun_1"] = {"marketRunId": "mrun_1", "lastSeq": 200}
    for seq in range(1, 201):
        db.docs[f"traceSteps/mrun_1__{seq:06d}"] = {"stepId": f"mrun_1__{seq:06d}", "seq": seq}
    return FirestoreStore("demo-hipstraw-mvp", client=db, mode="emulator"), db


def test_polling_after_a_seq_reads_only_the_new_steps(store: tuple[FirestoreStore, _FakeDb]) -> None:
    fs, db = store
    steps = fs.list_trace_steps_after("mrun_1", 195)
    assert [s["seq"] for s in steps] == [196, 197, 198, 199, 200]
    assert db.reads == 1 + 5


def test_refreshing_running_steps_reads_only_those(store: tuple[FirestoreStore, _FakeDb]) -> None:
    fs, db = store
    assert [s["seq"] for s in fs.get_trace_steps("mrun_1", [7, 3, 7])] == [3, 7]
    assert db.reads == 2
    assert fs.get_trace_steps("mrun_1", []) == [] and db.reads == 2
