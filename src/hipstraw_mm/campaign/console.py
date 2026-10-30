"""The governed campaign console (constitution XIII, v2.0.0): `hipstraw-mm campaign console`.

The campaign page with the actions the product owner approved on 30 October 2026: the Sponsor submits a
launch and accepts or rejects a validated Review; a Hipstraw reviewer accepts, corrects or rejects findings
and validates a Review. Each action calls the same library operation as its CLI command (`submit_launch_data`
beside `submit_launch`, `review_finding`, `validate_review`, `accept_review`, `reject_review`), so the
authority gate, the trace and the audit apply exactly as on the command line; this module only turns a JSON
request into that call. Nothing here writes to storage itself, chooses or runs a Line, or dispatches anything.

A change is accepted only as a JSON POST from the console's own page: the Host header and the Origin are
checked (loopback only, cross-site requests refused), the request carries the per-session token the console
issued, and its size is bounded. Until authentication exists, the actor declares who they are and in which
role, as on the CLI, and the gate decides what that role may do.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from hipstraw_mm.campaign.config import load_roles
from hipstraw_mm.campaign.intake import submit_launch_data
from hipstraw_mm.campaign.review import accept_review, reject_review, review_finding, validate_review
from hipstraw_mm.campaign.store import SqliteCampaignStore
from hipstraw_mm.campaign.viewer import CampaignHandler, CampaignView, _utc_now
from hipstraw_mm.errors import PreconditionError, UsageError
from hipstraw_mm.viewer.server import ViewerServer

Doc = dict[str, Any]
MAX_BODY = 256 * 1024
TOKEN_HEADER = "X-Hipstraw-Token"
# The approved actions (spec FR-056) and the right each one needs; the authority gate checks the right.
ACTIONS = {"submit": "submit_launch", "finding": "review_finding", "validate": "validate_review",
           "decide": "accept_review"}
EXAMPLES = ("kozmo_email_us.yaml", "kozmo_three_channels_us.yaml")


class ConsoleError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _text(body: Doc, key: str, *, required: bool = True) -> str | None:
    value = body.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise UsageError(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise UsageError(f"{key} must be text")
    return value.strip()


class CampaignConsole:
    """The approved actions, each one call to the governed operation the CLI uses."""

    def __init__(self, db_path: str, config_dir: Path, now: Callable[[], datetime] = _utc_now,
                 examples_dir: Path = Path("input/campaign")) -> None:
        self._db_path, self._config_dir, self._now = db_path, config_dir, now
        self._examples_dir = examples_dir

    def roles(self) -> dict[str, list[str]]:
        return load_roles(self._config_dir).roles

    def examples(self) -> list[Doc]:
        """The scenario launch files, so the form can start from one (read only)."""
        out = []
        for name in EXAMPLES:
            path = self._examples_dir / name
            if path.is_file():
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                out.append({"name": name, "launch": json.loads(json.dumps(raw, default=str))})
        return out

    def act(self, action: str, body: Doc) -> Doc:
        if action not in ACTIONS:
            raise ConsoleError(404, f"unknown action: {action}")
        by, role = _text(body, "by"), _text(body, "role")
        assert by is not None and role is not None
        store = SqliteCampaignStore(self._db_path)
        try:
            return getattr(self, f"_{action}")(store, body, by, role, self._now())  # type: ignore[no-any-return]
        finally:
            store.close()

    def _submit(self, store: SqliteCampaignStore, body: Doc, by: str, role: str, now: datetime) -> Doc:
        launch = body.get("launch")
        if not isinstance(launch, dict):
            raise UsageError("launch must be an object (the launch file's fields)")
        r = submit_launch_data(store, self._config_dir, launch, source="console form", by=by, role=role, now=now)
        return {"launchId": r.launchId, "positionVersion": r.positionVersion, "evidence": r.evidence}

    def _finding(self, store: SqliteCampaignStore, body: Doc, by: str, role: str, now: datetime) -> Doc:
        action = _text(body, "action")
        if action not in ("accept", "reject", "correct"):
            raise UsageError("action must be accept, reject or correct")
        verdict = _text(body, "verdict", required=False)
        if verdict is not None and verdict not in ("met", "partly", "not_met", "unknown"):
            raise UsageError("verdict must be met, partly, not_met or unknown")
        review_id, finding_id, reason = _text(body, "reviewId"), _text(body, "findingId"), _text(body, "reason")
        assert review_id is not None and finding_id is not None and reason is not None
        review = review_finding(store, self._config_dir, review_id, finding_id, action=action,  # type: ignore[arg-type]
                                reason=reason, by=by, role=role, now=now, text=_text(body, "text", required=False),
                                verdict=verdict)  # type: ignore[arg-type]
        found = next(f for f in review.findings if f.findingId == finding_id)
        return {"reviewId": review.reviewId, "findingId": finding_id, "reviewState": found.reviewState}

    def _validate(self, store: SqliteCampaignStore, body: Doc, by: str, role: str, now: datetime) -> Doc:
        review_id = _text(body, "reviewId")
        assert review_id is not None
        review = validate_review(store, self._config_dir, review_id, by=by, role=role, now=now)
        return {"reviewId": review.reviewId, "state": review.state}

    def _decide(self, store: SqliteCampaignStore, body: Doc, by: str, role: str, now: datetime) -> Doc:
        review_id, decision = _text(body, "reviewId"), _text(body, "decision")
        assert review_id is not None
        if decision == "accept":
            review = accept_review(store, self._config_dir, review_id, by=by, role=role, now=now,
                                   reason=_text(body, "reason", required=False))
        elif decision == "reject":
            reason = _text(body, "reason")
            assert reason is not None
            review = reject_review(store, self._config_dir, review_id, by=by, role=role, now=now, reason=reason)
        else:
            raise UsageError("decision must be accept or reject")
        return {"reviewId": review.reviewId, "state": review.state,
                "positionVersion": review.committedPositionVersion}


class CampaignConsoleHandler(CampaignHandler):
    """The campaign page's routes, plus the approved actions as JSON POSTs under /api/console/."""

    console: CampaignConsole
    token: str

    def _session(self) -> Doc:
        return {"writable": True, "token": self.token, "roles": self.console.roles(),
                "actions": sorted(ACTIONS)}

    def _route(self, head: bool = False) -> None:
        if urlparse(self.path).path.rstrip("/") == "/api/console/examples":
            self._json_response(200, self.console.examples())
            return
        super()._route(head)

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD, POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _same_origin(self) -> bool:
        origin = urlparse(self.headers.get("Origin", ""))
        port = getattr(self.server, "server_port", None)
        return origin.scheme == "http" and (origin.hostname or "") in self.allowed_hosts and origin.port == port

    def _read_body(self) -> tuple[int, bytes]:
        """Read the body before any answer, so a refusal reaches the client instead of a reset connection;
        a body far over the limit is left unread and the connection closed."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if 0 < length <= 4 * MAX_BODY:
            return length, self.rfile.read(length)
        if length > 4 * MAX_BODY:
            self.close_connection = True
        return length, b""

    def do_POST(self) -> None:  # noqa: N802 (http.server names its handlers this way)
        length, raw = self._read_body()
        if not self._check_host():
            return
        path = urlparse(self.path).path.rstrip("/")
        try:
            if not path.startswith("/api/console/"):
                raise ConsoleError(404, f"unknown route: {path}")
            if not self._same_origin():
                raise ConsoleError(403, "forbidden: a change must come from the console's own page")
            if not secrets.compare_digest(self.headers.get(TOKEN_HEADER, ""), self.token):
                raise ConsoleError(403, "forbidden: missing or wrong console token")
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ConsoleError(415, "a change is a JSON request")
            if length < 0:
                raise ConsoleError(400, "Content-Length is not a number")
            if length > MAX_BODY:
                raise ConsoleError(413, f"request larger than {MAX_BODY // 1024} KB")
            try:
                body = json.loads(raw or b"null")
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ConsoleError(400, f"not valid JSON: {exc}") from exc
            if not isinstance(body, dict):
                raise ConsoleError(400, "the request body must be a JSON object")
            self._json_response(200, self.console.act(path.rsplit("/", 1)[1], body))
        except ConsoleError as exc:
            self._json_error(exc.status, str(exc))
        except UsageError as exc:
            self._json_error(400, str(exc))
        except PreconditionError as exc:
            # The gate's refusals are already audited; a state precondition (e.g. pending findings) is a conflict.
            refused = str(exc).startswith(("role ", "unknown role"))
            self._json_error(403 if refused else 409, str(exc))


class ConsoleServer(ViewerServer):
    """The campaign console on the viewer server's rules (loopback only, Host header checked)."""

    def __init__(self, view: CampaignView, console: CampaignConsole, host: str = "127.0.0.1",
                 port: int = 8766) -> None:
        handler = type("ConsoleHandler", (CampaignConsoleHandler,),
                       {"console": console, "token": secrets.token_urlsafe(32)})
        super().__init__(view, host=host, port=port, handler=handler)
