"""T015: Adapter contract tests replaying real recordings (Constitution IV).

They replay tests/fixtures/recorded/real/, written once by tests/fixtures/record_real.py with real
keys, through the real adapters, to prove the adapters parse real Brave, page, and OpenAI responses.
The tests are skipped until that recording exists (T030).
"""

import json
import os
import re
from pathlib import Path

import pytest

from hipstraw_mm import llm_schemas
from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.adapters.search import BraveSearch

REAL_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "real"
MANIFEST = REAL_DIR / "manifest.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST.exists(), reason="Real recordings not yet created: run tests/fixtures/record_real.py (T030)"
)


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture
def replay():
    return ReplayStore(REAL_DIR, mode="replay")


def test_brave_returns_results(replay, manifest):
    results = BraveSearch(replay, denylist_domains=[]).search(manifest["query"], count=10)
    assert len(results) >= 1
    assert all(r.url.startswith("http") and r.title for r in results)


def test_fetch_returns_page_and_robots_decision(replay, manifest):
    fetcher = Fetcher(
        replay_store=replay,
        denylist_domains=[],
        user_agent=manifest["userAgent"],
        timeout_seconds=15,
        max_bytes=2_000_000,
    )
    assert fetcher.robots_allowed(manifest["pageUrl"]) is True
    page = fetcher.fetch(manifest["pageUrl"])
    assert page.fail_reason is None
    assert page.status == 200
    assert page.text
    assert isinstance(page.links, list)


@pytest.mark.parametrize(
    "schema_name", ["QueryPlan", "ListingExtraction", "HomepageIdentity", "CompanyEvidence", "ReviewJudgement"]
)
def test_schema_parses_from_recording(replay, manifest, schema_name):
    schema = getattr(llm_schemas, schema_name)
    llm = LLMClient(model=None, replay=replay)
    parsed = llm.parse(schema, messages=[], match_key=manifest["modelKeys"][schema_name], prompt_version="real")
    assert isinstance(parsed, schema)


def test_no_secrets_in_recordings():
    key_like = re.compile(r"sk-[A-Za-z0-9_-]{16,}|BSA[A-Za-z0-9_-]{16,}")
    env_values = [v for v in (os.environ.get("OPENAI_API_KEY"), os.environ.get("BRAVE_API_KEY")) if v and len(v) >= 8]
    for f in REAL_DIR.rglob("*.json"):
        content = f.read_text(encoding="utf-8")
        assert not key_like.search(content), f"key-like string in {f.name}"
        for value in env_values:
            assert value not in content, f"environment key value in {f.name}"
