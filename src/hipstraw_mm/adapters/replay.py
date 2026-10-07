"""Record and replay for the model, search, and fetch adapters (research R11).

Recordings live at `<scenario_dir>/<kind>/<sha256(matchKey)>.json` as `{matchKey, request, response}`.
Match keys are stable (URL, query, or schema name plus a stable ID), so editing a prompt does not
invalidate them. In replay mode a missing recording raises; it never falls through to the network.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from hipstraw_mm.logging_setup import REDACTED, secret_values

Mode = Literal["off", "replay", "record"]
MODES: tuple[Mode, ...] = ("off", "replay", "record")
_REDACT_KEYS = {"authorization", "x-subscription-token", "api_key"}


class ReplayMissingError(Exception):
    pass


class SecretLeakError(Exception):
    pass


def match_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if str(k).lower() in _REDACT_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def mode_from_env() -> Mode:
    mode = os.environ.get("HIPSTRAW_REPLAY", "off").strip().lower() or "off"
    if mode not in MODES:
        raise ValueError(f"HIPSTRAW_REPLAY must be one of {MODES}, got {mode!r}")
    return mode


class ReplayStore:
    def __init__(self, scenario_dir: Path | None, mode: Mode = "replay") -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if mode != "off" and scenario_dir is None:
            raise ValueError(f"mode '{mode}' needs a scenario directory")
        self.scenario_dir = Path(scenario_dir) if scenario_dir is not None else None
        self.mode: Mode = mode

    def path_for(self, kind: str, match_key: str) -> Path:
        assert self.scenario_dir is not None
        return self.scenario_dir / kind / f"{match_key_hash(match_key)}.json"

    def get(self, kind: str, match_key: str) -> dict[str, Any]:
        path = self.path_for(kind, match_key)
        if not path.exists():
            raise ReplayMissingError(f"no recorded {kind} response for {match_key!r} ({path})")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("matchKey") != match_key:
            raise ReplayMissingError(f"recording {path} is for {record.get('matchKey')!r}, not {match_key!r}")
        response: dict[str, Any] = record["response"]
        return response

    def put(self, kind: str, match_key: str, request: dict[str, Any], response: dict[str, Any]) -> None:
        record = {"matchKey": match_key, "request": redact(request), "response": redact(response)}
        text = json.dumps(record, indent=2, ensure_ascii=False)
        if any(secret in text for secret in secret_values()):
            raise SecretLeakError(f"refusing to write a {kind} recording that contains a key value")
        path = self.path_for(kind, match_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def call(
        self,
        kind: str,
        match_key: str,
        request: dict[str, Any],
        live: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Replay, or call `live` and (in record mode) save what it returned."""
        if self.mode == "replay":
            return self.get(kind, match_key)
        response = live()
        if self.mode == "record":
            self.put(kind, match_key, request, response)
        return response
