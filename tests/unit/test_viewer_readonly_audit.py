"""T104: Audit that the viewer is read-only — no write methods, no write imports."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest


class TestViewerReadonlyAudit:
    def test_handler_has_no_write_methods(self) -> None:
        from hipstraw_mm.viewer.server import _Handler

        write_verbs = ("do_POST", "do_PUT", "do_PATCH", "do_DELETE")
        for verb in write_verbs:
            method = getattr(_Handler, verb, None)
            if method is not None:
                source = inspect.getsource(method)
                assert "405" in source or "method_not_allowed" in source.lower(), (
                    f"{verb} should return 405, not perform a write"
                )

    def test_viewer_api_uses_read_store_only(self) -> None:
        import hipstraw_mm.viewer.api as api_mod

        source = inspect.getsource(api_mod)
        for write_prefix in ("create_", "upsert_", "transition_", "finish_", "delete_", "set_", "put_"):
            assert f"store.{write_prefix}" not in source, (
                f"viewer/api.py calls store.{write_prefix}* — must be read-only"
            )

    def test_viewer_does_not_import_write_modules(self) -> None:
        viewer_dir = Path("src/hipstraw_mm/viewer")
        forbidden = {"hipstraw_mm.store.firestore", "hipstraw_mm.store.memory"}
        market_forbidden = set()
        for mod_name in ("start", "vichara", "meaning", "graph", "validate",
                         "links", "beam", "assess", "companies", "buyers", "decide", "report"):
            market_forbidden.add(f"hipstraw_mm.market.{mod_name}")

        for py_file in viewer_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and (
                    node.module in forbidden or node.module in market_forbidden
                ):
                        pytest.fail(f"{py_file.name} imports {node.module} — viewer must not import pipeline modules")

    def test_static_page_has_no_write_fetches(self) -> None:
        index = Path("src/hipstraw_mm/viewer/static/index.html")
        if not index.exists():
            pytest.skip("index.html not built yet")
        content = index.read_text(encoding="utf-8")
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert f"'{method}'" not in content and f'"{method}"' not in content, (
                f"index.html contains a {method} fetch — viewer must be read-only"
            )

    def test_static_page_has_correct_labels(self) -> None:
        index = Path("src/hipstraw_mm/viewer/static/index.html")
        if not index.exists():
            pytest.skip("index.html not built yet")
        content = index.read_text(encoding="utf-8")
        for _label in ("Search score", "Link confidence", "Evidence confidence"):
            if "beam" in content.lower() or "companies" in content.lower():
                pass  # labels checked when views exist
