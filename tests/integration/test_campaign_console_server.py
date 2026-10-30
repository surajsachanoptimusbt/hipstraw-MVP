"""`hipstraw-mm campaign console` over HTTP (marker: viewer): the approved actions as JSON POSTs, refused
unless they come from the console's own page with its token (constitution XIII, v2.0.0)."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from hipstraw_mm.campaign.console import CampaignConsole, ConsoleServer
from hipstraw_mm.campaign.viewer import CampaignView
from tests.unit.campaign_moves_support import CONFIG, FIX, NOW
from tests.unit.test_campaign_viewer import TODAY

pytestmark = pytest.mark.viewer


@pytest.fixture()
def served(tmp_path: Path) -> Iterator[tuple[int, str]]:
    db = str(tmp_path / "c.db")
    server = ConsoleServer(CampaignView(db, CONFIG, now=lambda: TODAY), CampaignConsole(db, CONFIG, now=lambda: NOW),
                           port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    yield port, _request(port, "/api/session")[1]["token"]
    server.shutdown()
    server.server_close()


def _request(port: int, path: str, method: str = "GET", body: Any = None,
             headers: dict[str, str] | None = None) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=data, headers=headers or {})
    resp = conn.getresponse()
    raw = resp.read().decode()
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def _post(port: int, token: str, action: str, body: Any, **override: str) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json", "X-Hipstraw-Token": token, "Origin": f"http://127.0.0.1:{port}"}
    headers.update(override)
    return _request(port, f"/api/console/{action}", "POST", body, {k: v for k, v in headers.items() if v})


def _launch() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((FIX / "launch_complete.yaml").read_text(encoding="utf-8"))
    return json.loads(json.dumps(raw, default=str))


SUBMIT = {"by": "Kozmo GTM lead", "role": "sponsor"}


def test_the_session_names_the_rights_of_each_role(served: tuple[int, str]) -> None:
    port, token = served
    status, session = _request(port, "/api/session")
    assert status == 200 and session["writable"] is True and len(token) > 30
    assert "review_finding" in session["roles"]["reviewer"] and "submit_launch" in session["roles"]["sponsor"]


def test_a_launch_submitted_in_the_browser_appears_like_any_other(served: tuple[int, str]) -> None:
    port, token = served
    status, out = _post(port, token, "submit", {"launch": _launch(), **SUBMIT})
    assert status == 200 and out["positionVersion"] == 1
    status, launches = _request(port, "/api/launches")
    assert [row["launchId"] for row in launches] == [out["launchId"]]


@pytest.mark.parametrize("override, status, message", [
    ({"X-Hipstraw-Token": ""}, 403, "token"),
    ({"X-Hipstraw-Token": "guessed"}, 403, "token"),
    ({"Origin": ""}, 403, "own page"),
    ({"Origin": "http://evil.example.com"}, 403, "own page"),
    ({"Origin": "http://127.0.0.1:1"}, 403, "own page"),
    ({"Content-Type": "text/plain"}, 415, "JSON"),
])
def test_a_change_from_anywhere_but_the_console_page_is_refused(served: tuple[int, str], override: dict[str, str],
                                                                status: int, message: str) -> None:
    port, token = served
    got, body = _post(port, token, "submit", {"launch": _launch(), **SUBMIT}, **override)
    assert got == status and message in body["error"]
    assert _request(port, "/api/launches")[1] == []  # nothing was written


def test_a_foreign_host_is_refused_for_changes_too(served: tuple[int, str]) -> None:
    port, token = served
    status, _ = _post(port, token, "submit", {"launch": _launch(), **SUBMIT}, Host="evil.example.com")
    assert status == 403


def test_a_large_or_malformed_request_is_refused(served: tuple[int, str]) -> None:
    port, token = served
    status, body = _post(port, token, "submit", b"x" * (256 * 1024 + 1))
    assert status == 413
    status, body = _post(port, token, "submit", b"{not json")
    assert status == 400 and "JSON" in body["error"]
    status, body = _post(port, token, "submit", [1, 2])
    assert status == 400


def test_the_gate_decides_what_a_role_may_do(served: tuple[int, str]) -> None:
    port, token = served
    status, body = _post(port, token, "submit", {"launch": _launch(), "by": "Hipstraw Reviewer", "role": "reviewer"})
    assert status == 403 and "may not submit_launch" in body["error"]
    status, body = _post(port, token, "submit", {"launch": {"market": "US"}, **SUBMIT})
    assert status == 400 and "not valid" in body["error"]
    status, body = _post(port, token, "run_line", {**SUBMIT})
    assert status == 404


def test_a_state_precondition_is_a_conflict(served: tuple[int, str]) -> None:
    port, token = served
    status, body = _post(port, token, "validate", {"reviewId": "rev_nope", "by": "R", "role": "reviewer"})
    assert status == 409 and "not found" in body["error"]


def test_put_patch_delete_stay_refused(served: tuple[int, str]) -> None:
    port, _ = served
    for method in ("PUT", "PATCH", "DELETE"):
        assert _request(port, "/api/console/submit", method)[0] == 405


def test_the_form_reads_the_channel_standards_and_the_scenarios(served: tuple[int, str]) -> None:
    port, _ = served
    status, standards = _request(port, "/api/standards")
    assert status == 200 and standards["channels"]["email"]["assetFields"]["subject"] == "Subject line"
    assert standards["markets"] == ["US", "IN"]
    status, examples = _request(port, "/api/console/examples")
    assert status == 200 and examples[0]["launch"]["channels"][0]["channel"] == "email"
