"""market start: open a market run (Market Manager, right open_run)."""

from __future__ import annotations

from pathlib import Path

from hipstraw_mm.context import Context
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.market.layers import load_layers
from hipstraw_mm.market.settings import load_pipeline_settings
from hipstraw_mm.market.trace import Tracer


def new_market_run_id(ctx: Context) -> str:
    return f"mrun_{ctx.now():%Y%m%dT%H%M%S}"


def market_start(ctx: Context, program_id: str, objective_pdfs: list[Path] | None = None) -> str:
    program = ctx.store.get_program(program_id)
    if program is None:
        raise PreconditionError(f"program {program_id!r} not loaded (run intake first)")

    settings = load_pipeline_settings()
    layers = load_layers()
    run_id = new_market_run_id(ctx)

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
