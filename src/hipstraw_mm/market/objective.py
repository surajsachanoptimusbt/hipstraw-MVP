"""Objective documents: PDFs uploaded with a mandate become part of the run's objective bundle.

The Market Manager accepts them when it opens the run (right `ingest_objective`). Their text is stored
once in `objectiveDocuments` and joined to the program objective, so vichara prompts and the grounding
check read the same text.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hipstraw_mm.errors import PreconditionError, UsageError

Doc = dict[str, Any]


def read_pdf(path: Path) -> list[str]:
    """One whitespace-normalized string per page. Raises UsageError for a file that is not a readable PDF."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    if not path.is_file():
        raise UsageError(f"objective PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise UsageError(f"objective document must be a .pdf file: {path.name}")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise UsageError(f"{path.name} is encrypted; upload an unencrypted PDF")
        pages = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    except PdfReadError as exc:
        raise UsageError(f"{path.name} is not a readable PDF ({exc})") from exc
    if not any(pages):
        raise UsageError(f"{path.name} has no extractable text (it may be scanned images)")
    return pages


def ingest_documents(ctx: Any, tracer: Any, run_id: str, paths: list[Path], max_chars: int) -> list[Doc]:
    """Store each PDF as an `objectiveDocuments` record; text past `max_chars` in total is cut and reported."""
    budget = max_chars
    stored: list[Doc] = []
    unresolved: list[Doc] = []
    for n, path in enumerate(paths, start=1):
        with tracer.step("market_manager", "market_manager", "ingest_objective", right="ingest_objective") as step:
            step.set_inputs({"fileName": path.name})
            raw = path.read_bytes()
            pages = read_pdf(path)
            total = sum(len(p) for p in pages)
            kept: list[str] = []
            for page in pages:
                take = page[: max(0, budget)]
                kept.append(take)
                budget -= len(take)
            kept_chars = sum(len(p) for p in kept)
            doc = {
                "documentId": f"{run_id}__doc{n}",
                "marketRunId": run_id,
                "fileName": path.name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "pageCount": len(pages),
                "chars": total,
                "keptChars": kept_chars,
                "truncated": kept_chars < total,
                "pages": kept,
            }
            ctx.store.create_objective_document(doc)
            if doc["truncated"]:
                unresolved.append({
                    "kind": "objective_document",
                    "ref": path.name,
                    "reason": f"only {kept_chars} of {total} characters fit the objective limit ({max_chars})",
                })
            step.set_outputs({k: doc[k] for k in ("documentId", "pageCount", "chars", "keptChars", "truncated")})
            stored.append(doc)
    if unresolved:
        run = ctx.store.get_market_run(run_id) or {}
        run["unresolved"] = [*run.get("unresolved", []), *unresolved]
        ctx.store.upsert_market_run(run)
    return stored


def documents_text(docs: list[Doc]) -> str:
    parts = []
    for doc in docs:
        body = "\n".join(p for p in doc.get("pages", []) if p)
        if body:
            parts.append(f"[Document: {doc['fileName']}]\n{body}")
    return "\n\n".join(parts)


def resolve_pdf_paths(values: list[str] | None) -> list[Path]:
    paths = [Path(v).expanduser() for v in values or []]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise PreconditionError(f"objective PDF not found: {', '.join(missing)}")
    return paths
