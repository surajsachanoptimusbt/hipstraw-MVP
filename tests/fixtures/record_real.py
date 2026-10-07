"""T030: record one real response per adapter for the contract tests (Constitution IV).

Run once by a team member with real keys (quickstart.md, "Recording the real adapter responses"):

    $env:OPENAI_API_KEY="..."; $env:LLM_MODEL="..."; $env:BRAVE_API_KEY="..."
    $env:HIPSTRAW_REPLAY="record"
    python tests\\fixtures\\record_real.py

It makes exactly one Brave query, one page fetch (plus that host's robots.txt, and any same-site
redirect hops), and one OpenAI parse per schema. Files go to tests/fixtures/recorded/real/ with
secrets redacted; the script fails if any key value appears in a written file. Commit the files.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from hipstraw_mm import llm_schemas
from hipstraw_mm.adapters.fetch import Fetcher
from hipstraw_mm.adapters.llm import LLMClient
from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.adapters.search import BraveSearch
from hipstraw_mm.config import load_config
from hipstraw_mm.logging_setup import secret_values
from hipstraw_mm.models import site_host

ROOT = Path(__file__).resolve().parents[2]
REAL_DIR = Path(__file__).resolve().parent / "recorded" / "real"
QUERY = "SaaS companies Atlanta"
MAX_TEXT = 6000

SYSTEM = (
    "Use only the text provided by the user. Copy every excerpt verbatim from that text, at most 300 "
    "characters. Never output person fields, email addresses, or phone numbers. Return only the schema."
)


def _messages(task: str, payload: dict[str, object]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{task}\n\n{json.dumps(payload, ensure_ascii=False)}"},
    ]


def main() -> int:
    missing = [k for k in ("OPENAI_API_KEY", "LLM_MODEL", "BRAVE_API_KEY") if not os.environ.get(k)]
    if missing:
        print(f"error: set {', '.join(missing)} first", file=sys.stderr)
        return 1
    if os.environ.get("HIPSTRAW_REPLAY") != "record":
        print("error: set HIPSTRAW_REPLAY=record to confirm you want live calls", file=sys.stderr)
        return 1

    config = load_config(ROOT / "config")
    policy = config.source_policy
    if REAL_DIR.exists():
        shutil.rmtree(REAL_DIR)
    REAL_DIR.mkdir(parents=True)
    recorder = ReplayStore(REAL_DIR, mode="record")
    probe = ReplayStore(None, mode="off")  # robots checks of skipped results are not recorded

    def fetcher(store: ReplayStore) -> Fetcher:
        return Fetcher(
            replay_store=store,
            denylist_domains=policy.denylistDomains,
            user_agent=policy.userAgent,
            timeout_seconds=config.run.fetch.timeoutSeconds,
            max_bytes=config.run.fetch.maxBytes,
            per_host_delay_seconds=config.run.fetch.perHostDelaySeconds,
        )

    # 1. One Brave query.
    results = BraveSearch(recorder, denylist_domains=policy.denylistDomains).search(QUERY, count=10)
    print(f"search: {len(results)} results")

    # 2. One page fetch (plus its robots.txt) of the first result whose robots.txt allows it.
    checker = fetcher(probe)
    page_url = next((r.url for r in results if checker.robots_allowed(r.url)), None)
    if page_url is None:
        print("error: no result allows fetching by robots.txt", file=sys.stderr)
        return 1
    page = fetcher(recorder).fetch(page_url)
    if not page.ok:
        print(f"error: fetch of {page_url} failed: {page.fail_reason}", file=sys.stderr)
        return 1
    text = (page.text or "")[:MAX_TEXT]
    links = (page.links or [])[:40]
    print(f"fetch: {page_url} ({len(page.text or '')} chars, {len(page.links or [])} links)")

    # 3. One parse per schema.
    llm = LLMClient(model=os.environ["LLM_MODEL"], replay=recorder)
    domain = site_host(page.final_url or page_url)
    keys = {
        "QueryPlan": "real",
        "ListingExtraction": page_url,
        "HomepageIdentity": page_url,
        "CompanyEvidence": domain,
        "ReviewJudgement": "real-synthetic",
    }
    llm.parse(
        llm_schemas.QueryPlan,
        _messages(
            "Plan at most 3 web search queries that find small SaaS companies headquartered in Atlanta.",
            {"maxQueries": 3},
        ),
        keys["QueryPlan"],
        "record-real",
    )
    llm.parse(
        llm_schemas.ListingExtraction,
        _messages("List the companies named on this page.", {"url": page_url, "text": text, "links": links}),
        keys["ListingExtraction"],
        "record-real",
    )
    llm.parse(
        llm_schemas.HomepageIdentity,
        _messages("Is this page a single company's own homepage?", {"url": page_url, "text": text}),
        keys["HomepageIdentity"],
        "record-real",
    )
    llm.parse(
        llm_schemas.CompanyEvidence,
        _messages(
            "Extract cited claims about the main company on this page.",
            {
                "domain": domain,
                "pages": [{"sourceId": "s1", "url": page_url, "sourceType": "company_site", "text": text}],
            },
        ),
        keys["CompanyEvidence"],
        "record-real",
    )
    llm.parse(
        llm_schemas.ReviewJudgement,
        _messages(
            "Judge whether the fit holds and whether the falsifier is met, citing only these evidence IDs.",
            {
                "company": "Example Ledger Co (synthetic)",
                "falsifier": "The company is a subsidiary of a Fortune 500 enterprise.",
                "evidence": [
                    {
                        "evidenceId": "ev_synthetic_1",
                        "claimField": "hq",
                        "claimValue": "Atlanta, GA",
                        "excerpt": "Headquartered in Atlanta, GA",
                    },
                    {
                        "evidenceId": "ev_synthetic_2",
                        "claimField": "signal_pain",
                        "claimValue": "AP hiring",
                        "excerpt": "We are hiring an Accounts Payable Specialist",
                    },
                ],
            },
        ),
        keys["ReviewJudgement"],
        "record-real",
    )
    print(f"model: {llm.calls} calls")

    manifest = {"query": QUERY, "pageUrl": page_url, "userAgent": policy.userAgent, "modelKeys": keys}
    (REAL_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    leaks = [f for f in REAL_DIR.rglob("*.json") if any(s in f.read_text(encoding="utf-8") for s in secret_values())]
    if leaks:
        print(
            f"error: key values found in {[str(f) for f in leaks]}; delete {REAL_DIR} and investigate", file=sys.stderr
        )
        return 1
    print(f"done: {sum(1 for _ in REAL_DIR.rglob('*.json'))} files in {REAL_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
