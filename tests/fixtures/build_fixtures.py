"""T032: build replay recordings from a scenario file in tests/fixtures/scenarios/.

    python tests/fixtures/build_fixtures.py            # every scenario
    python tests/fixtures/build_fixtures.py basic      # one scenario

Writes tests/fixtures/recorded/<name>/ in the record-mode format ({matchKey, request, response}).
It checks the scenario first and writes nothing if a check fails:
- every fetched page is on a `.test` domain, and every other search result is `.test` or denylisted
  (Constitution IX);
- every excerpt marked verbatim passes the citation check against the page text the system will see,
  and every excerpt marked `verbatim: false` fails it;
- every link points at a link on its page, every claim at a page given to the model;
- every model response validates against its schema.

Scenario sections beyond the basic ones (added for Phase 4):
- `robots`: per-origin robots.txt, as text or `{status, text}`, instead of allow-all;
- `unreachable`: per-origin `dns` (the host name does not resolve) or `connect` (the connection
  fails); its robots.txt recording is that error, so nothing on it is ever fetched;
- `signalSearches`: verify-step searches (research R7) with explicit results, keyed by query;
- `noSignalResults`: `{name, domain}` entries whose three research R7 signal searches return nothing.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel

from hipstraw_mm import llm_schemas
from hipstraw_mm.adapters.fetch import html_to_text_and_links
from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.config import load_source_policy
from hipstraw_mm.evidence.excerpt_check import check_excerpt, normalize
from hipstraw_mm.models import host_of, is_denylisted

FIXTURES_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = FIXTURES_DIR / "scenarios"
RECORDED_DIR = FIXTURES_DIR / "recorded"
TEST_SOURCE_POLICY = FIXTURES_DIR / "config" / "source_policy.yaml"

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"
STRUCTURED_FIELDS = {"hq", "employees", "revenue", "parent", "parent_employees", "parent_revenue"}
RANKING_FIELDS = ("location", "metroMatch", "positionMatch")


def signal_queries(name: str, domain: str) -> list[str]:
    """The three verify-step signal searches, in order (research R7). Their strings are match keys."""
    return [
        f'"{name}" accounts payable OR procurement job',
        f'"{name}" invoice automation OR "AI agents" finance',
        f"site:{domain} careers",
    ]


class ScenarioError(Exception):
    pass


def _model_response(schema: type[BaseModel], obj: dict[str, Any], model: str) -> dict[str, Any]:
    try:
        content = schema.model_validate(obj).model_dump_json()
    except ValueError as exc:
        raise ScenarioError(f"{schema.__name__} response does not match its schema: {exc}") from exc
    return {"content": content, "refusal": None, "finishReason": "stop", "model": model}


def _require_cited(excerpt: str, text: str, where: str, *, name: str | None = None, value: str | None = None) -> None:
    result = check_excerpt(excerpt, text, value)
    if result.status != "pass":
        raise ScenarioError(f"{where}: excerpt fails the citation check ({result.reason}): {excerpt!r}")
    if name is not None and normalize(name) not in normalize(excerpt):
        raise ScenarioError(f"{where}: excerpt does not contain the name {name!r}")


def build(scenario_path: Path, out_dir: Path) -> int:
    """Check the scenario and write its recordings to `out_dir`. Returns the number of files written."""
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    name = scenario_path.stem
    if out_dir.name == "real":
        raise ScenarioError("refusing to overwrite the real adapter recordings")
    denylist = load_source_policy(TEST_SOURCE_POLICY).denylistDomains
    model = scenario["model"]
    fetched_at = scenario["fetchedAt"]
    audit = {"builtBy": "tests/fixtures/build_fixtures.py", "scenario": f"tests/fixtures/scenarios/{name}.yaml"}
    records: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []

    # Pages and robots.txt
    pages: dict[str, tuple[str, list[dict[str, str]]]] = {}
    origins: set[str] = set()
    for url, page in scenario["pages"].items():
        if not host_of(url).endswith(".test"):
            raise ScenarioError(f"page {url} is not on a .test domain")
        html = f"<html><body>\n{page['html']}</body></html>"
        pages[url] = html_to_text_and_links(html, url)
        response = {
            "status": page.get("status", 200),
            "headers": {"content-type": "text/html; charset=utf-8"},
            "text": html,
            "fetchedAt": fetched_at,
        }
        records.append(("fetch", url, {"url": url, **audit}, response))
        parsed = urlparse(url)
        origins.add(f"{parsed.scheme}://{parsed.netloc}")
    unreachable: dict[str, str] = scenario.get("unreachable", {})
    robots: dict[str, Any] = scenario.get("robots", {})
    for origin in unreachable:
        if origin in origins:
            raise ScenarioError(f"{origin} is unreachable but has pages")
    for origin in sorted(origins | set(robots) | set(unreachable)):
        if not host_of(origin).endswith(".test"):
            raise ScenarioError(f"robots origin {origin} is not on a .test domain")
        robots_url = f"{origin}/robots.txt"
        if origin in unreachable:
            kind = unreachable[origin]
            if kind not in ("dns", "connect"):
                raise ScenarioError(f"unreachable {origin}: expected dns or connect, got {kind!r}")
            response = {"status": None, "error": "ConnectError", "dnsFailed": kind == "dns"}
        else:
            spec = robots.get(origin, ROBOTS_ALLOW_ALL)
            if isinstance(spec, str):
                spec = {"status": 200, "text": spec}
            response = {
                "status": spec["status"],
                "headers": {"content-type": "text/plain"},
                "text": spec.get("text", ""),
            }
        records.append(("fetch", robots_url, {"url": robots_url, **audit}, response))

    # QueryPlan and search results
    queries = scenario["queries"]
    plan = {"queries": [{"query": q["query"], "purpose": q["purpose"]} for q in queries]}
    key = f"QueryPlan:{scenario['candidateId']}"
    records.append(
        ("model", key, {"schema": "QueryPlan", **audit}, _model_response(llm_schemas.QueryPlan, plan, model))
    )
    for q in queries:
        results = []
        for r in q["results"]:
            if not (host_of(r["url"]).endswith(".test") or is_denylisted(r["url"], denylist)):
                raise ScenarioError(f"search result {r['url']} is neither a .test domain nor denylisted")
            results.append({"url": r["url"], "title": r["title"], "description": r["snippet"]})
        request = {"params": {"q": q["query"]}, **audit}
        records.append(("search", q["query"], request, {"web": {"results": results}}))

    # Signal searches (verify step, research R7)
    signal_searches: dict[str, list[dict[str, str]]] = dict(scenario.get("signalSearches", {}))
    for company in scenario.get("noSignalResults", []):
        for query in signal_queries(company["name"], company["domain"]):
            signal_searches.setdefault(query, [])
    for query, found in signal_searches.items():
        results = []
        for r in found:
            if not (host_of(r["url"]).endswith(".test") or is_denylisted(r["url"], denylist)):
                raise ScenarioError(f"signal result {r['url']} is neither a .test domain nor denylisted")
            results.append({"url": r["url"], "title": r["title"], "description": r["snippet"]})
        request = {"params": {"q": query}, **audit}
        records.append(("search", query, request, {"web": {"results": results}}))

    # ListingExtraction
    for url, entries in scenario.get("listings", {}).items():
        if url not in pages:
            raise ScenarioError(f"listing {url} has no page")
        text, links = pages[url]
        link_ids = {link["href"]: link["linkId"] for link in links}
        companies = []
        for entry in entries:
            where = f"listing {url} / {entry['name']}"
            _require_cited(entry["excerpt"], text, where, name=entry["name"])
            link = entry["link"]
            if link is not None and link not in link_ids:
                raise ScenarioError(f"{where}: {link} is not a link on the page")
            companies.append(
                {
                    "name": entry["name"],
                    "linkId": link_ids[link] if link else None,
                    "excerpt": entry["excerpt"],
                    **{k: entry[k] for k in RANKING_FIELDS if k in entry},
                }
            )
        response = _model_response(llm_schemas.ListingExtraction, {"companies": companies}, model)
        records.append(("model", f"ListingExtraction:{url}", {"schema": "ListingExtraction", **audit}, response))

    # HomepageIdentity
    for url, identity in scenario.get("homepages", {}).items():
        if url not in pages:
            raise ScenarioError(f"homepage {url} has no page")
        if identity["isCompanyHomepage"]:
            _require_cited(identity["excerpt"], pages[url][0], f"homepage {url}", name=identity["name"])
        response = _model_response(llm_schemas.HomepageIdentity, identity, model)
        records.append(("model", f"HomepageIdentity:{url}", {"schema": "HomepageIdentity", **audit}, response))

    # CompanyEvidence
    for domain, ev in scenario.get("evidence", {}).items():
        source_ids = {}
        for i, page_url in enumerate(ev["pages"], start=1):
            if page_url not in pages:
                raise ScenarioError(f"evidence {domain}: page {page_url} is not in `pages`")
            source_ids[page_url] = f"s{i}"
        claims = []
        for claim in ev["claims"]:
            where = f"evidence {domain} / {claim['claimId']}"
            if claim["page"] not in source_ids:
                raise ScenarioError(f"{where}: {claim['page']} is not one of the pages given to the model")
            value = claim["claimValue"] if claim["claimField"] in STRUCTURED_FIELDS else None
            result = check_excerpt(claim["excerpt"], pages[claim["page"]][0], value, claim_field=claim["claimField"])
            if claim["verbatim"] and result.status != "pass":
                raise ScenarioError(f"{where}: verbatim excerpt fails ({result.reason})")
            if not claim["verbatim"] and result.status == "pass":
                raise ScenarioError(f"{where}: excerpt marked verbatim: false passes the check")
            claims.append(
                {
                    "claimId": claim["claimId"],
                    "claimField": claim["claimField"],
                    "claimValue": claim["claimValue"],
                    "sourceId": source_ids[claim["page"]],
                    "excerpt": claim["excerpt"],
                }
            )
        claim_ids = {c["claimId"] for c in claims}
        for item in ev["fitClaims"] + ev["interestSignals"]:
            if not set(item["claimIds"]) <= claim_ids:
                raise ScenarioError(f"evidence {domain}: {item['statement']!r} cites an unknown claim ID")
        obj = {
            "claims": claims,
            "fitClaims": ev["fitClaims"],
            "interestSignals": ev["interestSignals"],
            "falsifier": ev["falsifier"],
        }
        response = _model_response(llm_schemas.CompanyEvidence, obj, model)
        records.append(("model", f"CompanyEvidence:{domain}", {"schema": "CompanyEvidence", **audit}, response))

    # ReviewJudgement
    for key_suffix, judgement in scenario.get("judgements", {}).items():
        record_id = f"{scenario['runId']}__{key_suffix}"
        response = _model_response(llm_schemas.ReviewJudgement, judgement, model)
        records.append(("model", f"ReviewJudgement:{record_id}", {"schema": "ReviewJudgement", **audit}, response))

    keys = [(kind, key) for kind, key, _, _ in records]
    if len(set(keys)) != len(keys):
        raise ScenarioError("two recordings share a match key")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    store = ReplayStore(out_dir, mode="record")
    for kind, key, request, response in records:
        store.put(kind, key, request, response)
    return len(records)


def main(argv: list[str]) -> int:
    names = argv or sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))
    for name in names:
        try:
            count = build(SCENARIOS_DIR / f"{name}.yaml", RECORDED_DIR / name)
        except (ScenarioError, FileNotFoundError) as exc:
            print(f"error: {name}: {exc}", file=sys.stderr)
            return 1
        print(f"{name}: {count} files in {RECORDED_DIR / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
