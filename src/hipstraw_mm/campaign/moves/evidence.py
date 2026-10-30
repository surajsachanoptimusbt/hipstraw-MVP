"""Evidence Moves: M01 capture customer assets, M02 bounded source research, M03 verify metrics.

M02 reads only addresses named in the mandate (E1). Its summary step (E2) proposes claims from what it
read and lands with Unit 5; until a model is configured, M02 records the page reads and nothing more.
"""

from __future__ import annotations

from datetime import date

from hipstraw_mm.campaign.gate import check_read, mandate_addresses
from hipstraw_mm.campaign.intake import asset_claim_text, asset_content
from hipstraw_mm.campaign.moves import register
from hipstraw_mm.campaign.moves.common import MoveContext, MoveOutcome, PageRead

MAX_PAGE_CHARS = 200_000


@register("evidence.capture_assets")
def capture_assets(ctx: MoveContext) -> MoveOutcome:
    """M01: make sure every asset in the current mandate is evidence and has a claim in the Position."""
    out = MoveOutcome()
    v = ctx.mandate.version
    for asset in ctx.mandate.assets:
        content = asset_content(asset)
        evidence = ctx.asset_evidence(asset, content)
        if evidence is None:
            evidence = ctx.add_evidence(kind="asset", source="customer_submission",
                                        sourceRef=f"mandate:v{v}#asset:{asset.assetId}", verificationState="reported",
                                        uncertainty="as supplied", content=content, accessClass="D2")
            out.produced.append(evidence.evidenceId)
        if not any(evidence.evidenceId in i.evidenceRefs for i in ctx.items):
            out.newItems.append(ctx.new_item("claim", "readiness", asset_claim_text(asset), "reported",
                                             [evidence.evidenceId], channel=asset.channel))
    out.note = f"{len(out.newItems)} new asset claims"
    return out


def _read(ctx: MoveContext, url: str) -> PageRead:
    fetch = ctx.fetch
    if fetch is None:
        from hipstraw_mm.campaign.adapters import default_fetch

        fetch = ctx.fetch = default_fetch(ctx.config_dir)
    with ctx.tracer.step("workers", "fetch_worker", "fetch_page", right="fetch_page") as step:
        step.set_inputs({"url": url})
        page = fetch(url)
        ctx.tracer.observe_tool_call(kind="fetch", target=url, status="ok" if page.ok else "failed",
                                     detail=page.reason)
        step.set_outputs({"ok": page.ok, "reason": page.reason, "chars": len(page.text or "")})
    return page


@register("evidence.source_research")
def source_research(ctx: MoveContext) -> MoveOutcome:
    """M02: read the mandate's own addresses; an unreadable page becomes an explicit unknown."""
    out = MoveOutcome()
    pages: list[tuple[str, str]] = []
    for url in mandate_addresses(ctx.mandate):
        allowed, reason = check_read(url, ctx.mandate)
        if not allowed:  # unreachable by construction; kept so the gate's rule is visible here too
            out.note = reason
            continue
        page = _read(ctx, url)
        if page.ok and page.text:
            text = page.text[:MAX_PAGE_CHARS]
            evidence = ctx.add_evidence(kind="page_read", source="mandate_url", sourceRef=url,
                                        verificationState="observed",
                                        uncertainty="page as read by Hipstraw; may differ by audience or region",
                                        content=text, accessClass="D2")
            out.produced.append(evidence.evidenceId)
            pages.append((evidence.evidenceId, text))
        elif ctx.open_item("unknown", f"page:{url}") is None:
            out.newItems.append(ctx.new_item("unknown", "readiness", f"Could not read {url}: {page.reason}",
                                             "open", ctx.brief_ref(), key=f"page:{url}"))
    out.note = f"read {len(pages)} of {len(mandate_addresses(ctx.mandate))} pages; M06 judges what was read"
    return out


@register("evidence.verify_metrics")
def verify_metrics(ctx: MoveContext) -> MoveOutcome:
    """M03: each metric row becomes an observation, `observed` if complete and fresh, otherwise `stale`."""
    out = MoveOutcome()
    for e in ctx.evidence:
        if e.kind != "metric" or e.metric is None:
            continue
        key = f"metric:{e.evidenceId}"
        if any(i.key == key for i in ctx.items):
            continue
        m = e.metric
        text = f"{m.metric} = {m.value:g}{' ' + m.unit if m.unit else ''} ({m.windowStart} to {m.windowEnd})"
        if e.verificationState == "unverified":
            state, note = "stale", e.uncertainty
        else:
            age = (ctx.now.date() - date.fromisoformat(str(m.windowEnd))).days
            fresh = age <= ctx.settings.metricFreshDays
            state = "observed" if fresh else "stale"
            note = f"window ended {age} days ago" + ("" if fresh else f" (older than {ctx.settings.metricFreshDays})")
        out.newItems.append(ctx.new_item("observation", "readiness", text, state, [e.evidenceId], key=key, note=note))
    out.note = f"{len(out.newItems)} metric observations"
    return out
