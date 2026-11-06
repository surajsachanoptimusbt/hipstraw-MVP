"""`hipstraw-mm desk ...`: the reviewer desk from the command line. The same operations as the API.

    desk serve                       the API for the web app (http://127.0.0.1:8000)
    desk submit --thesis F --as R    open a case for a thesis; the agent works it at once
    desk list | desk show CASE       the queue, one case
    desk decide CASE --action approve|return --payload HASH --as reviewer --actor NAME [--note]
    desk verify                      recompute the ledger's hash chain
"""

from __future__ import annotations

import argparse
from pathlib import Path

from hipstraw_mm.context import CommandResult
from hipstraw_mm.desk.service import DB_PATH, Desk
from hipstraw_mm.desk.store import DeskStore
from hipstraw_mm.foundry.walkthrough import load_thesis


def register(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
    common: argparse.ArgumentParser,
    common_after: argparse.ArgumentParser,
    parser_class: type[argparse.ArgumentParser],
) -> None:
    group = sub.add_parser("desk", parents=[common], help="the reviewer desk: requests, the agent's plans, approvals")
    dsub = group.add_subparsers(dest="desk_command", required=True, parser_class=parser_class)
    db = argparse.ArgumentParser(add_help=False)
    db.add_argument("--db", default=str(DB_PATH), help="the desk's SQLite file")

    p = dsub.add_parser("serve", parents=[common_after, db], help="serve the API for the web app on 127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--pace", type=float, default=0.6, help="seconds between the agent's steps, to follow them live")

    p = dsub.add_parser("submit", parents=[common_after, db], help="open a case for a thesis; the agent works it")
    p.add_argument("--thesis", required=True)
    p.add_argument("--as", dest="role", default="customer")
    p.add_argument("--actor", default="Customer")

    dsub.add_parser("list", parents=[common_after, db], help="the review queue")
    p = dsub.add_parser("show", parents=[common_after, db], help="one case: the Lines picked, waiting on whom")
    p.add_argument("case")

    p = dsub.add_parser("decide", parents=[common_after, db], help="approve or return the agent's plan")
    p.add_argument("case")
    p.add_argument("--action", choices=["approve", "return"], required=True)
    p.add_argument("--payload", required=True, help="the plan's payload hash, as shown")
    p.add_argument("--as", dest="role", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--note", default="")

    dsub.add_parser("verify", parents=[common_after, db], help="recompute the ledger's hash chain")


def dispatch(args: argparse.Namespace) -> CommandResult:
    desk = Desk(DeskStore(Path(args.db)), Path(args.config_dir))
    if args.desk_command == "serve":
        import uvicorn

        from hipstraw_mm.desk.api import create_app

        desk.pace = args.pace
        uvicorn.run(create_app(desk), host="127.0.0.1", port=args.port, log_level="warning")
        return CommandResult("desk serve", message="desk API stopped")
    if args.desk_command == "submit":
        case = desk.submit(load_thesis(Path(args.thesis), desk.rubric), actor=args.actor, role=args.role)
        case = desk.run(case.id)
        return CommandResult("desk submit", runId=case.id, status=case.state,
                             message=f"{case.id} {case.company}: {case.state.replace('_', ' ')}, waiting on "
                                     f"{case.waitingOn}; plan {case.payloadHash}", data=desk.summary(case))
    if args.desk_command == "list":
        rows = [desk.summary(c) for c in desk.store.cases()]
        lines = [f"{r['id']}  {r['company']:<12} {r['caseType']:<18} {r['state'].replace('_', ' '):<15} "
                 f"waiting on {r['waitingOn']}" for r in rows]
        return CommandResult("desk list", message="\n".join(lines) or "no cases", counts={"cases": len(rows)},
                             data={"cases": rows})
    if args.desk_command == "show":
        d = desk.detail(args.case)
        lines = [f"{d['case']['id']} {d['case']['company']}: {d['case']['state'].replace('_', ' ')}, waiting on "
                 f"{d['case']['waitingOn']}", f"  plan {d['payloadHash']}"]
        for h in (d["recommendation"] or {}).get("hypotheses", []):
            lines.append(f"  {h['id']} {h['name']}: " + ", ".join(
                f"{t['taskId']} {t['lineId'] or '-'}" for t in h["tasks"]))
        return CommandResult("desk show", runId=args.case, status=d["case"]["state"], message="\n".join(lines),
                             data=d)
    if args.desk_command == "decide":
        case = desk.decide(args.case, action=args.action, payload_hash=args.payload, actor=args.actor,
                           role=args.role, note=args.note)
        return CommandResult("desk decide", runId=case.id, status=case.state,
                             message=f"{case.id}: {case.state}, waiting on {case.waitingOn}")
    result = desk.store.verify()
    return CommandResult("desk verify", status="ok" if result["ok"] else "broken",
                         message=f"ledger: {result['checked']} events checked, "
                                 + ("chain intact" if result["ok"] else f"broken at event {result['brokenAt']}"),
                         data=result)
