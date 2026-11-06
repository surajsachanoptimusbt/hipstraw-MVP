"""The predefined demand validation repertoire as a worksheet (Nov 6): the tasks a Line is decided for, the Lines
(strategies) each task may take, the Moves (methods) they are made of, and the metrics the Moves move.

Written from config/foundry, so the worksheet and the system always agree. Same layout as
docs/hipstraw_moves_and_lines.xlsx: one sheet each, a navy header row, Arial 10, wrapped text, frozen header and
ID column, filters, a Summary of counts as formulas over the other sheets, and Notes on the sources.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from hipstraw_mm.errors import PreconditionError
from hipstraw_mm.foundry.demand import DemandRubric

HEADER_FILL = "1F3864"
FONT = "Arial"
Sheet = tuple[list[tuple[str, int]], list[list[Any]]]  # columns (header, width) and rows


def sheets(rubric: DemandRubric) -> dict[str, Sheet]:
    """The Tasks, Lines, Moves and Metrics sheets."""
    dimension = {q: g.name for g in rubric.demandDimensions for q in g.questions}
    task_of = {t.phase: t for t in rubric.tasks}
    used_in: dict[str, list[str]] = {}
    for line in rubric.lines:
        for move_id in dict.fromkeys(m for stage in line.stages for m in stage):
            used_in.setdefault(move_id, []).append(line.id)

    def tests(question_ids: list[str]) -> str:
        names = [g.name for g in rubric.demandDimensions if set(g.questions) & set(question_ids)]
        return ", ".join(names) or "none: it judges or reviews the evidence"

    tasks: list[list[Any]] = [
        [t.id, t.name, t.question, t.phase, ", ".join(f"{line.id} {line.name}" for line in rubric.task_lines(t)),
         "Playbook rules: the first eligible Line, in playbook order"] for t in rubric.tasks]
    lines: list[list[Any]] = []
    for line in rubric.lines:
        task = task_of.get(line.phase)
        when = [f"{k} is {' or '.join(v)}" for k, v in line.useWhen.items()]
        when += [f"not when {k} is {' or '.join(v)}" for k, v in line.excludeWhen.items()]
        questions = [q for stage in line.stages for m in stage for q in rubric.tested_by(m)]
        lines.append([line.id, line.name, f"{task.id} {task.name}" if task else f"phase {line.phase}",
                      line.purpose, "; ".join(when) or "any market", "Yes" if line.endsProgram else "No",
                      " → ".join(", ".join(stage) for stage in line.stages), line.exit, tests(questions)])
    moves: list[list[Any]] = []
    for mv in rubric.moves:
        questions = rubric.tested_by(mv.id)
        moves.append([mv.id, mv.name, mv.effect, "Yes" if mv.effect == "E3" else "No", mv.does,
                      "\n".join(f"{n}. {x}" for n, x in enumerate(mv.how, 1)), mv.needs,
                      "; ".join(f"{t.replace('_', ' ')} (rung {rubric.evidenceTypes[t][1:]})" for t in mv.records)
                      or "-",
                      tests(questions), ", ".join(questions) or "-", ", ".join(mv.fills) or "-", mv.watchOut,
                      ", ".join(used_in.get(mv.id, [])) or "-"])
    profiles = list(rubric.profiles)
    metrics: list[list[Any]] = [
        [i.id, i.label, dimension.get(i.fills, ""), f"{i.fills} {rubric.dimension(i.fills).title}",
         *[rubric.profiles[p][i.target] for p in profiles], ", ".join(i.by)] for i in rubric.scorecard]
    return {
        "Tasks": ([("ID", 7), ("Task", 30), ("Question", 50), ("Phase", 8), ("Lines to choose from", 40),
                   ("Decided by", 28)], tasks),
        "Lines": ([("ID", 7), ("Line", 22), ("Task", 30), ("Strategy", 46), ("Use when (rule)", 28),
                   ("Ends the program", 10), ("Stages (in order; Moves in one stage run together)", 34),
                   ("Done when", 46), ("Tests (demand dimensions)", 32)], lines),
        "Moves": ([("ID", 7), ("Move", 30), ("Effect class", 9), ("Needs a charter", 10),
                   ("What it does ({placeholders} are filled in per hypothesis)", 50), ("How", 56), ("Needs", 34),
                   ("Records (evidence type, rung)", 34), ("Tests (demand dimensions)", 30), ("Rubric questions", 18),
                   ("Metrics it moves", 18), ("Watch out", 36), ("Used in Lines", 14)], moves),
        "Metrics": ([("ID", 7), ("Metric", 40), ("Demand dimension", 18), ("Informs", 40),
                     *[(f"Target: {p.replace('_', ' ')}", 12) for p in profiles], ("Gathered by", 16)], metrics),
    }


def summary(rubric: DemandRubric, last: dict[str, int]) -> list[tuple[str, str]]:
    """Counts as formulas over the other sheets (`last` is each sheet's last data row), so they follow any edit."""
    return [
        ("Tasks", f"=COUNTA(Tasks!A2:A{last['Tasks']})"),
        ("Lines", f"=COUNTA(Lines!A2:A{last['Lines']})"),
        ("Moves", f"=COUNTA(Moves!A2:A{last['Moves']})"),
        ("Metrics", f"=COUNTA(Metrics!A2:A{last['Metrics']})"),
        ("", ""),
        ("Moves by effect class", ""),
        *[(f"{e}: {what}", f'=COUNTIF(Moves!C2:C{last["Moves"]},"{e}")')
          for e, what in (("E0", "internal"), ("E1", "reads outside sources"),
                          ("E3", "contacts people, publishes or spends (needs a charter)"))],
        ("", ""),
        ("Lines per task", ""),
        *[(f"{t.id} {t.name}", f'=COUNTIF(Lines!C2:C{last["Lines"]},"{t.id} *")') for t in rubric.tasks],
        ("Lines that end the program", f'=COUNTIF(Lines!F2:F{last["Lines"]},"Yes")'),
    ]


def write_worksheet(rubric: DemandRubric, path: Path) -> Path:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise PreconditionError("the worksheet needs openpyxl: pip install openpyxl") from exc

    wb = Workbook()
    wb.remove(wb.active)
    body, bold, wrap = Font(name=FONT, size=10), Font(name=FONT, size=10, bold=True), \
        Alignment(wrap_text=True, vertical="top")
    data = sheets(rubric)
    for title, (columns, rows) in data.items():
        ws = wb.create_sheet(title)
        ws.append([c for c, _ in columns])
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for row_cells in ws.iter_rows(min_row=2):
            for cell in row_cells:
                cell.font, cell.alignment = body, wrap
        for n, (_, width) in enumerate(columns, 1):
            ws.column_dimensions[get_column_letter(n)].width = width
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.create_sheet("Summary")
    ws.append(["Demand validation: predefined tasks, Lines, Moves and metrics", ""])
    ws.append(["Counts are formulas over the other sheets", ""])
    ws.append(["", ""])
    for label, formula in summary(rubric, {title: len(rows) + 1 for title, (_, rows) in data.items()}):
        ws.append([label, formula])
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            cell.font = bold if cell.value in ("Moves by effect class", "Lines per task") else body
    ws["A1"].font = Font(name=FONT, size=12, bold=True)
    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 10

    ws = wb.create_sheet("Notes")
    notes = [
        ("Sources", ""),
        ("Generated", f"{date.today().isoformat()} from config/foundry by `hipstraw-mm demand worksheet`; edit "
                      "the YAML and regenerate rather than editing this file"),
        ("Repertoire", f"{rubric.repertoireVersion}: config/foundry/demand_repertoire.yaml (tasks, Lines, Moves)"),
        ("Rubric", f"{rubric.version} ({rubric.qualification}): config/foundry/demand_evidence.yaml (demand "
                   "dimensions, rubric questions, metrics and their targets by kind of buyer)"),
        ("How a Line is picked", "By the playbook's rules, never by a model (Nov 6 meeting). For each task of "
                                 "each hypothesis, a Line is eligible when its Use when conditions hold; the "
                                 "eligible Lines are ranked in playbook order (the order of this sheet) and the "
                                 "first is picked. Jev may later help rank Lines within a scenario; it stays "
                                 "deferred under constitution XI"),
        ("Effect classes", "E0 internal; E1 reads outside sources; E3 contacts people, publishes or spends, and "
                           "needs an approved charter (Blueprint Appendix E). In G0 people carry out E3 Moves"),
        ("Targets", "Hipstraw's starting values, to be calibrated in the field; no published source sets them"),
    ]
    for label, text in notes:
        ws.append([label, text])
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            cell.font, cell.alignment = body, wrap
    ws["A1"].font = bold
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 100

    wb.calculation.fullCalcOnLoad = True  # no cached values are written; the spreadsheet computes them on open
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
