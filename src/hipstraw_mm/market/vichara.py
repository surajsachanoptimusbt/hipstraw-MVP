"""Dimension deliberation (vichara) with basis grounding checks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from hipstraw_mm.evidence.excerpt_check import normalize
from hipstraw_mm.market.router import Check


@dataclass(frozen=True)
class GroundingResult:
    status: str
    reason: str | None = None


def check_basis_grounding(basis_text: str, objective_text: str) -> GroundingResult:
    if not basis_text or not basis_text.strip():
        return GroundingResult(status="fail", reason="empty_basis")
    normalized_basis = normalize(basis_text)
    normalized_objective = normalize(objective_text)
    if normalized_basis in normalized_objective:
        return GroundingResult(status="pass")
    return GroundingResult(status="fail", reason="basis_not_in_objective")


def check_item_grounding(item: dict[str, Any], objective_text: str) -> list[dict[str, Any]]:
    if item.get("status") != "answered":
        return []
    results = []
    for basis_text in item.get("basis", []):
        gr = check_basis_grounding(basis_text, objective_text)
        results.append({"basis": basis_text, "status": gr.status, "reason": gr.reason})
    return [r for r in results if r["status"] == "fail"]


_TOKEN = re.compile(r"\S+")
_DOC_HEADER = re.compile(r"\[Document: ([^\]]+)\]")
_NOT_ALNUM = re.compile(r"[^0-9a-z]+")


def _char_kind(ch: str) -> str:
    if unicodedata.category(ch) == "Co":
        return "private-use character (a PDF font glyph with no standard meaning)"
    try:
        return unicodedata.name(ch).lower()
    except ValueError:
        return "unnamed character"


def explain_grounding_miss(quote: str, objective_text: str) -> dict[str, Any]:
    """Why a quote failed the word-for-word check: the closest passage, words matched, the first
    difference, and unusual characters. Explains a failure; never turns it into a pass.

    Words are aligned on their letters and digits only, so a word that differs only by punctuation or a
    special character still lines up and the difference is reported precisely.
    """
    doc = [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(objective_text)]
    q_words = _TOKEN.findall(quote)
    q_norm = [normalize(w) for w in q_words]
    q_loose = [_NOT_ALNUM.sub("", w) for w in q_norm]
    d_norm = [normalize(t) for _, _, t in doc]
    d_loose = [_NOT_ALNUM.sub("", t) for t in d_norm]
    n = len(q_words)
    anchor = SequenceMatcher(None, d_loose, q_loose, autojunk=False).find_longest_match(0, len(d_loose), 0, n)
    if not n or not doc or anchor.size == 0:
        return {"verdict": "not_found", "quoteWords": n, "matchedWords": 0, "closest": None, "location": None,
                "differs": None, "characters": [],
                "explanation": "No word of the quote appears in the objective text."}

    slack = max(3, n // 4)
    lo = max(0, anchor.a - anchor.b - slack)
    hi = min(len(doc), anchor.a + (n - anchor.b) + slack)
    sm = SequenceMatcher(None, d_loose[lo:hi], q_loose, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    matched = sum(b.size for b in blocks)
    ops = sm.get_opcodes()
    while ops and ops[0][0] == "delete":   # passage words before the quote starts
        ops = ops[1:]
    while ops and ops[-1][0] == "delete":  # passage words after the quote ends
        ops = ops[:-1]

    # The closest passage: from the first matched word to where the quote's words run out.
    first = blocks[0]
    last = blocks[-1]
    p_start = lo + first.a
    p_end = min(hi, lo + last.a + last.size + (n - (last.b + last.size)))
    closest = objective_text[doc[p_start][0]:doc[p_end - 1][1]]
    headers = [h for h in _DOC_HEADER.finditer(objective_text) if h.start() < doc[p_start][0]]
    location = headers[-1].group(1) if headers else "program objective"

    differs: dict[str, Any] | None = None
    characters: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            for k in range(i2 - i1):
                di, qi = lo + i1 + k, j1 + k
                if d_norm[di] == q_norm[qi]:
                    continue
                if differs is None:
                    differs = {"position": qi + 1, "kind": "characters", "quote": q_words[qi],
                               "document": doc[di][2], "passageWord": di - p_start + 1}
                for ch in doc[di][2]:
                    code = f"U+{ord(ch):04X}"
                    if ord(ch) > 127 and ch not in q_words[qi] and all(c["code"] != code for c in characters):
                        characters.append({"char": ch, "code": code, "kind": _char_kind(ch),
                                           "documentWord": doc[di][2], "quoteWord": q_words[qi]})
            continue
        if differs is None or differs["kind"] == "characters":
            shown = max(1, j2 - j1)
            doc_words = [doc[lo + i][2] for i in range(i1, min(i2, i1 + shown))]
            differs = {
                "position": j1 + 1,
                "kind": {"replace": "replaced", "insert": "not in document", "delete": "only in document"}[tag],
                "quote": " ".join(q_words[j1:j2][:6]) or None,
                "document": " ".join(doc_words) or None,
                "passageWord": (lo + i1 - p_start + 1) if i2 > i1 else None,
            }
            break

    exact = matched == n and all(tag == "equal" for tag, *_ in ops)
    if exact:
        verdict = "near_miss"
        explanation = (f"All {n} words are in {location} in the same order; only punctuation or special "
                       "characters differ")
        if characters:
            c = characters[0]
            explanation += f": the document has {c['code']} ({c['kind']}) where the quote has {c['quoteWord']!r}"
        elif differs:
            explanation += f": the document has {differs['document']!r} where the quote has {differs['quote']!r}"
        explanation += ". Probably a real quote that the exact match misses."
    elif matched * 2 >= n:
        verdict = "partial"
        assert differs is not None
        if differs["kind"] == "not in document":
            what = f"the quote adds {differs['quote']!r}, which the document does not have"
        elif differs["kind"] == "only in document":
            what = f"the document has {differs['document']!r}, which the quote leaves out"
        else:
            what = f"the quote says {differs['quote']!r} where the document says {differs['document']!r}"
        explanation = (f"{matched} of {n} words match the closest passage in {location}. First difference at "
                       f"quote word {differs['position']}: {what}.")
    else:
        verdict = "not_found"
        explanation = (f"The closest passage shares only {matched} of the quote's {n} words in order. "
                       "The quote is paraphrased or not in the text.")
    return {"verdict": verdict, "quoteWords": n, "matchedWords": matched,
            "closest": closest if len(closest) <= 360 else closest[:359] + "…", "location": location,
            "differs": differs, "characters": characters, "explanation": explanation}


def vichara_checks(
    result: Any,
    tier: str,
    *,
    dimension_key: str,
    objective_text: str,
    max_items: int,
    has_documents: bool,
) -> list[Check]:
    """Validators for one vichara.v1 answer (rubric: config/validation.yaml). Blocking failures send an
    open-weight answer to frontier. Each check carries the details the validation log shows."""
    kept = [item.model_dump() for item in result.items][:max_items]
    checks = [
        Check("echo_key", result.dimensionKey == dimension_key, True,
              f"answered {result.dimensionKey!r}, asked {dimension_key!r}"
              if result.dimensionKey != dimension_key else "answers the dimension asked",
              {"asked": dimension_key, "answered": result.dimensionKey}),
    ]
    quotes: list[dict[str, Any]] = []
    for n, item in enumerate(kept, start=1):
        if item.get("status") != "answered":
            continue
        for basis in item.get("basis", []):
            found = check_basis_grounding(basis, objective_text).status == "pass"
            entry: dict[str, Any] = {"item": n, "quote": basis if len(basis) <= 400 else basis[:399] + "…",
                                     "found": found}
            if not found:
                entry["diagnosis"] = explain_grounding_miss(basis, objective_text)
            quotes.append(entry)
    failed = sum(1 for q in quotes if not q["found"])
    checks.append(Check(
        "grounding", not failed, True,
        f"{failed} basis excerpt(s) are not word for word in the objective text"
        if failed else "every basis is word for word in the objective text",
        {"checked": len(quotes), "failed": failed, "itemsKept": len(kept), "quotes": quotes},
    ))
    if tier == "open_weight":
        unresolved = [item for item in kept if item.get("status") == "unresolved"]
        abstained = has_documents and len(unresolved) == len(kept)
        checks.append(Check(
            "abstention", not abstained, True,
            "no answer although objective documents are attached; frontier double-checks"
            if abstained else "answered, or no documents to answer from",
            {"documentsAttached": has_documents, "itemsKept": len(kept), "unresolved": len(unresolved),
             "reasons": [str(item.get("reason")) for item in unresolved if item.get("reason")]},
        ))
    return checks
