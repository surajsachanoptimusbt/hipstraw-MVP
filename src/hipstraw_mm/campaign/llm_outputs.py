"""Structured outputs of the E2 Moves (contracts/llm-outputs.md) and the checks that keep them honest.

Every field is required (strict structured output). No field holds a score, probability or forecast
(tests/unit/test_campaign_no_score.py). The checks are rules, never another model call: quotes must be
found word for word in the evidence they cite, and a verdict of met or partly must rest on a quote.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from hipstraw_mm.campaign.models import EvidenceRecord
from hipstraw_mm.campaign.rubric import Rubric
from hipstraw_mm.market.router import Check


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteOut(_Out):
    evidenceId: str
    quote: str


class Judgement(_Out):
    questionId: str
    channel: str  # the channel judged, or "" for a campaign-wide question
    verdict: Literal["met", "partly", "not_met", "unknown"]
    reason: str
    quotes: list[QuoteOut]
    fix: str


class AssumptionOut(_Out):
    text: str
    core: bool
    evidenceRefs: list[str]


class GapOut(_Out):
    text: str
    area: Literal["strategy", "readiness"]
    itemRefs: list[str]
    evidenceRefs: list[str]


class Synthesis(_Out):
    """campaign_synthesis.v2 (M06): one judgement per rubric question and channel, plus assumptions and gaps."""

    judgements: list[Judgement]
    assumptions: list[AssumptionOut]
    gaps: list[GapOut]


class Variant(_Out):
    dimension: Literal["message", "audience", "offer", "channel"]
    text: str
    rationale: str
    evidenceRefs: list[str]
    hypothesis: str


class Variants(_Out):
    """campaign_variants.v1 (M07): variants worth testing, each with the hypothesis it would test."""

    variants: list[Variant]


# -- matching quotes ---------------------------------------------------------------------------------------

_FOLD = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "“": '"', "”": '"',
                       "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    """Case, typographic quotes and dashes, and runs of whitespace do not change what was said."""
    text = unicodedata.normalize("NFKC", text).translate(_FOLD)
    return re.sub(r"\s+", " ", text).strip().casefold()


def evidence_text(content: str | dict[str, Any] | list[Any] | Any) -> str:
    """Evidence content as plain text, so a quote can be checked against a structured record too."""
    if isinstance(content, dict):
        return "\n".join(evidence_text(v) for v in content.values())
    if isinstance(content, list):
        return "\n".join(evidence_text(v) for v in content)
    return "" if content is None else str(content)


_EDGE_PUNCTUATION = " .,;:!?\"'…"


def quote_found(quote: str, evidence: EvidenceRecord) -> bool:
    """The quote's words appear, in order, in the evidence. Punctuation a model adds or drops at the start or end
    of a quote (a full stop where it cut a sentence short, quote marks) does not change what was said."""
    words = normalize(quote).strip(_EDGE_PUNCTUATION)
    return bool(words) and words in normalize(evidence_text(evidence.content))


# -- checks ------------------------------------------------------------------------------------------------


def _pair(question_id: str, channel: str) -> str:
    return f"{question_id}/{channel}" if channel else question_id


def synthesis_checks(result: Synthesis, rubric: Rubric, evidence: list[EvidenceRecord], *,
                     channels: list[str]) -> list[Check]:
    by_id = {e.evidenceId: e for e in evidence}
    ids = [(j.questionId, j.channel) for j in result.judgements]
    expected = rubric.expected(channels)
    missing = [_pair(*p) for p in expected if p not in ids]
    extra = sorted({_pair(*p) for p in ids if p not in expected or ids.count(p) > 1})
    refs = [q.evidenceId for j in result.judgements for q in j.quotes]
    refs += [r for a in result.assumptions for r in a.evidenceRefs] + [r for g in result.gaps for r in g.evidenceRefs]
    unknown = sorted({r for r in refs if r not in by_id})
    bad_quotes = [f"{_pair(j.questionId, j.channel)}: {q.quote[:60]!r}" for j in result.judgements for q in j.quotes
                  if q.evidenceId in by_id and not quote_found(q.quote, by_id[q.evidenceId])]
    unsupported = [_pair(j.questionId, j.channel) for j in result.judgements
                   if j.verdict in ("met", "partly") and not j.quotes]
    return [
        Check("coverage", not missing and not extra, True,
              "every rubric question judged once per channel it asks about" if not missing and not extra
              else f"missing {', '.join(missing) or '-'}; repeated or unknown {', '.join(extra) or '-'}"),
        Check("evidence_ids", not unknown, True,
              "every cited evidence record exists" if not unknown else f"unknown evidence: {', '.join(unknown)}"),
        Check("quotes", not bad_quotes, True,
              "every quote is word for word in its evidence" if not bad_quotes
              else "not found word for word: " + "; ".join(bad_quotes)),
        Check("verdict_support", not unsupported, True,
              "every met or partly verdict quotes the campaign" if not unsupported
              else f"met or partly without a quote: {', '.join(unsupported)}"),
    ]


def variants_checks(result: Variants, *, max_variants: int, evidence: list[EvidenceRecord]) -> list[Check]:
    known = {e.evidenceId for e in evidence}
    unknown = sorted({r for v in result.variants for r in v.evidenceRefs if r not in known})
    empty = [v.text[:40] for v in result.variants if not v.hypothesis.strip()]
    return [
        Check("count", len(result.variants) <= max_variants, True,
              f"{len(result.variants)} variants (at most {max_variants})"),
        Check("evidence_ids", not unknown, True,
              "every cited evidence record exists" if not unknown else f"unknown evidence: {', '.join(unknown)}"),
        Check("hypothesis", not empty, True,
              "every variant states its hypothesis" if not empty else f"no hypothesis: {', '.join(empty)}"),
    ]
