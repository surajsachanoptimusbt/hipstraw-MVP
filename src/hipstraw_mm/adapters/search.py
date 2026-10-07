"""Brave Search API client (research R2). The system issues the queries; the model never searches."""

from __future__ import annotations

import html
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from hipstraw_mm.adapters.replay import ReplayStore
from hipstraw_mm.errors import ConfigError, ExternalServiceError
from hipstraw_mm.models import is_denylisted

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str


def _plain(text: str) -> str:
    return html.unescape(_TAG.sub("", text or "")).strip()


class BraveSearch:
    def __init__(
        self,
        replay: ReplayStore,
        denylist_domains: list[str],
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.replay = replay
        self.denylist = denylist_domains
        self.timeout = timeout_seconds
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.calls = 0

    def search(self, query: str, count: int) -> list[SearchResult]:
        self.calls += 1
        request = {"url": ENDPOINT, "params": {"q": query, "count": count}}
        data = self.replay.call("search", query, request, lambda: self._live(query, count))
        out: list[SearchResult] = []
        for item in (data.get("web") or {}).get("results") or []:
            url = str(item.get("url") or "")
            if not url.startswith(("http://", "https://")) or is_denylisted(url, self.denylist):
                continue
            out.append(
                SearchResult(url=url, title=_plain(item.get("title", "")), snippet=_plain(item.get("description", "")))
            )
        return out[:count]

    def _live(self, query: str, count: int) -> dict[str, Any]:
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise ConfigError("BRAVE_API_KEY is not set")
        headers = {"X-Subscription-Token": key, "Accept": "application/json"}
        params: dict[str, str | int] = {"q": query, "count": min(count, 20)}
        last = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = httpx.get(ENDPOINT, params=params, headers=headers, timeout=self.timeout)
            except httpx.HTTPError as exc:
                last = type(exc).__name__
            else:
                if resp.status_code == 200:
                    result: dict[str, Any] = resp.json()
                    return result
                last = f"HTTP {resp.status_code}"
                if resp.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < self.max_attempts:
                self.sleep(1.5 * attempt)
        raise ExternalServiceError(f"Brave search failed for {query!r}: {last}")
