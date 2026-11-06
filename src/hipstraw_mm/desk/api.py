"""The desk's HTTP API (FastAPI), for the Next.js app in web/. It calls the desk's operations and nothing else.

Every change names the acting person and role (headers X-Hipstraw-Actor and X-Hipstraw-Role) and passes the
authority gate, which refuses a missing or unknown role. The server binds to the loopback address only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hipstraw_mm.desk.service import AuthorityError, Desk, StaleError
from hipstraw_mm.errors import UsageError

THESES = Path("input/demand/theses")


class DecisionIn(BaseModel):
    action: Literal["approve", "return"]
    payloadHash: str
    note: str = ""


def create_app(desk: Desk, *, seed: Path | None = THESES) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if seed is not None and not desk.store.cases():
            desk.seed(seed)
        yield

    app = FastAPI(title="Hipstraw reviewer desk", version="0.1", lifespan=lifespan)

    @app.exception_handler(AuthorityError)
    async def _forbidden(_r: Request, exc: AuthorityError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(StaleError)
    async def _stale(_r: Request, exc: StaleError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(UsageError)
    async def _bad(_r: Request, exc: UsageError) -> JSONResponse:
        status = 404 if str(exc).startswith("no case ") else 422
        return JSONResponse({"detail": str(exc)}, status_code=status)

    def who(actor: str | None, role: str | None) -> tuple[str, str]:
        if not actor or not role:
            raise AuthorityError("every change names the acting person and role (X-Hipstraw-Actor, X-Hipstraw-Role)")
        return actor, role

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "cases": len(desk.store.cases()), "ledger": desk.store.verify()}

    @app.get("/api/offerings")
    def offerings() -> list[dict[str, Any]]:
        return desk.offerings()

    @app.get("/api/cases")
    def cases() -> list[dict[str, Any]]:
        return [desk.summary(c) for c in desk.store.cases()]

    @app.get("/api/cases/{case_id}")
    def case(case_id: str) -> dict[str, Any]:
        return desk.detail(case_id)

    @app.get("/api/cases/{case_id}/events")
    def events(case_id: str, after: int = 0) -> list[dict[str, Any]]:
        return [e.model_dump() for e in desk.events(case_id, after)]

    @app.post("/api/requests", status_code=201)
    def submit(body: dict[str, Any], tasks: BackgroundTasks,
               x_hipstraw_actor: str | None = Header(default=None),
               x_hipstraw_role: str | None = Header(default=None)) -> dict[str, Any]:
        actor, role = who(x_hipstraw_actor, x_hipstraw_role)
        desk.authorize(role, "submit_request")
        new = desk.submit(desk.request_model(body), actor=actor, role=role)
        tasks.add_task(desk.run, new.id)  # the agent works the case after the response, step by step
        return desk.summary(new)

    @app.post("/api/cases/{case_id}/decision")
    def decide(case_id: str, body: DecisionIn,
               x_hipstraw_actor: str | None = Header(default=None),
               x_hipstraw_role: str | None = Header(default=None)) -> dict[str, Any]:
        actor, role = who(x_hipstraw_actor, x_hipstraw_role)
        desk.decide(case_id, action=body.action, payload_hash=body.payloadHash, actor=actor, role=role,
                    note=body.note)
        return desk.detail(case_id)

    @app.get("/api/library")
    def library() -> dict[str, Any]:
        return desk.library()

    @app.get("/api/ledger")
    def ledger(limit: int = 200) -> dict[str, Any]:
        events = desk.store.events()
        return {"verify": desk.store.verify(), "total": len(events),
                "events": [e.model_dump() for e in events[-limit:]][::-1]}

    @app.get("/api/{rest:path}")
    def unknown(rest: str) -> None:
        raise HTTPException(status_code=404, detail=f"unknown route: /api/{rest}")

    return app
