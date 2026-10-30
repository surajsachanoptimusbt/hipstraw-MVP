"""A launch's status for `campaign show`: mandate, head Position, Line runs and Reviews."""

from __future__ import annotations

from collections import Counter
from typing import Any

from hipstraw_mm.campaign.models import Launch, LineRun, ReviewRun
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.errors import PreconditionError


def launch_summary(store: CampaignStore, launch_id: str) -> dict[str, Any]:
    launch = store.get(Launch, launch_id)
    mandate = store.latest_mandate(launch_id)
    position = store.head_position(launch_id)
    if launch is None or mandate is None or position is None:
        raise PreconditionError(f"launch {launch_id} not found")
    return {
        "launchId": launch_id,
        "productName": launch.productName,
        "market": launch.market,
        "mandateVersion": mandate.version,
        "dayZero": mandate.dayZero.isoformat(),
        "position": {
            "version": position.version,
            "state": position.state,
            "counts": dict(Counter(i.kind for i in position.items)),
            "items": [i.model_dump(mode="json") for i in position.items],
        },
        "lineRuns": [
            {"lineRunId": r.lineRunId, "lineId": r.lineId, "state": r.state, "nextStage": r.nextStage}
            for r in store.list_for_launch(LineRun, launch_id)
        ],
        "reviews": [
            {"reviewId": r.reviewId, "state": r.state, "findings": len(r.findings)}
            for r in store.list_for_launch(ReviewRun, launch_id)
        ],
    }


def summary_text(summary: dict[str, Any]) -> str:
    pos = summary["position"]
    lines = [
        f"{summary['launchId']}  {summary['productName']}  market {summary['market']}  Day Zero {summary['dayZero']}",
        f"mandate v{summary['mandateVersion']}  Position v{pos['version']} ({pos['state']})",
    ]
    for item in pos["items"]:
        refs = ",".join(item["evidenceRefs"])
        lines.append(f"  {item['itemId']:<4} {item['kind']:<11} {item['state']:<17} {item['text']}  [{refs}]")
    for run in summary["lineRuns"]:
        lines.append(f"  Line run {run['lineRunId']}: {run['lineId']} {run['state']}")
    for review in summary["reviews"]:
        lines.append(f"  Review {review['reviewId']}: {review['state']} ({review['findings']} findings)")
    return "\n".join(lines)
