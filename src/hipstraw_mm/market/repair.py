"""Bounded repair loop (Constitution XIV): max 3 attempts, then 'repair exhausted'."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepairResult:
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 0


def bounded_repair(
    *,
    items: dict[str, Any],
    check_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
    repair_fn: Callable[[list[dict[str, Any]]], dict[str, Any]],
    max_attempts: int = 3,
) -> RepairResult:
    failures = check_fn(items)
    if not failures:
        return RepairResult()

    attempts = 0
    while failures and attempts < max_attempts:
        patches = repair_fn(failures)
        for key, patch in patches.items():
            items[key] = patch
        attempts += 1
        failures = check_fn(items)

    result = RepairResult(attempts=attempts)
    if failures:
        seen_keys = set()
        for f in failures:
            key = f["key"]
            if key not in seen_keys:
                result.unresolved.append({"key": key, "reason": "repair exhausted"})
                seen_keys.add(key)
    return result
