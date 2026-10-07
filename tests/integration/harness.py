"""Helpers for the integration tests: drive `cli.main` against a MemoryStore and replayed adapters."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hipstraw_mm import cli
from hipstraw_mm.config import LoadedConfig
from hipstraw_mm.store.memory import MemoryStore

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
TEST_CONFIG_DIR = FIXTURES_DIR / "config"

# The `basic` recordings were built for this clock, so it fixes the run ID their judgement keys use.
FIXED_NOW = datetime(2026, 10, 7, 10, 15, 0, tzinfo=timezone.utc)
RUN_ID = "run_20261007T101500"
PROGRAM_ID = "invoice_alpha_genesis"
CANDIDATE_ID = "invoice_alpha_genesis__saas_recurring_fees"
POSITION_FILE = FIXTURES_DIR / "positions" / "first_position.yaml"
STEPS = ("discover", "verify", "review", "report")


@dataclass
class CliResult:
    code: int
    json: dict[str, Any] | None
    stderr: str


@dataclass
class Harness:
    """One store, one replay scenario, and one temporary working area, shared by every CLI call."""

    store: MemoryStore
    runs_dir: Path
    reports_dir: Path
    context_factory: Callable[[LoadedConfig], cli.Context]

    def cli(self, *argv: str) -> CliResult:
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            [*argv, "--config-dir", str(TEST_CONFIG_DIR), "--json"],
            context_factory=self.context_factory,
            stdout=out,
            stderr=err,
        )
        text = out.getvalue().strip()
        return CliResult(code, json.loads(text) if text else None, err.getvalue())

    def log_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self.runs_dir / run_id / "run.log"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class CompletedRun:
    harness: Harness
    run_id: str
    results: dict[str, CliResult]

    @property
    def store(self) -> MemoryStore:
        return self.harness.store

    def records(self) -> list[dict[str, Any]]:
        return self.store.list_company_records(self.run_id)

    def record(self, name: str) -> dict[str, Any]:
        matches = [r for r in self.records() if r["name"] == name]
        assert len(matches) == 1, f"expected one record named {name!r}, found {len(matches)}"
        return matches[0]

    def record_name(self, record_id: str) -> str:
        record = self.store.get_company_record(record_id)
        assert record is not None, f"no company record {record_id}"
        return str(record["name"])

    def decision(self, record: dict[str, Any]) -> dict[str, Any]:
        decision = self.store.get_review_decision(record["companyRecordId"])
        assert decision is not None, f"no review decision for {record['companyRecordId']}"
        return decision

    def evidence(self) -> list[dict[str, Any]]:
        return self.store.list_evidence(self.run_id)


def run_steps(harness: Harness, steps: tuple[str, ...] = STEPS) -> CompletedRun:
    """intake, candidates, position, then the given steps, every one through `cli.main`."""
    results = {
        "intake": harness.cli("intake", "--program", "invoice_alpha"),
        "candidates": harness.cli("candidates", "--program", PROGRAM_ID),
        "position": harness.cli("position", "--candidate", CANDIDATE_ID, "--file", str(POSITION_FILE)),
    }
    run_id = (results["position"].json or {}).get("runId", RUN_ID)
    for step in steps:
        results[step] = harness.cli(step, "--run", run_id)
    return CompletedRun(harness, run_id, results)


def run_basic(harness: Harness) -> CompletedRun:
    """intake, candidates, position, then every step."""
    return run_steps(harness, STEPS)


def require_success(completed: CompletedRun) -> CompletedRun:
    """Fail the calling fixture with the first failing command's error."""
    import pytest

    for command, result in completed.results.items():
        if result.code != 0:
            pytest.fail(f"`{command}` exited with {result.code}: {result.stderr.strip()}")
    return completed


def step_counts(completed: CompletedRun, step: str) -> dict[str, Any]:
    """The counts on the step's `step_end` log event."""
    ends = [e for e in completed.harness.log_events(completed.run_id) if e["event"] == "step_end" and e["step"] == step]
    assert len(ends) == 1, f"expected one step_end for {step}, got {len(ends)}"
    return dict(ends[0]["counts"])
