"""market start: open a market run (Market Manager, right open_run)."""

from __future__ import annotations

from pathlib import Path

from hipstraw_mm.context import Context
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.market.agents import load_agent_registry
from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.playbook import load_playbook
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer


def new_market_run_id(ctx: Context) -> str:
    return f"mrun_{ctx.now():%Y%m%dT%H%M%S}"


def market_start(
    ctx: Context, program_id: str, objective_pdfs: list[Path] | None = None, run_id: str | None = None
) -> str:
    """Open a market run. `run_id` is for replaying a recorded run, whose path IDs embed its run ID."""
    program = ctx.store.get_program(program_id)
    if program is None:
        raise PreconditionError(f"program {program_id!r} not loaded (run intake first)")

    settings = load_pipeline_settings()
    layers = load_layers()
    run_id = run_id or new_market_run_id(ctx)

    objective = {
        "text": program.get("objective", ""),
        "experimentContexts": program.get("experimentContexts", []),
        "constraints": program.get("defaultConstraints", {}),
    }

    run_doc = {
        "marketRunId": run_id,
        "programId": program_id,
        "objective": objective,
        "constraintsInForce": program.get("defaultConstraints", {}),
        "config": settings.model_dump(),
        "model": ctx.llm.model,
        "status": "opened",
        "stepTimes": {},
        "counts": {"modelCalls": 0, "searches": 0, "fetches": 0, "traceSteps": 0},
        "unresolved": [],
        "marketStatus": None,
        "unassessed": [],
        "errorStage": None,
        "errorMessage": None,
        "lastSeq": 0,
        "finalPathShortfall": None,
        # The agent design in force for this run: capabilities, skills, tools (config/agents.yaml).
        "agentRegistry": load_agent_registry().model_dump(),
        # The playbook the Review will use, and the market types it chooses plays by.
        "playbookVersion": load_playbook().version,
        "marketTypes": program.get("marketTypes", []),
    }
    ctx.store.upsert_market_run(run_doc)

    tracer = Tracer(store=ctx.store, layers=layers, settings=settings, run_id=run_id, clock=ctx.now)
    ctx.tracer = tracer

    with tracer.step("market_manager", "market_manager", "open_run", right="open_run") as step:
        step.set_inputs({"programId": program_id})
        step.set_outputs({"marketRunId": run_id, "objectiveDocuments": len(objective_pdfs or [])})

    if objective_pdfs:
        from hipstraw_mm.market.objective import ingest_documents

        ingest_documents(ctx, tracer, run_id, objective_pdfs, settings.objective.maxChars)
    return run_id
