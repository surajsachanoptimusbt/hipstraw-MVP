"""Website load outcome and the existence excerpt (data-model.md, FR-008, FR-016, research R4).

The excerpt is the sentence containing the first occurrence of the company name, or 100 characters on
each side when no sentence boundary is found, capped at 300 characters. It is copied from the page
text, so it passes the citation check exactly when the name occurs on the page.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from hipstraw_mm.evidence.excerpt_check import _TYPOGRAPHY, MAX_EXCERPT_CHARS
from hipstraw_mm.models import normalize_company_name, site_host

WebsiteStatus = Literal["resolves", "unreadable", "fails"]
GONE_HTTP_STATUSES = {404, 410}


def website_status(fail_reason: str | None, http_status: int | None) -> WebsiteStatus:
    """Only a website that does not exist fails: HTTP 404 or 410, or a host name that does not resolve.
    Anything else that stops the page being read (robots.txt, 401, 403, 429, server errors, timeouts,
    a redirect to another domain) means it exists but is unreadable (2026-10-07)."""
    if fail_reason is None:
        return "resolves"
    if fail_reason == "dns_error" or (fail_reason == "http_error" and http_status in GONE_HTTP_STATUSES):
        return "fails"
    return "unreadable"


_SENTENCE_END = re.compile(r"[.!?](?=\s)|\n")
_WINDOW = 100


def _name_pattern(name: str) -> re.Pattern[str] | None:
    words = name.translate(_TYPOGRAPHY).split()
    if not words:
        return None
    return re.compile(r"\s+".join(re.escape(w) for w in words), re.IGNORECASE)


def existence_excerpt(text: str, name: str) -> str:
    """The text around the first occurrence of `name`, or "" if the name does not occur."""
    pattern = _name_pattern(name)
    # The typography table maps one character to one, so positions in the folded text match `text`.
    match = pattern.search(text.translate(_TYPOGRAPHY)) if pattern else None
    if match is None:
        return ""
    left = 0
    for boundary in _SENTENCE_END.finditer(text, 0, match.start()):
        left = boundary.end()
    right_match = _SENTENCE_END.search(text, match.end())
    right = right_match.end() if right_match else len(text)
    if left == 0 and right == len(text):  # no sentence boundary at all
        left, right = max(0, match.start() - _WINDOW), min(len(text), match.end() + _WINDOW)
    excerpt = text[left:right].strip()
    if len(excerpt) > MAX_EXCERPT_CHARS:
        start = max(0, match.start() - _WINDOW)
        excerpt = text[start : min(len(text), match.end() + _WINDOW)].strip()[:MAX_EXCERPT_CHARS]
    return excerpt


EXISTENCE_PAGE_WORDS = ("about", "contact")


def find_existence(pages: list[tuple[str, str]], name: str) -> tuple[str, str]:
    """(url, excerpt) for the existence citation (FR-016, 2026-10-07).

    `pages` are (url, text) of pages already fetched in the run: the homepage first, then the
    website's own pages in fetch order. The homepage is used if it names the company; otherwise the
    first page whose path contains "about" or "contact" and names it. No page is fetched for this.
    Returns (homepage url, "") when none names the company.
    """
    home_url, home_text = pages[0]
    excerpt = existence_excerpt(home_text, name)
    if excerpt:
        return home_url, excerpt
    for url, text in pages[1:]:
        path = urlparse(url).path.casefold()
        if any(word in path for word in EXISTENCE_PAGE_WORDS):
            excerpt = existence_excerpt(text, name)
            if excerpt:
                return url, excerpt
    return home_url, ""


def name_matches_domain(name: str, domain: str) -> bool:
    """False when no label of the website's host looks like the company name (research R4), for
    example Addison Health Systems on writepad.com. Then the existence citation alone links them."""
    words = normalize_company_name(name).split()
    compact = "".join(words)
    first = next((w for w in words if w != "the" and len(w) >= 3), "")
    labels = [label.replace("-", "") for label in site_host(domain).split(".")[:-1]]
    for label in labels:
        if len(label) < 3 or label == "www":
            continue
        if compact and (label in compact or compact in label):
            return True
        if first and first in label:
            return True
    return False
