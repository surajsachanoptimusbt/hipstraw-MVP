"""GET/HEAD-only HTTP server for the read-only trace viewer (Constitution XIII).

Binds to loopback only. Accepts only a ReadStore (no write methods). Checks the Host header
against DNS rebinding.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from hipstraw_mm.viewer.api import (
    shape_beam,
    shape_blob,
    shape_companies,
    shape_decisions,
    shape_deliberations,
    shape_documents,
    shape_graph,
    shape_links,
    shape_paths,
    shape_run_detail,
    shape_runs,
    shape_step,
    shape_steps,
)

STATIC_DIR = Path(__file__).parent / "static"
VENDOR_DIR = STATIC_DIR / "vendor"
VENDOR_NAME = re.compile(r"^[a-z0-9][a-z0-9.\-]*\.js$")
PAGE_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
WRITE_PREFIXES = ("create", "upsert", "transition", "finish", "seal", "delete", "set", "put")
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _has_write_methods(obj: Any) -> bool:
    for name in dir(obj):
        if name.startswith("_"):
            continue
        if any(name.startswith(p) for p in WRITE_PREFIXES):
            return True
    return False


def as_read_store(store: Any) -> Any:
    """Wrap a full store so only read methods are visible. Pass-through if already clean."""
    if not _has_write_methods(store):
        return store

    class _ReadOnly:
        pass

    ro = _ReadOnly()
    for name in dir(store):
        if name.startswith("_"):
            continue
        if any(name.startswith(p) for p in WRITE_PREFIXES):
            continue
        attr = getattr(store, name)
        if callable(attr):
            setattr(ro, name, attr)
    return ro


class _Handler(BaseHTTPRequestHandler):
    store: Any
    allowed_hosts: set[str]

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _check_host(self) -> bool:
        host = self.headers.get("Host", "")
        host_name = host.split(":")[0].lower()
        if host_name not in self.allowed_hosts:
            self._json_error(403, "forbidden: Host header not allowed")
            return False
        return True

    def _json_response(self, code: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code: int, message: str) -> None:
        self._json_response(code, {"error": message})

    def _html_response(self, code: int, content: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        if not self._check_host():
            return
        self._route()

    def do_HEAD(self) -> None:
        if not self._check_host():
            return
        self._route(head=True)

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def _route(self, head: bool = False) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/":
            self._serve_index(head)
            return

        m = re.match(r"^/vendor/([^/]+)$", path)
        if m:
            self._serve_vendor(m.group(1), head)
            return

        if path == "/api/runs":
            data = shape_runs(self.store)
            if head:
                self._json_response(200, [])
            else:
                self._json_response(200, data)
            return

        m = re.match(r"^/api/runs/([^/]+)$", path)
        if m:
            run_id = m.group(1)
            run_detail = shape_run_detail(self.store, run_id)
            if run_detail is None:
                self._json_error(404, f"run {run_id} not found")
            else:
                self._json_response(200, run_detail)
            return

        m = re.match(r"^/api/runs/([^/]+)/deliberations$", path)
        if m:
            run_id = m.group(1)
            delibs = shape_deliberations(self.store, run_id)
            self._json_response(200, delibs)
            return

        for suffix, shaper in (
            ("beam", shape_beam),
            ("companies", shape_companies),
            ("decisions", shape_decisions),
            ("documents", shape_documents),
        ):
            m = re.match(rf"^/api/runs/([^/]+)/{suffix}$", path)
            if m:
                self._json_response(200, shaper(self.store, m.group(1)))
                return

        m = re.match(r"^/api/runs/([^/]+)/graph$", path)
        if m:
            run_id = m.group(1)
            ver_str = qs.get("version", [None])[0]
            try:
                ver = int(ver_str) if ver_str else None
            except ValueError:
                self._json_error(400, "version must be an integer")
                return
            graph_data = shape_graph(self.store, run_id, ver)
            if graph_data is None:
                self._json_error(404, f"graph not found for run {run_id}")
            else:
                self._json_response(200, graph_data)
            return

        m = re.match(r"^/api/runs/([^/]+)/links$", path)
        if m:
            self._json_response(200, shape_links(self.store, m.group(1)))
            return

        m = re.match(r"^/api/runs/([^/]+)/paths$", path)
        if m:
            self._json_response(200, shape_paths(self.store, m.group(1)))
            return

        m = re.match(r"^/api/runs/([^/]+)/steps$", path)
        if m:
            run_id = m.group(1)
            refresh_str = qs.get("refresh", [None])[0]
            if refresh_str:
                seqs = [int(s) for s in refresh_str.split(",") if s.strip()]
                steps_data = shape_steps(self.store, run_id, refresh=seqs)
            else:
                after = int(qs.get("after", ["0"])[0])
                steps_data = shape_steps(self.store, run_id, after=after)
            self._json_response(200, steps_data)
            return

        m = re.match(r"^/api/runs/([^/]+)/steps/(\d+)$", path)
        if m:
            run_id, seq_str = m.group(1), m.group(2)
            step_data = shape_step(self.store, run_id, int(seq_str))
            if step_data is None:
                self._json_error(404, f"step {seq_str} not found in run {run_id}")
            else:
                self._json_response(200, step_data)
            return

        m = re.match(r"^/api/blobs/([^/]+)$", path)
        if m:
            blob_id = m.group(1)
            blob_data = shape_blob(self.store, blob_id)
            if blob_data is None:
                self._json_error(404, f"blob {blob_id} not found")
            else:
                self._json_response(200, blob_data)
            return

        self._json_error(404, f"unknown route: {path}")

    def _serve_index(self, head: bool = False) -> None:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            self._html_response(200, b"<html><body>Viewer not built yet</body></html>")
            return
        content = index_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Security-Policy", PAGE_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(content)

    def _serve_vendor(self, name: str, head: bool) -> None:
        file = (VENDOR_DIR / name).resolve()
        if not VENDOR_NAME.match(name) or file.parent != VENDOR_DIR.resolve() or not file.is_file():
            self._json_error(404, f"unknown vendor file: {name}")
            return
        content = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(content)


class ViewerServer(HTTPServer):
    allow_reuse_address = False

    def __init__(self, store: Any, host: str = "127.0.0.1", port: int = 8765) -> None:
        if host not in ALLOWED_HOSTS:
            raise ValueError(f"viewer host must be a loopback address, got {host!r}")
        if _has_write_methods(store):
            raise TypeError(
                "viewer store has write methods; pass as_read_store(store) or use a ReadStore"
            )

        handler = type("Handler", (_Handler,), {
            "store": store,
            "allowed_hosts": ALLOWED_HOSTS | {host},
        })
        super().__init__((host, port), handler)
