"""Versioned prompt templates for the five model calls (contracts/llm-outputs.md).

Each file is the system message for one call; the user message is the call's JSON input. The file
name (without `.txt`) is the prompt version that each model call logs.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

QUERY_PLAN = "query_plan.v1"
LISTING_EXTRACTION = "listing_extraction.v1"
HOMEPAGE_IDENTITY = "homepage_identity.v1"
COMPANY_EVIDENCE = "company_evidence.v1"
REVIEW_JUDGEMENT = "review_judgement.v1"


@cache
def load(version: str) -> str:
    return resources.files(__package__).joinpath(f"{version}.txt").read_text(encoding="utf-8")


def messages(version: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    """System message from the template, user message with the call's explicit inputs as JSON."""
    return [
        {"role": "system", "content": load(version)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
    ]
