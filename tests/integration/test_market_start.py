"""T010: Integration test for `market start` through cli.main."""

from __future__ import annotations

import io

import pytest

from hipstraw_mm.cli import main
from hipstraw_mm.store.memory import MemoryStore


@pytest.fixture
def market_harness(test_config, replay_adapters):
    """Drives market commands through cli.main with a memory store and replay adapters."""
    from hipstraw_mm.context import Context
    from hipstraw_mm.logging_setup import EventLog

    store = MemoryStore()
    adapters = replay_adapters("us1")

    def context_factory(config):
        return Context(
            config=test_config,
            store=store,
            log=EventLog(runs_dir=None, stream=None),
            llm=adapters.llm,
            search=adapters.search,
            new_fetcher=adapters.new_fetcher,
        )

    return store, context_factory


class TestMarketStart:
    def test_start_creates_opened_run(self, market_harness) -> None:
        store, ctx_factory = market_harness
        # First load the program via intake (file name != stored programId)
        out = io.StringIO()
        code = main(["intake", "--program", "invoice_alpha"], context_factory=ctx_factory, stdout=out)
        assert code == 0

        out = io.StringIO()
        code = main(
            ["market", "start", "--program", "invoice_alpha_genesis"],
            context_factory=ctx_factory,
            stdout=out,
        )
        assert code == 0
        output = out.getvalue()
        assert "mrun_" in output

        # Find the created run
        runs = store.list_market_runs()
        assert len(runs) >= 1
        run = runs[0]
        assert run["status"] == "opened"
        assert run["objective"] is not None
        assert run["config"] is not None
        assert run["lastSeq"] >= 1

    def test_start_creates_market_manager_step(self, market_harness) -> None:
        store, ctx_factory = market_harness
        main(["intake", "--program", "invoice_alpha"], context_factory=ctx_factory, stdout=io.StringIO())
        main(
            ["market", "start", "--program", "invoice_alpha_genesis"],
            context_factory=ctx_factory,
            stdout=io.StringIO(),
        )
        runs = store.list_market_runs()
        run_id = runs[0]["marketRunId"]
        steps = store.list_trace_steps_after(run_id, 0)
        assert len(steps) >= 1
        step = steps[0]
        assert step["layer"] == "market_manager"
        assert step["right"] == "open_run"
        assert step["status"] == "ok"
        assert run_id in str(step["outputs"])

    def test_unknown_program_exits_2(self, market_harness) -> None:
        _, ctx_factory = market_harness
        err = io.StringIO()
        code = main(
            ["market", "start", "--program", "nonexistent_program"],
            context_factory=ctx_factory,
            stdout=io.StringIO(),
            stderr=err,
        )
        assert code == 2

    def test_market_show(self, market_harness) -> None:
        store, ctx_factory = market_harness
        main(["intake", "--program", "invoice_alpha"], context_factory=ctx_factory, stdout=io.StringIO())
        out_start = io.StringIO()
        main(
            ["market", "start", "--program", "invoice_alpha_genesis"],
            context_factory=ctx_factory,
            stdout=out_start,
        )
        run_id = out_start.getvalue().strip().split()[-1]

        out_show = io.StringIO()
        code = main(
            ["market", "show", "--run", run_id],
            context_factory=ctx_factory,
            stdout=out_show,
        )
        assert code == 0
        output = out_show.getvalue()
        assert "opened" in output
