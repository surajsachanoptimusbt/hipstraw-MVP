"""The existence excerpt, built from homepage text without a model (data-model.md, FR-016).

The excerpt is the sentence containing the first occurrence of the company name, or 100 characters on
each side when no sentence boundary is found, capped at 300 characters. It is copied from the page
text, so it passes the citation check exactly when the name occurs on the page.
"""

from __future__ import annotations

import re

from hipstraw_mm.evidence.excerpt_check import _TYPOGRAPHY, MAX_EXCERPT_CHARS

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
