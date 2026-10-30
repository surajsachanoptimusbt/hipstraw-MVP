"""T009: campaign commands run without building the market context (no Firestore, no market program)."""

from __future__ import annotations

import io
import json

from hipstraw_mm import cli


def _refuse(_config: object) -> cli.Context:
    raise AssertionError("campaign commands must not build the market context")


def test_campaign_lint_does_not_build_the_market_context() -> None:
    out = io.StringIO()
    code = cli.main(["campaign", "--db", ":memory:", "lint", "--json"], context_factory=_refuse,
                    stdout=out, stderr=io.StringIO())
    assert code == 0
    assert json.loads(out.getvalue())["command"] == "campaign lint"


def test_campaign_view_has_its_own_port() -> None:
    from hipstraw_mm.campaign.cli import HANDLERS

    args = cli.build_parser().parse_args(["campaign", "--db", "x.db", "view"])
    assert args.campaign_command == "view" and args.port == 8766 and "view" in HANDLERS
