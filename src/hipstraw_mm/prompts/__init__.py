"""Versioned prompt templates for the five model calls (contracts/llm-outputs.md).

Each file is the system message for one call; the user message is the call's JSON input. The file
name (without `.txt`) is the prompt version that each model call logs.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

QUERY_PLAN = "query_plan.v2"
LISTING_EXTRACTION = "listing_extraction.v2"
HOMEPAGE_IDENTITY = "homepage_identity.v2"
COMPANY_EVIDENCE = "company_evidence.v2"
REVIEW_JUDGEMENT = "review_judgement.v1"

VICHARA = "vichara.v1"
VICHARA_COVERAGE = "vichara_coverage.v1"
VICHARA_REPAIR = "vichara_repair.v1"
VICHARA_PROPOSE = "vichara_propose.v1"
GRAPH_LEVEL = "graph_level.v2"
GRAPH_COVERAGE = "graph_coverage.v1"
GRAPH_REPAIR = "graph_repair.v1"
LINK_VERIFICATION = "link_verification.v1"
PATH_ASSESSMENT = "path_assessment.v1"
BEAM_SCORING = "beam_scoring.v1"
BUYER_ROLES = "buyer_roles.v2"


@cache
def load(version: str) -> str:
    return resources.files(__package__).joinpath(f"{version}.txt").read_text(encoding="utf-8")


def messages(version: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    """System message from the template, user message with the call's explicit inputs as JSON."""
    return [
        {"role": "system", "content": load(version)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
    ]
