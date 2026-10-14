"""Firestore mode guards: emulator stays the default; cloud is an explicit, checked opt-in."""

from __future__ import annotations

from pathlib import Path

import pytest

from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.store.firestore import check_store_preconditions, firestore_mode


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HIPSTRAW_FIRESTORE", "FIRESTORE_EMULATOR_HOST", "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(name, raising=False)


def test_emulator_is_the_default_mode() -> None:
    assert firestore_mode() == "emulator"


def test_unknown_mode_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIPSTRAW_FIRESTORE", "prod")
    with pytest.raises(PreconditionError, match="emulator, cloud"):
        firestore_mode()


def test_emulator_mode_keeps_its_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(PreconditionError, match="FIRESTORE_EMULATOR_HOST"):
        check_store_preconditions("demo-hipstraw-mvp", "emulator")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    check_store_preconditions("demo-hipstraw-mvp", "emulator")
    with pytest.raises(PreconditionError, match="demo-"):
        check_store_preconditions("hipstraw-prod", "emulator")


def test_cloud_mode_refuses_an_emulator_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    with pytest.raises(PreconditionError, match="unset it"):
        check_store_preconditions("hipstraw-mvp", "cloud")


def test_cloud_mode_refuses_a_demo_project() -> None:
    with pytest.raises(PreconditionError, match="project ID"):
        check_store_preconditions("demo-hipstraw-mvp", "cloud")


def test_cloud_mode_checks_the_key_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    with pytest.raises(PreconditionError, match="does not exist"):
        check_store_preconditions("hipstraw-mvp", "cloud")
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key))
    check_store_preconditions("hipstraw-mvp", "cloud")
