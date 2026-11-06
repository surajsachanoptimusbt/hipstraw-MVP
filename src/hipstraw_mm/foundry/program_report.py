"""The demand validation walkthrough as a page (self-contained HTML, opened from disk) and as markdown.

Both show the same things, in the order the Nov 5 meeting asked for them: the walkthrough log (what the agent did
and why, every Line and Move it picked), then for each hypothesis its demand dimensions with the Lines, Moves and
evidence that test them, the Lines considered, each chosen Line and its Moves in detail, and the scorecard."""

from __future__ import annotations

from html import escape

from hipstraw_mm.foundry.walkthrough import (
    DimensionPlan,
    EvidenceKind,
    HypothesisPlan,
    LogLine,
    PlannedLine,
    PlannedMove,
    Walkthrough,
)

_STATE = {"met": "met", "partly": "partly", "not_met": "not met", "unknown": "unknown",
          "not_applicable": "not applicable"}
_EFFECT = {"E0": "internal", "E1": "reads outside sources", "E2": "model inference",
           "E3": "contacts people, publishes or spends: needs an approved charter"}
_MARKET = {"buyer": "Buyer", "motion": "Sold", "recurring": "Bought again", "problem": "Problem shown"}
_STATUS = {"done": "done", "next": "next", "planned": "planned"}
_HOW_TO_READ = [
    ("Line", "a strategy: ordered stages of Moves, chosen for a market by its conditions"),
    ("Move", "a method: one action, filled in for this market, that records evidence of set types"),
    ("Demand dimension", "what the evidence must show (problem, buyer, solution, payment, recurring, reachable); "
                         "each is judged by its own rubric questions and they are never added up"),
    ("Rung", "where evidence sits on the ladder: rungs 0 to 2 (simulation, desk research, attention) never count "
             "as demand; rungs 3 to 7 (interest, conversation, commitment, payment, repeat payment) do"),
]


def _value(key: str, value: str) -> str:
    if key == "recurring":
        return "yes" if value == "true" else "no"
    return value.replace("_", "-") if key == "motion" else value


def _rung(k: EvidenceKind) -> str:
    return f"{k.type.replace('_', ' ')} (rung {k.level[1:]})"


# --- markdown -----------------------------------------------------------------------------------------------------

def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _md_log(lines: list[LogLine]) -> list[str]:
    return [f"{'  ' * (ln.depth + 1)}- {ln.text}" + (f" **[{ln.tag}]**" if ln.tag else "") for ln in lines]


def _md_move(m: PlannedMove) -> list[str]:
    status = f"{m.effect}, {_STATUS[m.status]}" + (", needs an approved charter" if m.needsCharter else "")
    out = [f"- **Stage {m.stage}. {m.id} {m.name}** ({status}). {m.does}"]
    out += [f"  {n}. {x}" for n, x in enumerate(m.how, 1)]
    if m.needs:
        out.append(f"  - Needs: {m.needs}")
    if m.records:
        out.append("  - Records: " + "; ".join(k.label for k in m.records))
    if m.dimensions:
        out.append(f"  - Tests: {', '.join(m.dimensions)} ({', '.join(m.tests)})")
    out += [f"  - Pass when: {x}" for x in m.passWhen]
    out += [f"  - Gives: {m.output}", f"  - Watch out: {m.watchOut}"]
    return out


def render_program_markdown(w: Walkthrough) -> str:
    out = [f"# Demand validation program: {w.product}", "", f"> {w.scope}", "",
           f"**Thesis.** {w.statement}", "",
           f"Market: {w.market}" + (f", {w.geography}" if w.geography else "") + f". As of {w.asOf.isoformat()}. "
           f"Rubric `{w.rubricVersion}` ({w.qualification}), repertoire `{w.repertoireVersion}`.", ""]
    out += [f"- **{term}**: {text}" for term, text in _HOW_TO_READ]
    out += ["", "## Walkthrough log", ""]
    for s in w.steps:
        out += [f"### {s.n}. {s.title}", "", f"_{s.summary}_", ""] + _md_log(s.lines) + [""]
    for p in w.hypotheses:
        out += [f"## {p.id} {p.name}", "", f"{p.demand}.", "",
                f"- Segment: {p.segment}", f"- Offering: {p.offering}", f"- Who decides and pays: {p.buyerRole}",
                f"- Now: {p.assessment.decisionText} ({p.checkpoint})", f"- First action: {p.firstAction}", "",
                "### Demand dimensions: Lines, Moves and evidence", "",
                "| Demand dimension | Now | Lines (strategies) | Moves (methods) | Evidence recorded | Indicators |",
                "|---|---|---|---|---|---|"]
        for d in p.dimensions:
            now = ", ".join(f"{q.id} {_STATE[q.state]}" for q in d.questions)
            out.append(f"| {d.name}: {_cell(d.question)} | {now} | {_cell(', '.join(d.lines) or '-')} | "
                       f"{_cell(', '.join(d.moves) or '-')} | {_cell('; '.join(_rung(k) for k in d.evidence) or '-')}"
                       f" | {_cell('; '.join(f'{i.label} {i.current}/{i.target:g}' for i in d.indicators if i.state != 'not_applicable') or '-')} |")  # noqa: E501
        out += ["", "### Lines considered", "", "| Phase | Line | Verdict | Why |", "|---|---|---|---|"]
        out += [f"| {c.phase} | {c.id} {c.name} | {'chosen' if c.chosen else 'fits' if c.fits else 'does not fit'} | "
                f"{_cell('; '.join(c.reasons))} |" for c in p.lines]
        out += ["", "### Program: the chosen Lines and their Moves", ""]
        for pl in p.program:
            out += [f"#### Phase {pl.phase}, {pl.phaseName}: {pl.id} {pl.name}", "",
                    f"Strategy: {pl.purpose}. Why this Line: {'; '.join(pl.why)}. "
                    f"Tests: {', '.join(pl.tests) or 'none'}. Done when: {pl.exit}.", ""]
            for stage in pl.stages:
                for m in stage:
                    out += _md_move(m)
            out.append("")
        out += ["### Scorecard", "", "| Demand dimension | Indicator | Now | Target | Gathered by |",
                "|---|---|---|---|---|"]
        out += [f"| {d.name} | {i.label} | {'n/a' if i.state == 'not_applicable' else i.current} | {i.target:g} | "
                f"{', '.join(i.by)} |" for d in p.dimensions for i in d.indicators]
        out.append("")
    out += ["## Repertoire", "", "### Lines (strategies)", "", "| ID | Line | Phase | Use when | Stages | Used by |",
            "|---|---|---|---|---|---|"]
    out += [f"| {x.id} | {x.name} | {x.phase} | {'; '.join(x.useWhen)} | "
            f"{' > '.join(', '.join(s) for s in x.stages)} | {', '.join(x.usedBy) or '-'} |" for x in w.lines]
    out += ["", "### Moves (methods)", "", "| ID | Move | Effect | Tests | Records | Used by |",
            "|---|---|---|---|---|---|"]
    out += [f"| {x.id} | {x.name} | {x.effect} | {', '.join(x.dimensions) or '-'} | "
            f"{'; '.join(_rung(k) for k in x.records) or '-'} | {', '.join(x.usedBy) or '-'} |" for x in w.moves]
    out += ["", "## Decisions needed", ""] + [f"- {d}" for d in w.openDecisions] + [""]
    return "\n".join(out)


# --- the page -----------------------------------------------------------------------------------------------------

_CSS = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#1d2430; --muted:#5d6878; --line:#dde2e8; --accent:#0f5e63;
  --accent-soft:#e6f0f0; --e3:#8a4b08; --e3-soft:#fbf0e3; --ok:#1d6b3a; --ok-soft:#e5f3ea; --off:#8b95a1;
  --next:#3d3aa8; --next-soft:#ebeafb; --warn:#a3261b; --warn-soft:#fbe9e7; }
@media (prefers-color-scheme: dark) { :root { --bg:#12161c; --card:#1a2028; --ink:#e3e8ee; --muted:#9aa5b3;
  --line:#2c3440; --accent:#5bb8bd; --accent-soft:#1c3032; --e3:#f0b46e; --e3-soft:#352816; --ok:#7fd39c;
  --ok-soft:#183223; --off:#6b7480; --next:#a9a6ff; --next-soft:#25243f; --warn:#ff9a8f; --warn-soft:#3a1d1a; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width:1180px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:26px; margin:4px 0 8px; } h2 { font-size:20px; margin:0 0 4px; }
h3 { font-size:13px; margin:26px 0 10px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.eyebrow { color:var(--accent); font-weight:600; font-size:12.5px; letter-spacing:.05em; text-transform:uppercase; }
.muted { color:var(--muted); } .small { font-size:13px; } .mono { font-family:Consolas, monospace; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin:16px 0; }
.note { background:var(--accent-soft); border-left:3px solid var(--accent); padding:10px 14px; border-radius:6px; }
.read { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px; margin:12px 0; }
.read div { border:1px solid var(--line); border-radius:8px; padding:8px 12px; background:var(--card);
  font-size:13.5px; }
nav { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0; }
nav a { padding:5px 12px; border:1px solid var(--line); border-radius:999px; text-decoration:none; color:var(--ink);
  background:var(--card); font-size:13px; }
.meta { display:flex; flex-wrap:wrap; gap:6px 18px; font-size:13px; color:var(--muted); }
.chip { display:inline-block; padding:1px 9px; border-radius:999px; font-size:12px; font-weight:600;
  background:var(--accent-soft); color:var(--accent); margin:1px 4px 1px 0; white-space:nowrap; }
.chip.e3 { background:var(--e3-soft); color:var(--e3); } .chip.ok { background:var(--ok-soft); color:var(--ok); }
.chip.off { background:transparent; color:var(--off); border:1px solid var(--line); }
.chip.next { background:var(--next-soft); color:var(--next); }
.chip.warn { background:var(--warn-soft); color:var(--warn); }
.log { margin:0; padding-left:0; list-style:none; counter-reset:step; }
.log > li { border-left:2px solid var(--line); padding:0 0 14px 20px; position:relative; }
.log > li::before { counter-increment:step; content:counter(step); position:absolute; left:-12px; top:1px;
  width:22px; height:22px; border-radius:50%; background:var(--accent); color:#fff; font-size:12px;
  display:flex; align-items:center; justify-content:center; }
.log summary { cursor:pointer; } .log > li > details > summary { font-weight:600; }
.log > li > details > summary .muted { font-weight:400; }
.tree, .tree ul { list-style:none; margin:4px 0 0; padding-left:16px; }
.tree li { margin:3px 0; } .tree li.d2, .tree li.d3 { font-size:13px; } .tree li.d3 { color:var(--muted); }
.tree details > summary { list-style-position:outside; }
table { width:100%; border-collapse:collapse; font-size:13.5px; }
th, td { text-align:left; vertical-align:top; padding:7px 8px; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; font-size:12.5px; }
tr.chosen td { background:var(--ok-soft); } tr.group td { background:var(--bg); font-weight:600; }
.scroll { overflow-x:auto; } table.dims { min-width:860px; } table.dims td > div { margin-bottom:3px; }
.flow { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:10px; }
.flow > div { border:1px solid var(--line); border-radius:8px; padding:10px 12px; position:relative; }
.flow .ph { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
.flow .ln { font-weight:700; margin:2px 0 6px; } .flow ol { margin:0; padding-left:20px; font-size:13px; }
.flow .none { color:var(--off); font-size:13px; } .flow li.done { color:var(--muted); text-decoration:line-through; }
.flow li.next { font-weight:700; color:var(--next); }
.market { display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px; }
.market div { border:1px solid var(--line); border-radius:8px; padding:8px 10px; }
.market b { display:block; font-size:16px; }
.line { border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:8px; padding:12px 14px;
  margin:14px 0; }
.line .head { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; }
.line .head b { font-size:16px; }
.line dl { display:grid; grid-template-columns:120px 1fr; gap:4px 12px; margin:8px 0 4px; font-size:13.5px; }
.line dt { color:var(--muted); }
.stage { display:grid; grid-template-columns:64px 1fr; gap:8px; margin:10px 0; }
.stage .n { color:var(--muted); font-size:12px; font-weight:600; padding-top:12px; text-transform:uppercase; }
.moves { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:8px; }
.move { border:1px solid var(--line); border-radius:8px; padding:10px 12px; background:var(--card); font-size:13.5px; }
.move.done { opacity:.62; } .move.next { border-color:var(--next); box-shadow:0 0 0 1px var(--next); }
.move .t { font-weight:700; font-size:14.5px; } .move .k { color:var(--muted); font-size:11.5px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; margin-top:8px; }
.move ol, .move ul { margin:2px 0 0; padding-left:20px; } .move p { margin:2px 0 0; }
.score { display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px; margin-bottom:10px; }
.dimhead { font-weight:600; margin:12px 0 6px; font-size:14px; }
.tile { border:1px solid var(--line); border-radius:8px; padding:10px 12px; }
.tile .v { font-size:22px; font-weight:700; } .tile .v span { font-size:14px; color:var(--muted); font-weight:500; }
.bar { height:5px; background:var(--line); border-radius:3px; margin:6px 0; overflow:hidden; }
.bar i { display:block; height:100%; background:var(--accent); }
@media (max-width:640px) { .stage { grid-template-columns:1fr; } .stage .n { padding:0; }
  .line dl { grid-template-columns:1fr; } .moves { grid-template-columns:1fr; } }
"""


def _chip(text: str) -> str:
    t = text.lower()
    tone = ("ok" if t in ("chosen", "done", "met", "demand", "reached") or t.startswith("continue")
            else "next" if t in ("next", "first action")
            else "e3" if t in ("needs charter", "e3")
            else "warn" if t in ("not met", "fix first", "stop or reframe", "revise")
            else "off" if t in ("not chosen", "fits, not chosen", "unknown", "not demand", "not applicable", "planned",
                              "not used")
            else "")
    return f'<span class="chip {tone}">{escape(text)}</span>'


def _tree(lines: list[LogLine]) -> str:
    """The step's lines as a nested list; a line with deeper lines below it folds them (open down to depth 1)."""
    depths: list[int] = []
    for ln in lines:  # a line is at most one level below the line before it
        depths.append(min(ln.depth, depths[-1] + 1) if depths else 0)
    out: list[str] = []
    for n, ln in enumerate(lines):
        depth, nxt = depths[n], depths[n + 1] if n + 1 < len(lines) else 0
        text = escape(ln.text) + (" " + _chip(ln.tag) if ln.tag else "")
        if nxt > depth:
            out.append(f'<li class="d{depth}"><details{" open" if depth < 2 else ""}><summary>{text}</summary><ul>')
        else:
            out.append(f'<li class="d{depth}">{text}</li>' + "</ul></details></li>" * (depth - nxt))
    return f'<ul class="tree">{"".join(out)}</ul>'


def _kinds(kinds: list[EvidenceKind]) -> str:
    return "".join(f'<span class="chip {"ok" if k.demand else "off"}" title="{escape(k.rung)}">{escape(_rung(k))}'
                   f"</span>" for k in kinds) or '<span class="muted">none</span>'


def _move(m: PlannedMove) -> str:
    chips = (f'<span class="chip{" e3" if m.effect == "E3" else ""}" title="{escape(_EFFECT[m.effect])}">'
             f"{m.effect} {escape(_EFFECT[m.effect].split(':')[0])}</span>" + _chip(_STATUS[m.status]))
    how = "".join(f"<li>{escape(x)}</li>" for x in m.how)
    head = f'<div class="t"><span class="mono">{m.id}</span> {escape(m.name)}</div><div>{chips}</div>'
    if not m.records and not m.tests:  # a Move that judges the evidence, shown short
        return f"""<div class="move {m.status}">{head}
  <p>{escape(m.does)}</p><details><summary class="muted small">How</summary><ol>{how}</ol></details>
  <div class="k">Gives</div><p>{escape(m.output)}</p></div>"""
    tests = ("".join(f'<span class="chip">{escape(d)}</span>' for d in m.dimensions)
             + f' <span class="muted small">{", ".join(m.tests)}</span>')
    passes = ('<div class="k">Pass when</div><ul>' + "".join(f"<li>{escape(x)}</li>" for x in m.passWhen)
              + "</ul>") if m.passWhen else ""
    return f"""<div class="move {m.status}">{head}
  <div class="k">For this market</div><p>{escape(m.does)}</p>
  <div class="k">How</div><ol>{how}</ol>
  <div class="k">Needs</div><p>{escape(m.needs)}</p>
  <div class="k">Records</div><p>{_kinds(m.records)}</p>
  <div class="k">Tests</div><p>{tests}</p>
  {passes}
  <div class="k">Gives</div><p>{escape(m.output)}</p>
  <div class="k">Watch out</div><p>{escape(m.watchOut)}</p>
</div>"""


def _line(pl: PlannedLine) -> str:
    stages = "".join(f'<div class="stage"><div class="n">Stage {n}</div><div class="moves">'
                     + "".join(_move(m) for m in stage) + "</div></div>" for n, stage in enumerate(pl.stages, 1))
    tests = "".join(f'<span class="chip">{escape(d)}</span>' for d in pl.tests) or '<span class="muted">-</span>'
    return f"""<div class="line">
  <div class="head"><span class="muted small">Phase {pl.phase} · {escape(pl.phaseName)}</span>
    <b><span class="mono">{pl.id}</span> {escape(pl.name)}</b>{_chip("chosen")}</div>
  <dl><dt>Strategy</dt><dd>{escape(pl.purpose)}</dd>
    <dt>Why this Line</dt><dd>{escape("; ".join(pl.why))}</dd>
    <dt>Tests</dt><dd>{tests}</dd><dt>Done when</dt><dd>{escape(pl.exit)}</dd></dl>
  {stages}
</div>"""


def _flow(p: HypothesisPlan, phases: dict[int, str]) -> str:
    cols = []
    for phase, name in sorted(phases.items()):
        chosen = next((pl for pl in p.program if pl.phase == phase), None)
        if chosen:
            moves = "".join(f'<li class="{m.status}">{m.id} {escape(m.name)}</li>'
                            for stage in chosen.stages for m in stage)
            body = f'<div class="ln">{chosen.id} {escape(chosen.name)}</div><ol>{moves}</ol>'
        else:
            why = "; ".join(f"{c.id} {c.name}: {', '.join(r for r in c.reasons if 'needs' in r or 'not' in r)}"
                            for c in p.lines if c.phase == phase)
            body = f'<div class="none">No Line in this phase. {escape(why)}</div>'
        cols.append(f'<div><div class="ph">Phase {phase} · {escape(name)}</div>{body}</div>')
    return f'<div class="flow">{"".join(cols)}</div>'


def _dimension_row(d: DimensionPlan) -> str:
    now = "".join(f'<div>{q.id} {_chip(_STATE[q.state])}</div>' for q in d.questions)
    lines = "".join(f"<div>{escape(x)}</div>" for x in d.lines) or '<span class="muted">none</span>'
    moves = "".join(f"<div>{escape(x)}</div>" for x in d.moves) or '<span class="muted">none</span>'
    inds = "".join(f"<div>{escape(i.label)}: <b>{i.current}</b> / {i.target:g}</div>" for i in d.indicators
                   if i.state != "not_applicable") or '<span class="muted">not applicable</span>'
    return (f"<tr><td><b>{escape(d.name)}</b><div class='muted small'>{escape(d.question)}</div></td><td>{now}</td>"
            f"<td>{lines}</td><td>{moves}</td><td>{_kinds(d.evidence)}</td><td>{inds}</td></tr>")


def _hypothesis(p: HypothesisPlan, phases: dict[int, str]) -> str:
    a = p.assessment
    market = "".join(f'<div><span class="muted small">{_MARKET[k]}</span><b>{escape(_value(k, v))}</b>'
                     f'<span class="muted small">{escape(p.marketWhy[k])}</span></div>' for k, v in p.market.items())
    considered = ""
    for c in p.lines:
        conds = "".join(f'<span class="chip {"ok" if ("as needed" in r or "every market" in r) else "off"}">'
                        f'{"✓" if ("as needed" in r or "every market" in r) else "✗"} {escape(r)}</span>'
                        for r in c.reasons)
        verdict = "chosen" if c.chosen else ("fits, not chosen" if c.fits else "not chosen")
        considered += (f'<tr class="{"chosen" if c.chosen else ""}"><td>{c.phase}</td>'
                       f'<td><b>{c.id}</b> {escape(c.name)}</td><td>{conds}</td><td>{_chip(verdict)}</td></tr>')
    tiles = ""
    for d in p.dimensions:
        shown = [i for i in d.indicators if i.state != "not_applicable"]
        if not d.indicators:
            continue
        tiles += f'<div class="dimhead">{escape(d.name)}</div><div class="score">'
        if not shown:
            tiles += ('<div class="tile"><div class="muted small">Not applicable: the offering is bought once'
                      "</div></div>")
        for i in shown:
            pct = min(100, round(100 * i.current / i.target)) if i.target else 0
            tiles += (f'<div class="tile"><div class="small">{escape(i.label)}</div>'
                      f'<div class="v">{i.current} <span>/ {i.target:g}</span></div>'
                      f'<div class="bar"><i style="width:{pct}%"></i></div>'
                      f'<div class="muted small">{i.id} · {i.fills} · by {", ".join(i.by)}</div></div>')
        tiles += "</div>"
    questions = ""
    for d in p.dimensions:
        questions += f'<tr class="group"><td colspan="4">{escape(d.name)}</td></tr>'
        questions += "".join(f"<tr><td>{q.id}</td><td>{escape(q.title)}</td><td>{_chip(_STATE[q.state])}</td>"
                             f"<td>{escape(q.reason)}</td></tr>" for q in d.questions)
    return f"""
<section class="card" id="{p.id}">
  <div class="eyebrow">Hypothesis {p.id} · priority {p.priority}</div>
  <h2>{escape(p.name)}</h2>
  <p>{escape(p.demand)}.</p>
  <div class="meta"><span><b>Segment:</b> {escape(p.segment)}</span><span><b>Offering:</b> {escape(p.offering)}</span>
    <span><b>Who decides and pays:</b> {escape(p.buyerRole)}</span></div>
  <p>{_chip(a.decision.replace('_', ' '))}{_chip(p.checkpoint)}
     <span class="muted small">{escape(a.decisionText)}</span></p>
  <div class="note"><b>First action.</b> {escape(p.firstAction)}</div>
  <h3>The program at a glance: one Line (strategy) per phase, its Moves (methods) in order</h3>
  {_flow(p, phases)}
  <h3>Demand dimensions: the Lines, Moves and evidence that test each</h3>
  <div class="scroll"><table class="dims"><colgroup><col style="width:19%"><col style="width:10%">
    <col style="width:13%"><col style="width:21%"><col style="width:22%"><col style="width:15%"></colgroup>
    <tr><th>Demand dimension</th><th>Rubric questions now</th><th>Lines (strategies)</th>
    <th>Moves (methods)</th><th>Evidence they record</th><th>Indicators</th></tr>
    {"".join(_dimension_row(d) for d in p.dimensions)}</table></div>
  <h3>Market read: what the Lines' conditions test</h3><div class="market">{market}</div>
  <h3>Lines considered, with each condition checked</h3>
  <div class="scroll"><table><tr><th>Phase</th><th>Line</th><th>Conditions</th><th>Verdict</th></tr>{considered}
  </table></div>
  <h3>The chosen Lines and their Moves, in detail</h3>
  {"".join(_line(pl) for pl in p.program)}
  <h3>Demand scorecard</h3>
  {tiles}
  <p class="muted small">Each indicator counts evidence from the segment against its target. They are never added
  up; the rubric's rules make the decision.</p>
  <h3>Rubric questions now</h3>
  <div class="scroll"><table><tr><th>ID</th><th>Question</th><th>Now</th><th>Why</th></tr>{questions}</table></div>
</section>"""


def _repertoire(w: Walkthrough) -> str:
    lines = "".join(
        f"<tr><td class='mono'>{x.id}</td><td><b>{escape(x.name)}</b><div class='muted small'>{escape(x.purpose)}"
        f"</div></td><td>{x.phase}</td><td>{escape('; '.join(x.useWhen))}</td>"
        f"<td class='mono small'>{escape(' > '.join(', '.join(s) for s in x.stages))}</td>"
        f"<td>{''.join(_chip(h) for h in x.usedBy) or _chip('not used')}</td></tr>" for x in w.lines)
    moves = "".join(
        f"<tr><td class='mono'>{x.id}</td><td>{escape(x.name)}</td><td>{x.effect}</td>"
        f"<td>{escape(', '.join(x.dimensions)) or '<span class=muted>judges the evidence</span>'}</td>"
        f"<td>{_kinds(x.records)}</td><td>{''.join(_chip(h) for h in x.usedBy) or _chip('not used')}</td></tr>"
        for x in w.moves)
    return f"""
<section class="card" id="repertoire"><h2>Repertoire: every Line and Move the agent could pick</h2>
  <p class="muted small">Repertoire {escape(w.repertoireVersion or '')}. Which rubric questions a Move tests is set
  by the rubric; the demand dimensions follow from them.</p>
  <h3>Lines (strategies)</h3>
  <div class="scroll"><table><tr><th>ID</th><th>Line</th><th>Phase</th><th>Use when</th><th>Stages of Moves</th>
    <th>Picked for</th></tr>{lines}</table></div>
  <h3>Moves (methods)</h3>
  <div class="scroll"><table><tr><th>ID</th><th>Move</th><th>Effect</th><th>Tests</th><th>Records</th>
    <th>Picked for</th></tr>{moves}</table></div>
</section>"""


def render_program_html(w: Walkthrough) -> str:
    steps = "".join(f'<li><details open><summary>{escape(s.title)} <span class="muted small">{escape(s.summary)}'
                    f"</span></summary>{_tree(s.lines)}</details></li>" for s in w.steps)
    nav = "".join(f'<a href="#{p.id}">{p.id} {escape(p.name)}</a>' for p in w.hypotheses)
    decisions = "".join(f"<li>{escape(d)}</li>" for d in w.openDecisions)
    source = f"<span>Source: {escape(w.source)}</span>" if w.source else ""
    read = "".join(f"<div><b>{escape(t)}</b>: {escape(x)}</div>" for t, x in _HOW_TO_READ)
    phases = {pl.phase: pl.phaseName for p in w.hypotheses for pl in p.program}
    phases.update({x.phase: phases.get(x.phase, "") for x in w.lines})
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Demand validation: {escape(w.product)}</title><style>{_CSS}</style></head>
<body><main>
  <div class="eyebrow">Hipstraw · demand validation walkthrough</div>
  <h1>{escape(w.product)}: {escape(w.market)}</h1>
  <p>{escape(w.statement)}</p>
  <div class="meta"><span>{escape(w.geography)}</span><span>As of {w.asOf.isoformat()}</span>
    <span>Rubric {escape(w.rubricVersion)} ({escape(w.qualification)})</span>
    <span>Repertoire {escape(w.repertoireVersion or '')}</span>{source}</div>
  <div class="read">{read}</div>
  <p class="note small">{escape(w.scope)} Every choice below is a rule in the rubric or repertoire, so the same thesis
  gives the same program.</p>
  <nav><a href="#log">Walkthrough log</a>{nav}<a href="#repertoire">Repertoire</a>
    <a href="#decisions">Decisions needed</a></nav>
  <section class="card" id="log"><h2>Walkthrough log</h2>
    <p class="muted small">What the agent did with the thesis, step by step: what it looked at, what it picked and
    why. Open a line to see the detail under it.</p>
    <ol class="log">{steps}</ol></section>
  {"".join(_hypothesis(p, phases) for p in w.hypotheses)}
  {_repertoire(w)}
  <section class="card" id="decisions"><h2>Decisions needed</h2><ul>{decisions}</ul></section>
</main></body></html>
"""
