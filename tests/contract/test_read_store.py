"""T008: Contract tests for the ReadStore protocol."""

from __future__ import annotations

import inspect

import pytest

from hipstraw_mm.store.base import ReadStore
from hipstraw_mm.store.memory import MemoryStore

WRITE_PREFIXES = ("create", "upsert", "transition", "finish", "seal", "delete", "set", "put")


class TestReadStoreProtocol:
    def test_read_store_has_no_write_methods(self) -> None:
        methods = [
            name for name, _ in inspect.getmembers(ReadStore, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for name in methods:
            assert not any(name.startswith(p) for p in WRITE_PREFIXES), (
                f"ReadStore has write-like method: {name}"
            )

    def test_memory_store_satisfies_read_store(self) -> None:
        store = MemoryStore()
        read_methods = [
            name for name, _ in inspect.getmembers(ReadStore, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for name in read_methods:
            assert hasattr(store, name), f"MemoryStore missing ReadStore method: {name}"

    def test_viewer_rejects_object_with_write_method(self) -> None:
        from hipstraw_mm.viewer.server import ViewerServer

        class BadStore:
            def get_market_runs(self):
                return []
            def create_something(self):
                pass

        with pytest.raises((TypeError, ValueError)):
            ViewerServer(BadStore(), host="127.0.0.1", port=0)
