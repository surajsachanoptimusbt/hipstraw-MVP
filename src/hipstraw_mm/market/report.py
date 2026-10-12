"""Market report generation (Market Manager, stage 'reported')."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_market_report(store: Any, run_id: str) -> str:
    run = store.get_market_run(run_id)
    if run is None:
        return f"# Market Run {run_id}\n\nRun not found.\n"

    lines = [f"# Market Discovery Report: {run_id}\n"]

    status = run.get("status", "unknown")
    lines.append(f"**Status**: {status}\n")

    ms = run.get("marketStatus")
    if ms:
        lines.append(f"**Market Status**: {ms.get('state', 'unknown')} — {ms.get('reason', '')}\n")

    shortfall = run.get("finalPathShortfall")
    if shortfall:
        lines.append(
            f"**Path Shortfall**: wanted {shortfall['wanted']},"
            f" found {shortfall['found']} — {shortfall['reason']}\n"
        )

    lines.append("\n## Counts\n")
    counts = run.get("counts", {})
    for key, val in counts.items():
        lines.append(f"- {key}: {val}")
    lines.append("")

    unresolved = run.get("unresolved", [])
    if unresolved:
        lines.append("\n## Unresolved Items\n")
        for item in unresolved:
            lines.append(f"- **{item.get('kind', '?')}** {item.get('ref', '?')}: {item.get('reason', '?')}")
        lines.append("")

    unassessed = run.get("unassessed", [])
    if unassessed:
        lines.append("\n## Unassessed Dimensions\n")
        for item in unassessed:
            lines.append(f"- **{item.get('dimensionKey', '?')}**: {item.get('reason', '?')}")
        lines.append("")

    decisions = store.list_path_decisions(run_id) if hasattr(store, "list_path_decisions") else []
    if decisions:
        lines.append("\n## Path Decisions\n")
        for d in decisions:
            lines.append(f"- **{d.get('pathId', '?')}**: {d.get('decision', '?')} — {d.get('reason', '')}")
        lines.append("")

    lines.extend(_market_map_section(store, run_id))
    lines.extend(_companies_section(store, run_id, {d.get("pathId"): d for d in decisions}))
    return "\n".join(lines) + "\n"


def _money(v: Any) -> str:
    if v is None:
        return "-"
    v = float(v)
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}K"


def _market_map_section(store: Any, run_id: str) -> list[str]:
    market_map = store.get_market_map(run_id) if hasattr(store, "get_market_map") else None
    if not market_map or not market_map.get("tiles"):
        return []
    tiles = sorted(market_map["tiles"], key=lambda t: -(t.get("valueMid") or 0))
    lines = [
        "\n## Market Map\n",
        f"{len(tiles)} micro markets at the {market_map.get('level')} level. Size: {market_map.get('sizeBasis')}.\n",
        "| Micro market | Segment | Value pool (hypothesis) | Position | Change |",
        "|---|---|---|---|---|",
    ]
    for t in tiles[:15]:
        pos = t.get("position") or {}
        change = t.get("change") or {}
        lines.append(
            f"| {' > '.join(t['labels'][1:])} | {t['group']} | {_money(t.get('valuePoolUsdLow'))}-"
            f"{_money(t.get('valuePoolUsdHigh'))} | {pos.get('status', 'screened')} | "
            f"{change.get('direction', 'new')} |"
        )
    lines.append("")
    return lines


def _companies_section(store: Any, run_id: str, decisions: dict[str, Any]) -> list[str]:
    finals = [p for p in store.list_paths(run_id) if p.get("isFinal")]
    if not finals:
        return []
    companies = store.list_market_companies(run_id)
    roles = store.list_buyer_roles(run_id)
    lines = ["\n## Target Companies by Path\n"]
    for n, path in enumerate(finals, start=1):
        pid = path["pathId"]
        decision = decisions.get(pid, {}).get("decision", "not decided")
        lines.append(f"### Path {n}: {' > '.join(path.get('nodeLabels', []))}\n")
        packet = path.get("researchPacket") or {}
        position = path.get("marketPosition") or {}
        estimate = position.get("economicEstimate") or {}
        if position.get("recommendation"):
            lines.append(
                f"Position & Evaluation: **{position['recommendation']}** at {position.get('confidence')} confidence"
                + (f"; value pool {_money(estimate.get('valuePoolUsdLow'))}-{_money(estimate.get('valuePoolUsdHigh'))}"
                   f" ({estimate.get('unit')}, hypothesis)" if estimate else "")
                + (f". Canonical position v{position.get('version')}, trajectory {position.get('trajectory')}."
                   if position.get("version") else ".") + "\n"
            )
        for req in position.get("researchRequirements", [])[:3]:
            lines.append(f"- Research needed ({req['priority']}): {req['evidenceGap']}")
        if position.get("researchRequirements"):
            lines.append("")
        lines.append(
            f"Decision: **{decision}**. Child run `{path.get('childRunId', '-')}`: "
            f"{packet.get('found', 0)} found, {packet.get('included', 0)} included, "
            f"{packet.get('needsVerification', 0)} need verification, {packet.get('excluded', 0)} excluded.\n"
        )
        rows = [(c, link) for c in companies for link in c.get("links", []) if link["pathId"] == pid]
        for title, disposition in (("Included", "include"), ("Needs verification", "needs_verification")):
            chosen = [(c, link) for c, link in rows if link["disposition"] == disposition]
            if not chosen:
                continue
            lines.append(f"**{title}**\n")
            for c, link in chosen:
                hq = c.get("hq") or {}
                where = ", ".join(x for x in (hq.get("city"), hq.get("state")) if x) or "HQ unknown"
                path_roles = [
                    f"{r['role']} ({r['authority']})"
                    for doc in roles if doc.get("pathId") == pid and doc.get("domainKey") == c["domainKey"]
                    for r in doc.get("roles", [])
                ]
                role_text = f"; buyer roles: {', '.join(path_roles)}" if path_roles else ""
                lines.append(
                    f"- **{c['name']}** ({c.get('domain') or c['domainKey']}), {where}, "
                    f"evidence confidence {c.get('evidenceConfidence', 0):.2f}{role_text}. {link.get('reason') or ''}"
                )
            lines.append("")
        excluded = sum(1 for _, link in rows if link["disposition"] == "exclude")
        if excluded:
            lines.append(f"{excluded} excluded by Review (outside the constraints or without a working website).\n")
    return lines


def write_market_report(
    store: Any,
    tracer: Any,
    run_id: str,
    out_dir: Path | None = None,
) -> Path:
    content = build_market_report(store, run_id)
    output = (out_dir or Path("reports")) / f"{run_id}.md"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tracer.step(
        "market_manager",
        "market_manager",
        "write_report",
        right="record_disposition",
    ) as ctx:
        ctx.set_inputs({"runId": run_id})
        output.write_text(content, encoding="utf-8")
        ctx.set_outputs({"path": str(output), "bytes": len(content)})

    return output
