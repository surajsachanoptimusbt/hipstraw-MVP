"""`hipstraw-mm campaign view`: the read-only campaign page over HTTP (marker: viewer). GET and HEAD only,
loopback only, Host header checked, the same rules as the market viewer."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hipstraw_mm.campaign.viewer import CampaignHandler, CampaignView
from hipstraw_mm.viewer.server import ViewerServer
from tests.unit.campaign_moves_support import CONFIG
from tests.unit.test_campaign_viewer import TODAY, reviewed

pytestmark = pytest.mark.viewer


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[int, str]]:
    db = tmp_path_factory.mktemp("served") / "c.db"
    launch_id = reviewed(db)
    server = ViewerServer(CampaignView(str(db), CONFIG, now=lambda: TODAY), port=0, handler=CampaignHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], launch_id
    server.shutdown()
    server.server_close()


def _request(port: int, path: str, method: str = "GET", host: str | None = None) -> tuple[int, Any, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers={"Host": host} if host else {})
    resp = conn.getresponse()
    raw = resp.read().decode()
    headers = dict(resp.getheaders())
    conn.close()
    try:
        return resp.status, json.loads(raw), headers
    except json.JSONDecodeError:
        return resp.status, raw, headers


def test_page_is_the_campaign_page_with_a_strict_policy(served: tuple[int, str]) -> None:
    port, _ = served
    status, body, headers = _request(port, "/")
    assert status == 200 and '<div id="root">' in body and "campaign" in body.lower()
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert 'src="http' not in body and 'src="//' not in body
    for name in ("react.production.min.js", "react-dom.production.min.js", "htm.umd.js"):
        assert f"/vendor/{name}" in body
        assert _request(port, f"/vendor/{name}")[0] == 200


def test_launch_routes(served: tuple[int, str]) -> None:
    port, launch_id = served
    status, launches, _ = _request(port, "/api/launches")
    assert status == 200 and [r["launchId"] for r in launches] == [launch_id]
    status, shown, _ = _request(port, f"/api/launches/{launch_id}")
    assert status == 200 and shown["rubric"]["reviewState"] == "accepted"
    status, steps, _ = _request(port, f"/api/launches/{launch_id}/trace")
    assert status == 200 and any(s["operation"] == "call_model" for s in steps)


def test_a_traced_prompt_can_be_opened(served: tuple[int, str]) -> None:
    port, launch_id = served
    _, steps, _ = _request(port, f"/api/launches/{launch_id}/trace")
    blob = next((s["promptBlobId"] for s in steps if s.get("promptBlobId")), None)
    if blob is None:
        pytest.skip("the canned model leaves no prompt blob")
    status, body, _ = _request(port, f"/api/blobs/{blob}")
    assert status == 200 and body["content"]


@pytest.mark.parametrize("path", ["/api/launches/lch_nope", "/api/blobs/nope", "/api/nothing"])
def test_unknown_paths_are_404(served: tuple[int, str], path: str) -> None:
    port, _ = served
    status, body, _ = _request(port, path)
    assert status == 404 and "error" in body


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_write_methods_are_refused(served: tuple[int, str], method: str) -> None:
    port, launch_id = served
    status, _, headers = _request(port, f"/api/launches/{launch_id}", method=method)
    assert status == 405 and "GET" in headers["Allow"]


def test_a_foreign_host_is_refused(served: tuple[int, str]) -> None:
    port, _ = served
    assert _request(port, "/api/launches", host="evil.example.com")[0] == 403
    assert _request(port, "/api/launches", host="localhost")[0] == 200


def test_only_loopback_can_be_bound(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ViewerServer(CampaignView(str(tmp_path / "c.db"), CONFIG), host="0.0.0.0", port=0, handler=CampaignHandler)


def test_the_page_never_sends_a_write() -> None:
    page = Path("src/hipstraw_mm/viewer/static/campaign.html").read_text(encoding="utf-8")
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert f'"{method}"' not in page and f"'{method}'" not in page
    assert "score" not in page.lower() and "forecast" not in page.lower()


def test_the_page_has_the_three_views_and_the_audit() -> None:
    page = Path("src/hipstraw_mm/viewer/static/campaign.html").read_text(encoding="utf-8")
    for view in ('k: "report"', 'k: "campaign"', 'k: "desk"', 'k: "position"', 'k: "lines"', 'k: "trace"'):
        assert view in page, view
    assert "hs review finding --review" in page  # the desk shows the command; the page itself never writes
