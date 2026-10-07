"""`hipstraw-mm` command line (contracts/cli.md, Constitution II).

Every step is its own subcommand. Errors always go to stderr with the exit codes from the contract;
with `--json`, stdout also carries one JSON object including an `error` field.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, TextIO

from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient, LLMSchemaError
from hipstraw_mm.adapters.replay import ReplayMissingError, ReplayStore, mode_from_env
from hipstraw_mm.adapters.search import BraveSearch
from hipstraw_mm.config import LoadedConfig, load_config
from hipstraw_mm.errors import ExternalServiceError, HipstrawError, PreconditionError, UsageError
from hipstraw_mm.logging_setup import EventLog, scrub
from hipstraw_mm.store.base import InvalidTransitionError, NotFoundError, Store

COMMANDS = ("intake", "candidates", "position", "discover", "verify", "review", "report", "run", "show")


@dataclass
class Context:
    """Everything a step needs. Tests build their own with a MemoryStore and replay adapters."""

    config: LoadedConfig
    store: Store
    log: EventLog
    llm: LLMClient
    search: BraveSearch
    new_fetcher: Callable[[], Fetcher]
    reports_dir: Path = Path("reports")
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))


@dataclass
class CommandResult:
    command: str
    message: str = ""
    runId: str | None = None
    status: str | None = None
    counts: dict[str, int] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"command": self.command}
        for key in ("runId", "status", "counts"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.warnings:
            out["warnings"] = self.warnings
        return out


def build_context(config: LoadedConfig) -> Context:
    """The real context: emulator-only Firestore, live (or recorded) adapters."""
    from hipstraw_mm.store.firestore import FirestoreStore, check_emulator_preconditions

    project_id = os.environ.get("HIPSTRAW_PROJECT_ID") or config.run.projectId
    check_emulator_preconditions(project_id)
    mode = mode_from_env()
    replay_dir = os.environ.get("HIPSTRAW_REPLAY_DIR")
    if mode != "off" and not replay_dir:
        raise PreconditionError("HIPSTRAW_REPLAY_DIR must be set when HIPSTRAW_REPLAY is 'replay' or 'record'")
    replay = ReplayStore(Path(replay_dir) if replay_dir else None, mode=mode)
    log = EventLog(runs_dir=Path(".runs"))
    policy = config.source_policy
    fetch = config.run.fetch

    def new_fetcher() -> Fetcher:
        return Fetcher(
            replay_store=replay,
            denylist_domains=policy.denylistDomains,
            user_agent=policy.userAgent,
            timeout_seconds=fetch.timeoutSeconds,
            max_bytes=fetch.maxBytes,
            per_host_delay_seconds=fetch.perHostDelaySeconds,
        )

    return Context(
        config=config,
        store=FirestoreStore(project_id),
        log=log,
        llm=LLMClient(model=config.run.model.name, replay=replay, log=log),
        search=BraveSearch(replay, denylist_domains=policy.denylistDomains, timeout_seconds=fetch.timeoutSeconds),
        new_fetcher=new_fetcher,
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.prog}: {message}")


def build_parser() -> argparse.ArgumentParser:
    common = _Parser(add_help=False)
    common.add_argument("--config-dir", default="config", help="config directory (default: ./config)")
    common.add_argument("--json", action="store_true", help="print one JSON object on stdout")

    parser = _Parser(prog="hipstraw-mm", description="Find and review target companies for one micro-market.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    p = sub.add_parser("intake", parents=[common], help="load a program config into the store")
    p.add_argument("--program", default="invoice_alpha")

    p = sub.add_parser("candidates", parents=[common], help="copy the program's experiment contexts")
    p.add_argument("--program", required=True, help="program ID, e.g. invoice_alpha_genesis")

    p = sub.add_parser("position", parents=[common], help="create a run from a first-position file")
    p.add_argument("--candidate", required=True)
    p.add_argument("--file", required=True)

    for name, help_text in [
        ("discover", "find companies for a run"),
        ("verify", "check websites and extract cited evidence"),
        ("review", "Market Manager Review: dispositions and baseline"),
        ("show", "print a run's status, counts, and dispositions"),
    ]:
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.add_argument("--run", required=True)

    p = sub.add_parser("report", parents=[common], help="write the markdown demo report")
    p.add_argument("--run", required=True)
    p.add_argument("--out", default=None, help="output directory (default: reports/)")

    p = sub.add_parser("run", parents=[common], help="position, discover, verify, review, report")
    p.add_argument("--candidate", required=True)
    p.add_argument("--file", required=True)
    return parser


def _not_implemented(ctx: Context, args: argparse.Namespace) -> CommandResult:
    raise UsageError(f"'{args.command}' is not implemented yet")


HANDLERS: dict[str, Callable[[Context, argparse.Namespace], CommandResult]] = {
    name: _not_implemented for name in COMMANDS
}


_HANDLED = (HipstrawError, InvalidTransitionError, NotFoundError, LLMSchemaError, ReplayMissingError)


def _error_code(exc: Exception) -> int:
    if isinstance(exc, HipstrawError):
        return exc.exit_code
    if isinstance(exc, (InvalidTransitionError, NotFoundError)):
        return PreconditionError.exit_code
    return ExternalServiceError.exit_code


def main(
    argv: list[str] | None = None,
    *,
    context_factory: Callable[[LoadedConfig], Context] = build_context,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    command = "hipstraw-mm"
    json_mode = "--json" in (argv if argv is not None else sys.argv[1:])
    try:
        args = build_parser().parse_args(argv)
        command, json_mode = args.command, args.json
        ctx = context_factory(load_config(Path(args.config_dir)))
        result = HANDLERS[command](ctx, args)
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    except _HANDLED as exc:
        code = _error_code(exc)
        message = scrub(str(exc) or type(exc).__name__)
        print(f"error: {message}", file=err)
        if json_mode:
            print(json.dumps({"command": command, "error": {"code": code, "message": message}}), file=out)
        return code

    if json_mode:
        print(json.dumps(result.to_json()), file=out)
    else:
        if result.message:
            print(result.message, file=out)
        for warning in result.warnings:
            print(f"warning: {warning}", file=err)
    return 0
