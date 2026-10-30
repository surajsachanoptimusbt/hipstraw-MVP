"""Strategy Moves.

M06 judges the campaign rubric and M07 proposes variants: bounded model steps (E2) through the task
router, with explicit inputs and structured output. Their output is a proposal: M06 changes no item, and
M07's variants enter the working Position only as `proposed` hypotheses for the Review. A quote that cannot
be found word for word turns its verdict into `unknown`; nothing model-made is kept on trust.
M08 requests evidence for open core assumptions (E0).
"""

from __future__ import annotations

from typing import Any

from hipstraw_mm import prompts
from hipstraw_mm.campaign.channels import ChannelStandards, channel_plans, load_channel_standards
from hipstraw_mm.campaign.intake import asset_content
from hipstraw_mm.campaign.llm_outputs import (
    Judgement,
    Synthesis,
    Variants,
    evidence_text,
    normalize,
    quote_found,
    synthesis_checks,
    variants_checks,
)
from hipstraw_mm.campaign.models import EvidenceRequest, Transition
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome
from hipstraw_mm.campaign.rubric import load_rubric
from hipstraw_mm.market.router import TaskRouter, load_routing

MAX_EVIDENCE_CHARS = 8_000
# Prompt files live with the others in hipstraw_mm/prompts; the constants stay here, outside the market
# routing table, so Hipstraw's tasks reach frontier by router rule R1 and the market Routing tab is unchanged.
SYNTHESIS_PROMPT = "campaign_synthesis.v2"
VARIANTS_PROMPT = "campaign_variants.v1"
NO_MODEL = "no model configured: set OPENAI_API_KEY and LLM_MODEL, or replay recorded calls"


ASSET_WHAT = {
    "landing_page": "landing page copy", "email_copy": "email copy", "ad_copy": "ad copy",
    "creative": "creative description", "brief": "brief", "other": "asset",
}


def _what(ctx: MoveContext, source_ref: str, kind: str) -> str:
    """What one evidence record is, in words the model can match rubric questions to."""
    if source_ref.endswith("#brief"):
        return "the customer's campaign brief"
    if "#asset:" in source_ref:
        asset_id = source_ref.rsplit(":", 1)[1]
        asset = next((a for a in ctx.mandate.assets if a.assetId == asset_id), None)
        if asset is not None:
            where = f" for {asset.channel}" if asset.channel else ""
            return f"{ASSET_WHAT[asset.kind]}{where} (supplied by the customer)"
    if kind == "page_read":
        return f"page read by Hipstraw from {source_ref}"
    return kind


def _channels(ctx: MoveContext, standards: ChannelStandards) -> list[dict[str, Any]]:
    """Each channel with who the Sponsor says it reaches, how that channel reaches people and is read, and what
    its readers see before the channel cuts the text off (from the channel's length checks), so "Written for the
    channel" is judged on what is shown, not on the whole text."""
    out = []
    for plan in channel_plans(ctx.mandate):
        standard = standards.channels.get(plan.channel)
        assets = [a for a in ctx.mandate.assets if a.channel == plan.channel]
        limits = {c.args["field"]: c.args["max"] for c in (standard.checks if standard else [])
                  if c.check == "asset_field_max"}
        out.append({
            "channel": plan.channel, "name": standards.name(plan.channel), "audienceOnChannel": plan.audience,
            "setup": plan.setup, "successMeasure": plan.successMeasure,
            "reach": standard.reach.model_dump() if standard else None, "format": standard.format if standard else None,
            "assets": [e.evidenceId for a in assets if (e := ctx.asset_evidence(a, asset_content(a))) is not None],
            "shownFirst": [{"field": field, "characters": limit, "shown": value[:limit], "cutOff": len(value) > limit}
                           for a in assets for field, limit in limits.items() if (value := a.fields.get(field))],
        })
    return out


def _landing_page(ctx: MoveContext) -> dict[str, Any] | None:
    """The landing page every channel sends people to: the copy the customer supplied, and any page Hipstraw read."""
    pages = [a for a in ctx.mandate.assets if a.kind == "landing_page"]
    if not pages:
        return None
    supplied = [e.evidenceId for a in pages if (e := ctx.asset_evidence(a, asset_content(a))) is not None]
    read = [e.evidenceId for e in ctx.evidence if e.kind == "page_read"]
    return {"url": pages[0].url, "suppliedCopy": supplied, "readByHipstraw": read}


def _payload(ctx: MoveContext, standards: ChannelStandards | None = None) -> dict[str, Any]:
    m = ctx.mandate
    standards = standards or load_channel_standards(ctx.config_dir)
    return {
        "launch": {
            "product": m.product.model_dump(mode="json"), "audience": m.audience.model_dump(mode="json"),
            "market": m.market, "dayZero": m.dayZero.isoformat(), "objective": m.objective.model_dump(mode="json"),
            "channels": m.strategy.channels, "message": m.strategy.message, "offer": m.strategy.offer,
        },
        "channels": _channels(ctx, standards),
        "landingPage": _landing_page(ctx),
        "evidence": [
            {"evidenceId": e.evidenceId, "kind": e.kind, "what": _what(ctx, e.sourceRef, e.kind),
             "sourceRef": e.sourceRef, "text": evidence_text(e.content)[:MAX_EVIDENCE_CHARS]}
            for e in ctx.evidence if e.kind != "metric"
        ],
        "assetsOnFile": [
            {"what": what, "evidenceId": e.evidenceId}
            for e in ctx.evidence if e.kind != "metric" and "supplied by the customer" in (what := _what(
                ctx, e.sourceRef, e.kind))
        ],
        "position": [{"itemId": i.itemId, "kind": i.kind, "state": i.state, "text": i.text} for i in ctx.items],
    }


def _call(ctx: MoveContext, schema: Any, version: str, payload: dict[str, Any], validate: Any) -> tuple[Any, str]:
    router = TaskRouter(ctx.model, ctx.tracer, load_routing(ctx.config_dir), run_id=ctx.launch_id)
    with ctx.tracer.step("readiness_testing", "move_runner", version.split(".")[0], right="run_move") as step:
        step.set_inputs({"moveId": ctx.move.id, "task": version})
        result, routing = router.call(
            step, schema, prompts.messages(version, payload), task=version,
            match_key=f"{ctx.launch_id}:{ctx.line_run_id}:{ctx.move.id}", validate=validate,
        )
        step.set_outputs({"routing": routing})
    model = routing["attempts"][-1].get("model") or getattr(ctx.model.llm, "model", "") or ""
    return result, str(model)


@register("strategy.synthesize")
def synthesize(ctx: MoveContext) -> MoveOutcome:
    """M06: one rubric judgement per question, plus assumptions and gaps, as proposals."""
    if ctx.model is None:
        return MoveOutcome(status="blocked", note=NO_MODEL)
    rubric = load_rubric(ctx.config_dir)
    standards = load_channel_standards(ctx.config_dir)
    channels = ctx.mandate.strategy.channels
    payload = _payload(ctx, standards)
    payload["rubric"] = [q.model_dump() for q in rubric.questions]
    result, model = _call(ctx, Synthesis, SYNTHESIS_PROMPT, payload,
                          lambda r, _tier: synthesis_checks(r, rubric, ctx.evidence, channels=channels))
    assert isinstance(result, Synthesis)
    evidence = {e.evidenceId: e for e in ctx.evidence}
    judged: dict[tuple[str, str], Judgement] = {}
    for j in result.judgements:
        judged.setdefault((j.questionId, j.channel), j)

    out = MoveOutcome(models=[model])
    downgraded = 0
    for question_id, channel in rubric.expected(channels):
        q = rubric.question(question_id)
        assert q is not None
        found = judged.get((question_id, channel))
        if found:
            verdict, reason, fix = found.verdict, found.reason, found.fix
        else:
            verdict, reason, fix = "unknown", "not judged by the model", q.fix
        quotes = [x for x in (found.quotes if found else []) if x.evidenceId in evidence
                  and quote_found(x.quote, evidence[x.evidenceId])]
        if found and len(quotes) < len(found.quotes):
            verdict, quotes, downgraded = "unknown", [], downgraded + 1
            reason = f"A quote could not be found word for word in the evidence, so this stays unknown. ({reason})"
        elif verdict in ("met", "partly") and not quotes:
            verdict, downgraded = "unknown", downgraded + 1
            reason = f"No supporting quote, so this stays unknown. ({reason})"
        out.proposals.append({
            "type": "rubric", "questionId": q.id, "title": q.title, "area": q.area, "verdict": verdict,
            "reason": reason, "quotes": [x.model_dump() for x in quotes], "fix": fix,
            "channel": channel or None, "channelName": standards.name(channel) if channel else None,
            "rubricVersion": rubric.version,
        })
    def same(text: str) -> str:
        return normalize(text).rstrip(" .!?")

    held = {same(i.text) for i in ctx.items if i.kind == "assumption"}
    for a in result.assumptions:
        if same(a.text) in held:
            continue  # already an assumption in the Position; repeating it adds nothing for the reviewer
        out.proposals.append({"type": "assumption", "text": a.text, "core": a.core,
                              "evidenceRefs": [r for r in a.evidenceRefs if r in evidence]})
    open_unknowns = {same(i.text) for i in ctx.items if i.kind == "unknown"}
    for g in result.gaps:
        if same(g.text) in open_unknowns:
            continue  # already an open unknown in the Position
        out.proposals.append({"type": "gap", "text": g.text, "area": g.area, "itemRefs": g.itemRefs,
                              "evidenceRefs": [r for r in g.evidenceRefs if r in evidence]})
    verdicts = [p["verdict"] for p in out.proposals if p["type"] == "rubric"]
    out.note = (", ".join(f"{verdicts.count(v)} {v}" for v in ("met", "partly", "not_met", "unknown"))
                + (f"; {downgraded} downgraded to unknown" if downgraded else ""))
    return out


@register("strategy.propose_variants")
def propose_variants(ctx: MoveContext) -> MoveOutcome:
    """M07: variants worth testing, each a `proposed` hypothesis for the Review."""
    if ctx.model is None:
        return MoveOutcome(status="blocked", note=NO_MODEL)
    payload = _payload(ctx)
    payload["maxVariants"] = ctx.settings.maxVariants
    result, model = _call(ctx, Variants, VARIANTS_PROMPT, payload,
                          lambda r, _tier: variants_checks(r, max_variants=ctx.settings.maxVariants,
                                                           evidence=ctx.evidence))
    assert isinstance(result, Variants)
    known = {e.evidenceId for e in ctx.evidence}
    out = MoveOutcome(models=[model])
    for v in result.variants[: ctx.settings.maxVariants]:
        refs = [r for r in v.evidenceRefs if r in known]
        item = ctx.new_item("hypothesis", "strategy", f"{v.dimension}: {v.text}", "proposed", refs,
                            note=f"Hypothesis: {v.hypothesis} Why: {v.rationale}")
        out.newItems.append(item)
        out.proposals.append({"type": "variant", "itemId": item.itemId, "dimension": v.dimension, "text": v.text,
                              "hypothesis": v.hypothesis, "rationale": v.rationale, "evidenceRefs": refs})
    out.note = f"{len(out.newItems)} variants proposed"
    return out


@register("strategy.request_evidence")
def request_evidence(ctx: MoveContext) -> MoveOutcome:
    """M08: every open core assumption gets an evidence request to the Sponsor."""
    out = MoveOutcome()
    for item in ctx.items:
        if item.kind != "assumption" or not item.core or item.state != "open":
            continue
        claim = item.text[:1].lower() + item.text[1:]
        request = EvidenceRequest(
            requestId=ctx.record_id("erq"), launchId=ctx.launch_id, assumptionItemId=item.itemId,
            question=f"What evidence shows that {claim.rstrip('.')}?", requestedFrom=ctx.owner(),
            createdAt=ctx.now.isoformat(),
        )
        ctx.store.insert(request)
        out.produced.append(request.requestId)
        out.transitions.append(Transition(itemId=item.itemId, fromState="open", toState="awaiting_evidence"))
    out.note = f"{len(out.produced)} evidence requests"
    return out
