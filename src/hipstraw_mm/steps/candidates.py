"""T037 candidates: copy the program's six experiment contexts. No model call, no generation (FR-019)."""

from __future__ import annotations

from hipstraw_mm.context import CommandResult, Context
from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.models import MarketCandidate


def candidates(ctx: Context, program_id: str) -> CommandResult:
    program = ctx.store.get_program(program_id)
    if program is None:
        raise PreconditionError(f"program {program_id} not found; run `hipstraw-mm intake` first")
    ids = []
    for context in program["experimentContexts"]:
        candidate = MarketCandidate(
            candidateId=f"{program_id}__{context['id']}",
            programId=program_id,
            experimentContextId=context["id"],
            label=context["label"],
        )
        ctx.store.upsert_candidate(candidate.model_dump())
        ids.append(candidate.candidateId)
    return CommandResult(
        "candidates",
        message="\n".join(["candidates:", *(f"  {i}" for i in ids)]),
        counts={"candidates": len(ids)},
    )
