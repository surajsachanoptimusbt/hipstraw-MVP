"""Page fetcher: denylist, robots.txt, HTML only, size cap, redirect rule (research R3, FR-002, FR-008).

Redirects are followed by this module, one hop at a time, so every hop is checked against the
denylist and robots.txt and each hop is its own replay recording.
"""

from __future__ import annotations

import functools
import hashlib
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.models import is_denylisted, same_company_or_subdomain

MAX_REDIRECTS = 5
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_DROP_TAGS = ["script", "style", "noscript", "template", "svg"]
# Elements that start a new line, as a browser renders them. Inline elements (a, strong, span, ...)
# never break a line, so "<strong>Acme</strong>: x" reads "Acme: x", as the model and a reader see it.
_BLOCK_TAGS = [
    "address", "article", "aside", "blockquote", "body", "caption", "dd", "details", "dialog", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hgroup", "hr", "html", "legend", "li", "main", "nav", "ol", "option", "p", "pre",
    "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "title", "tr", "ul",
]  # fmt: skip
_LINE_BREAK = "\x00"  # placeholder; NUL is removed from the input first, so it marks only block boundaries


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    status: int | None = None
    text: str | None = None
    links: list[dict[str, str]] | None = None
    content_sha256: str | None = None
    fetched_at: str | None = None
    # robots_disallowed | denylisted | not_html | too_large | http_error | network_error | dns_error
    # | redirect_off_site | too_many_redirects | bad_url
    fail_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.fail_reason is None and self.text is not None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def html_to_text_and_links(html: str, base_url: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html.replace(_LINE_BREAK, " "), "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base_url, str(anchor["href"]).strip()))[0]
        if urlparse(href).scheme not in ("http", "https") or href in seen:
            continue
        seen.add(href)
        anchor_text = " ".join(anchor.get_text(" ").split())[:200]
        links.append({"linkId": f"L{len(links) + 1}", "href": href, "anchorText": anchor_text})
    for br in soup.find_all("br"):
        br.replace_with(_LINE_BREAK)
    for block in soup.find_all(_BLOCK_TAGS):
        block.insert_before(_LINE_BREAK)
        block.insert_after(_LINE_BREAK)
    # Whitespace inside a line collapses to one space, as in a browser; only block boundaries break lines.
    raw = soup.get_text().replace(_LINE_BREAK + _LINE_BREAK, _LINE_BREAK)
    lines = (" ".join(part.split()) for part in raw.split(_LINE_BREAK))
    return "\n".join(line for line in lines if line), links


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _host_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return True


def _transport_error(url: str, exc: httpx.HTTPError) -> dict[str, Any]:
    """A failed request. A connection that failed because the host name does not resolve is recorded
    with `dnsFailed`, because only a missing domain shows the website is gone (research R3)."""
    raw: dict[str, Any] = {"status": None, "error": type(exc).__name__}
    host = urlparse(url).hostname
    if isinstance(exc, httpx.ConnectError) and host and not _host_resolves(host):
        raw["dnsFailed"] = True
    return raw


class Fetcher:
    """One fetcher per run: its robots.txt cache and per-host delays last for that run."""

    def __init__(
        self,
        replay_store: ReplayStore,
        denylist_domains: list[str],
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
        per_host_delay_seconds: float = 0.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.replay = replay_store
        self.denylist = denylist_domains
        self.user_agent = user_agent
        self.timeout = timeout_seconds
        self.max_bytes = max_bytes
        self.per_host_delay = per_host_delay_seconds
        self._sleep = sleep
        self._clock = clock
        self._robots: dict[str, RobotFileParser | bool] = {}
        self._dns_failed: set[str] = set()  # origins whose robots.txt request found no such host
        self._last_request: dict[str, float] = {}
        self._http: httpx.Client | None = None
        self.fetches = 0

    # -- public ------------------------------------------------------------

    def fetch(self, url: str, *, same_company_only: bool = False) -> FetchResult:
        """Fetch one page. With `same_company_only`, redirects must stay on the URL's company key."""
        self.fetches += 1
        result = FetchResult(url=url)
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            result.final_url = current
            if urlparse(current).scheme not in ("http", "https"):
                result.fail_reason = "bad_url"
                return result
            if is_denylisted(current, self.denylist):
                result.fail_reason = "denylisted"
                return result
            if not self.robots_allowed(current):
                result.fail_reason = "dns_error" if _origin(current) in self._dns_failed else "robots_disallowed"
                return result

            raw = self.replay.call("fetch", current, {"url": current}, functools.partial(self._live_get, current))
            if raw.get("error"):
                result.fail_reason = "dns_error" if raw.get("dnsFailed") else "network_error"
                return result
            status = int(raw["status"])
            headers = {k.lower(): v for k, v in (raw.get("headers") or {}).items()}
            result.status = status

            if 300 <= status < 400:
                location = headers.get("location")
                if not location:
                    result.fail_reason = "http_error"
                    return result
                target = urljoin(current, location)
                if same_company_only and not same_company_or_subdomain(url, target):
                    result.final_url = target
                    result.fail_reason = "redirect_off_site"
                    return result
                result.redirect_chain.append(current)
                current = target
                continue

            if not 200 <= status < 300:
                result.fail_reason = "http_error"
                return result
            content_type = str(headers.get("content-type", "")).lower()
            if not content_type.startswith(_HTML_TYPES):
                result.fail_reason = "not_html"
                return result
            body = str(raw.get("text") or "")
            if raw.get("tooLarge") or len(body.encode("utf-8")) > self.max_bytes:
                result.fail_reason = "too_large"
                return result

            text, links = html_to_text_and_links(body, current)
            result.text = text
            result.links = links
            result.content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            result.fetched_at = str(raw.get("fetchedAt") or _utc_now())
            return result

        result.fail_reason = "too_many_redirects"
        return result

    def robots_allowed(self, url: str) -> bool:
        origin = _origin(url)
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            raw = self.replay.call("fetch", robots_url, {"url": robots_url}, lambda: self._live_robots(robots_url))
            if raw.get("dnsFailed"):
                self._dns_failed.add(origin)
            self._robots[origin] = self._parse_robots(raw)
        entry = self._robots[origin]
        if isinstance(entry, bool):
            return entry
        return entry.can_fetch(self.user_agent, url)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _parse_robots(raw: dict[str, Any]) -> RobotFileParser | bool:
        status = raw.get("status")
        if raw.get("error") or status is None:
            return False  # unknown rules: do not fetch
        status = int(status)
        if status in (401, 403) or status >= 500:
            return False
        if 400 <= status < 500:
            return True  # no robots.txt: everything allowed
        parser = RobotFileParser()
        parser.parse(str(raw.get("text") or "").splitlines())
        return parser

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(headers={"User-Agent": self.user_agent}, timeout=self.timeout)
        return self._http

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self.per_host_delay - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _live_robots(self, robots_url: str) -> dict[str, Any]:
        self._throttle(robots_url)
        try:
            resp = self._client().get(robots_url, follow_redirects=True)
        except httpx.HTTPError as exc:
            return _transport_error(robots_url, exc)
        return {
            "status": resp.status_code,
            "text": resp.text[:500_000],
            "headers": {"content-type": resp.headers.get("content-type", "")},
        }

    def _live_get(self, url: str) -> dict[str, Any]:
        self._throttle(url)
        try:
            with self._client().stream("GET", url, follow_redirects=False) as resp:
                headers = {"content-type": resp.headers.get("content-type", "")}
                if resp.headers.get("location"):
                    headers["location"] = resp.headers["location"]
                out: dict[str, Any] = {
                    "status": resp.status_code,
                    "headers": headers,
                    "text": "",
                    "fetchedAt": _utc_now(),
                }
                is_html = headers["content-type"].lower().startswith(_HTML_TYPES)
                if not 200 <= resp.status_code < 300 or not is_html:
                    return out
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > self.max_bytes:
                        out["tooLarge"] = True
                        return out
                try:
                    out["text"] = body.decode(resp.encoding or "utf-8", errors="replace")
                except LookupError:
                    out["text"] = body.decode("utf-8", errors="replace")
                return out
        except httpx.HTTPError as exc:
            return _transport_error(url, exc)
