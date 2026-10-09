"""T012: Integration tests for the viewer server (marker: viewer)."""

from __future__ import annotations

import http.client
import json
import threading
import time

import pytest

from hipstraw_mm.store.memory import MemoryStore

pytestmark = pytest.mark.viewer


def _seed_store():
    store = MemoryStore()
    run_id = "mrun_viewer_test"
    store.upsert_market_run({
        "marketRunId": run_id, "status": "opened", "lastSeq": 1,
        "counts": {}, "marketStatus": None, "programId": "test",
        "model": "gpt-4o", "createdAt": "2026-01-01T00:00:00Z",
    })
    store.create_trace_step({
        "stepId": f"{run_id}__000001", "marketRunId": run_id, "seq": 1,
        "status": "ok", "layer": "market_manager", "actor": "market_manager",
        "operation": "open_run", "inputs": {}, "outputs": {"runId": run_id},
        "decision": None, "right": "open_run", "rationale": None,
        "alternatives": [], "checks": [], "model": None,
        "promptBlobId": None, "responseBlobId": None, "toolCalls": [],
        "cost": {"inputTokens": None, "outputTokens": None, "usd": None},
        "latencyMs": 50, "startedAt": "2026-01-01T00:00:00Z",
        "endedAt": "2026-01-01T00:00:01Z", "error": None, "parentStepId": None,
    })
    return store, run_id


@pytest.fixture
def viewer_server():
    from hipstraw_mm.viewer.server import ViewerServer, as_read_store

    store, run_id = _seed_store()
    server = ViewerServer(as_read_store(store), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    port = server.server_address[1]
    yield port, run_id, store
    server.shutdown()


def _get(port: int, path: str, host_header: str | None = None) -> tuple[int, dict | str, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if host_header:
        headers["Host"] = host_header
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode()
    resp_headers = dict(resp.getheaders())
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = body
    conn.close()
    return resp.status, data, resp_headers


def _method(port: int, method: str, path: str) -> tuple[int, dict | str, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path)
    resp = conn.getresponse()
    body = resp.read().decode()
    resp_headers = dict(resp.getheaders())
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = body
    conn.close()
    return resp.status, data, resp_headers


class TestGETAndHEAD:
    def test_get_root(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, body, _ = _get(port, "/")
        assert status == 200

    def test_head_root(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, _, _ = _method(port, "HEAD", "/")
        assert status == 200

    def test_get_api_runs(self, viewer_server) -> None:
        port, run_id, _ = viewer_server
        status, data, _ = _get(port, "/api/runs")
        assert status == 200
        assert isinstance(data, list)

    def test_get_steps(self, viewer_server) -> None:
        port, run_id, _ = viewer_server
        status, data, _ = _get(port, f"/api/runs/{run_id}/steps?after=0")
        assert status == 200

    def test_get_single_step(self, viewer_server) -> None:
        port, run_id, _ = viewer_server
        status, data, _ = _get(port, f"/api/runs/{run_id}/steps/1")
        assert status == 200


class TestDisallowedMethods:
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    @pytest.mark.parametrize("path", ["/", "/api/runs", "/api/runs/mrun_test/steps"])
    def test_disallowed_method_returns_405(self, viewer_server, method, path) -> None:
        port, _, _ = viewer_server
        status, _, headers = _method(port, method, path)
        assert status == 405
        allow = headers.get("Allow", headers.get("allow", ""))
        assert "GET" in allow
        assert "HEAD" in allow


class TestHostHeaderCheck:
    def test_foreign_host_returns_403(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, _, _ = _get(port, "/api/runs", host_header="evil.example.com")
        assert status == 403

    def test_localhost_host_ok(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, _, _ = _get(port, "/api/runs", host_header="localhost")
        assert status == 200

    def test_127_0_0_1_host_ok(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, _, _ = _get(port, "/api/runs", host_header="127.0.0.1")
        assert status == 200


class TestNonLoopbackHostRaises:
    def test_non_loopback_raises(self) -> None:
        from hipstraw_mm.viewer.server import ViewerServer
        store, _ = _seed_store()
        with pytest.raises((ValueError, OSError)):
            ViewerServer(store, host="192.168.1.1", port=0)


class TestWriteMethodRejection:
    def test_viewer_rejects_store_with_write_method(self) -> None:
        from hipstraw_mm.viewer.server import ViewerServer

        class WriteStore:
            def get_market_runs(self):
                return []
            def create_evidence(self, data):
                pass

        with pytest.raises((TypeError, ValueError)):
            ViewerServer(WriteStore(), host="127.0.0.1", port=0)


class TestStoreSpyZeroWrites:
    def test_no_write_calls_during_requests(self, viewer_server) -> None:
        port, run_id, store = viewer_server
        original_methods = {}
        write_calls = []
        for name in dir(store):
            if any(name.startswith(p) for p in ("create", "upsert", "transition", "finish")):
                original = getattr(store, name)
                original_methods[name] = original

                def spy(n=name):
                    def wrapper(*args, **kwargs):
                        write_calls.append(n)
                        return original_methods[n](*args, **kwargs)
                    return wrapper
                setattr(store, name, spy())

        _get(port, "/api/runs")
        _get(port, f"/api/runs/{run_id}/steps?after=0")
        _get(port, f"/api/runs/{run_id}/steps/1")

        assert len(write_calls) == 0, f"Write calls during requests: {write_calls}"


class TestUnknownRunReturns404:
    def test_unknown_run(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, data, _ = _get(port, "/api/runs/mrun_nonexistent")
        assert status == 404
        assert "error" in data


class TestPortInUse:
    def test_port_already_bound(self, viewer_server) -> None:
        from hipstraw_mm.viewer.server import ViewerServer, as_read_store
        port, _, _ = viewer_server
        store, _ = _seed_store()
        with pytest.raises((OSError, SystemExit)):
            ViewerServer(as_read_store(store), host="127.0.0.1", port=port)


class TestStaticPage:
    def test_index_sets_a_strict_content_security_policy(self, viewer_server) -> None:
        port, _, _ = viewer_server
        status, body, headers = _get(port, "/")
        assert status == 200
        assert "<div id=\"root\">" in body
        csp = headers["Content-Security-Policy"]
        assert "default-src 'none'" in csp and "connect-src 'self'" in csp
        assert "http" not in csp

    def test_page_loads_scripts_only_from_this_server(self, viewer_server) -> None:
        port, _, _ = viewer_server
        _, body, _ = _get(port, "/")
        assert "src=\"http" not in body and "src=\"//" not in body
        for name in ("react.production.min.js", "react-dom.production.min.js", "htm.umd.js"):
            assert f"/vendor/{name}" in body
            status, script, headers = _get(port, f"/vendor/{name}")
            assert status == 200
            assert headers["Content-Type"].startswith("text/javascript")
            assert len(script) > 500

    @pytest.mark.parametrize("path", [
        "/vendor/..%2Fserver.py", "/vendor/../server.py", "/vendor/missing.js",
        "/vendor/README.md", "/vendor/.hidden.js",
    ])
    def test_vendor_route_serves_only_known_files(self, viewer_server, path: str) -> None:
        port, _, _ = viewer_server
        status, _, _ = _get(port, path)
        assert status == 404
