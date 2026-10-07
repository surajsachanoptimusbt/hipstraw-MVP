"""T038 position: validate the first-position file and create `runs/{runId}` with status `created`.

The constraints, budgets, and model in force are copied from config now, so a later config change
cannot alter this run (FR-001).
"""

from __future__ import annotations

from pathlib import Path

from hipstraw_mm.config import load_first_position
from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.errors import ConfigError, PreconditionError
from hipstraw_mm.models import ConstraintsInForce, MetroRef, Position, Run, new_run_id


def position(ctx: Context, candidate_id: str, file: str) -> CommandResult:
    store, config = ctx.store, ctx.config
    candidate = store.get_candidate(candidate_id)
    if candidate is None:
        raise PreconditionError(f"candidate {candidate_id} not found; run `hipstraw-mm candidates` first")
    program = store.get_program(candidate["programId"])
    if program is None:
        raise PreconditionError(f"program {candidate['programId']} not found; run `hipstraw-mm intake` first")

    first = load_first_position(Path(file), {i["id"] for i in program["primaryInterests"]})
    if first.candidateId != candidate_id:
        raise ConfigError(f"{file}: candidateId is {first.candidateId!r}, but --candidate is {candidate_id!r}")

    run_id = new_run_id(ctx.now())
    if store.get_run(run_id) is not None:
        raise PreconditionError(f"run {run_id} already exists; try again in a second")
    constraints = config.run.constraints
    run = Run(
        runId=run_id,
        programId=program["programId"],
        candidateId=candidate_id,
        position=Position(**first.model_dump(exclude={"candidateId"})),
        constraintsInForce=ConstraintsInForce(
            maxEmployees=constraints.maxEmployees,
            maxRevenueUsd=constraints.maxRevenueUsd,
            metros=[MetroRef(id=m.id, csaCode=m.csaCode, name=m.name) for m in config.metros_in_force()],
            largeEnterpriseParents=list(constraints.largeEnterpriseParents),
        ),
        budgets=config.run.budgets.model_dump(),
        model=config.run.model.name,
    )
    store.upsert_run(run.model_dump(mode="json"))
    return CommandResult("position", message=f"run {run_id} created", runId=run_id, status="created")
