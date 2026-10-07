"""T036 intake: load the program config into `programs/{programId}`."""

from __future__ import annotations

from hipstraw_mm.config import load_program_config
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.models import Program


def intake(ctx: Context, program: str) -> CommandResult:
    path = ctx.config.program_path(program)
    config = load_program_config(path)
    constraints = ctx.config.run.constraints
    doc = Program(
        programId=config.programId,
        name=config.name,
        objective=config.objective,
        sourceUrl=config.sourceUrl,
        experimentContexts=config.experimentContexts,
        primaryInterests=config.primaryInterests,
        defaultConstraints={
            "maxEmployees": constraints.maxEmployees,
            "maxRevenueUsd": constraints.maxRevenueUsd,
            "metroIds": list(constraints.metroIds),
        },
    )
    ctx.store.upsert_program(doc.model_dump())
    return CommandResult(
        "intake",
        message=f"program {config.programId} loaded from {path}",
        counts={"experimentContexts": len(config.experimentContexts), "primaryInterests": len(config.primaryInterests)},
    )
