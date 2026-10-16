"""One-off extractor: The Hipstraw Market Mastery Playbook (PDF) -> config/playbook/*.yaml.

The YAML it writes is reviewed and committed; from then on the YAML, not the PDF, is the source.
Cards (strategies, plays, lines, gambit cards) are parsed from the plain text; tables (moves,
actions, gambit terms, stances, hard rules, market types, gates, situation finder, state calls,
and the stance matrices) from pypdf's layout text, which keeps column positions.

Usage: python scripts/extract_playbook.py "docs/The Hipstraw Market Mastery Playbook - Case 01.pdf" config/playbook
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from pypdf import PdfReader

VERSION = "playbook.v0.1"
STANCES = ["Listen", "Scout", "Probe", "Co-create", "Activate", "Build", "Expand", "Protect"]
MARK = {"●": "default", "○": "allowed", "×": "never"}
DISCIPLINES = ("Explore", "Develop", "Build", "Scale", "Any stage", "Govern and exit")
MOVE_TABLE_HEADINGS = (
    r"^(Ask and verify|Access and|partners|Offer and|conversion|Supply and|delivery|Economics and|scale"
    r"|Close out and|stop|13 Gambits|A Gambit|Gambit needs|runs on weak|ends with a|over the whole)"
)
FINDER_HEADINGS = (
    r"^(Need and buyers|Offer and conversion|Channels and partners|Supply and delivery|Economics and scale"
    r"|Conduct and compliance)$"
)
GAMBIT_TABLE_IN_CARD = r"\sGambit Give Get Max loss.*?(?=\s(?:Must be true|Stance|Used with|Net-value check):)"


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).replace(" ", " ")


def flat(s: str) -> str:
    return " ".join(s.split())


def ids(s: str, prefix: str) -> list[str]:
    return list(dict.fromkeys(re.findall(rf"\b{prefix}\d\d\b", s or "")))


def stance_names(s: str) -> list[str]:
    return [x for x in STANCES if re.search(rf"\b{re.escape(x)}\b", s or "")]


def join_fragments(parts: list[str]) -> str:
    out = ""
    for p in (x.strip() for x in parts):
        if not p:
            continue
        out = out + p if out.endswith("-") and p[:1].islower() else (f"{out} {p}" if out else p)
    return out.strip()


def load(pdf: Path) -> tuple[str, list[str]]:
    reader = PdfReader(str(pdf))
    plain = norm("\n".join(p.extract_text() or "" for p in reader.pages))
    plain = re.sub(r"\nThe Hipstraw Market Mastery Playbook\nPage \d+ of \d+", "\n", plain)
    layout = [norm(p.extract_text(extraction_mode="layout") or "") for p in reader.pages]
    return plain, layout


# ---------------------------------------------------------------- layout tables


def layout_rows(
    pages: list[str], header: list[str], row_start: str, stop: str, first_page: int = 0, skip: str = r"$^",
    key_col: int = 0,
) -> list[list[str]]:
    """Rows of a layout table spanning pages, until a line containing `stop`.

    A row starts where column `key_col` matches `row_start`; following lines continue it. Lines matching
    `skip` (sub-headings inside the table) are ignored.
    """
    rows: list[list[list[str]]] = []
    cols: list[int] | None = None
    for page in pages[first_page:]:
        for line in page.splitlines():
            if line.strip().startswith(header[0]) and all(h in line for h in header):
                pos, found = 0, []
                for name in header:
                    i = line.find(name, pos)
                    found.append(i)
                    pos = i + len(name)
                if -1 not in found:
                    cols = found
                continue
            if cols is None:
                continue
            if stop in line:
                return [[join_fragments(c) for c in r] for r in rows]
            stripped = line.strip()
            if not stripped or re.match(r"(Page \d+ of|The Hipstraw Market Mastery Playbook)", stripped):
                continue
            if re.match(skip, stripped):
                continue
            cells = [line[cols[i]:(cols[i + 1] if i + 1 < len(cols) else None)] for i in range(len(cols))]
            if re.match(row_start, cells[key_col].strip()):
                rows.append([[c] for c in cells])
            elif rows:
                for i, c in enumerate(cells):
                    rows[-1][i].append(c)
    raise ValueError(f"table {header[:2]} never reached its stop marker {stop!r}")


def matrix(pages: list[str], header0: str, row_labels: list[str], first_page: int) -> dict[str, dict[str, str]]:
    """● ○ × cells read by column position under the stance headers. Blank cells mean 'not typical'."""
    out: dict[str, dict[str, str]] = {}
    cols: list[int] | None = None
    want = list(row_labels)
    for page in pages[first_page:]:
        for line in page.splitlines():
            if line.strip().startswith(header0) and "Listen" in line and "Protect" in line:
                cols = [line.index(s.split("-")[0]) for s in STANCES]
                continue
            if cols is None or not want:
                continue
            if line.strip().startswith(want[0]):
                cells: dict[str, str] = {}
                for m in re.finditer(r"[●○×]", line):
                    nearest = min(range(len(cols)), key=lambda i: abs(cols[i] - m.start()))
                    cells[STANCES[nearest]] = MARK[m.group()]
                out[want.pop(0)] = cells
        if not want:
            return out
    raise ValueError(f"matrix rows not found: {want[:3]}")


# ---------------------------------------------------------------- cards


def cards(text: str, start: str, end: str, prefix: str) -> list[tuple[str, str, str, str]]:
    """(id, name, discipline group, flattened body)."""
    begin = text.index(start)
    section = text[begin: text.index(end, begin)]
    pattern = re.compile(rf"^({prefix}\d\d) · ([^\n]+)\n(.*?)(?=^{prefix}\d\d · |\Z)", re.S | re.M)
    out, group = [], ""
    for m in pattern.finditer(section):
        before = section[: m.start()].rstrip().splitlines()
        if before and before[-1].strip() in DISCIPLINES:
            group = before[-1].strip()
        body = flat(m.group(3))
        body = re.sub(rf"\s({'|'.join(DISCIPLINES)})$", "", body)
        out.append((m.group(1), m.group(2).strip(), group, body))
    return out


FIELD_NAMES = [
    "Use when", "Don't use when", "Must be true", "Stance", "Plays", "Strategy", "Lines", "Gambits",
    "First step", "Levers", "Who decides", "Done when", "Example", "Pioneer's tip", "Tip", "Steps",
    "If... then...", "Window", "Stop if", "Escalate if", "Used by", "Used with", "Net-value check",
]


def fields(body: str) -> dict[str, str]:
    pattern = "|".join(re.escape(f) for f in sorted(FIELD_NAMES, key=len, reverse=True))
    parts = re.split(rf"(?:(?<=\s)|^)({pattern}):\s", body)
    out = {"_lead": parts[0].strip()}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1].strip().rstrip(".").strip()
    return out


def stance_field(s: str) -> dict[str, Any]:
    s = (s or "").rstrip(".")
    default = re.match(r"([\w-]+)(?: / Pause)? \(default\)", s)
    allowed_part, _, never_part = s.partition("never")
    d = default.group(1) if default else None
    allowed = [x for x in stance_names(allowed_part) if x != d]
    return {"default": d, "allowed": allowed, "never": stance_names(never_part)}


def build_strategies(text: str) -> list[dict[str, Any]]:
    out = []
    for sid, name, _, body in cards(text, "9 Strategies", "10 Plays", "S"):
        f = fields(body)
        plays = f.get("Plays", "")
        # "runs inside P02, ..." (S02) means no primary plays; the playbook's §7.3 lists them as "also".
        primary, also = ("", plays) if plays.startswith("runs inside") else plays.partition("also")[::2]
        out.append({
            "id": sid, "name": name, "purpose": f["_lead"],
            "useWhen": f.get("Use when"), "dontUseWhen": f.get("Don't use when"), "mustBeTrue": f.get("Must be true"),
            "stance": stance_field(f.get("Stance", "")),
            "plays": {"primary": ids(primary, "P"), "also": ids(also, "P")},
            "lines": ids(f.get("Lines", ""), "L"),
            "levers": [x.strip() for x in f.get("Levers", "").split(",") if x.strip()],
            "whoDecides": f.get("Who decides"), "doneWhen": f.get("Done when"),
            "example": f.get("Example"), "tip": f.get("Pioneer's tip"),
        })
    return out


def build_plays(text: str) -> list[dict[str, Any]]:
    out = []
    for pid, name, group, body in cards(text, "10 Plays", "11 Lines", "P"):
        f = fields(body)
        preferred, _, alt = f.get("Lines", "").partition("alt.")
        strategy = f.get("Strategy", "")
        first = f.get("First step", "")
        first_id = re.search(r"\b([MA]\d\d)\b", first)
        out.append({
            "id": pid, "name": name, "discipline": group, "purpose": f["_lead"],
            "useWhen": f.get("Use when"), "dontUseWhen": f.get("Don't use when"), "mustBeTrue": f.get("Must be true"),
            "stance": stance_field(f.get("Stance", "")),
            "strategy": {"primary": ids(strategy.split("(")[0], "S")[0], "also": ids(strategy.partition("(")[2], "S")},
            "lines": {"preferredText": preferred.strip().rstrip("·").strip(), "preferred": ids(preferred, "L"),
                      "alternatives": ids(alt, "L")},
            "gambits": ids(f.get("Gambits", ""), "G"),
            "firstStep": {"id": first_id.group(1) if first_id else None, "text": first},
            "whoDecides": f.get("Who decides"), "doneWhen": f.get("Done when"),
            "example": f.get("Example"), "tip": f.get("Tip"),
        })
    return out


def build_lines(text: str) -> list[dict[str, Any]]:
    out = []
    for lid, name, group, body in cards(text, "11 Lines", "12 Moves", "L"):
        f = fields(body)
        purpose, _, starts = f["_lead"].partition("Starts when")
        prim, _, alt = f.get("Used by", "").partition("alt.")
        texts = {
            m.group(2): m.group(1).strip()
            for m in re.finditer(r"(?:^|→)\s*([^→(]+?)\s*\(([MAL]\d\d)", f.get("Steps", ""))
        }
        step_ids = re.findall(r"\b([MAL]\d\d)\b", f.get("Steps", ""))
        out.append({
            "id": lid, "name": name, "discipline": group, "purpose": purpose.strip(),
            "startsWhen": starts.strip().rstrip("."),
            "steps": [{"id": s, "text": texts.get(s)} for s in step_ids],
            "branches": f.get("If... then..."),
            "branchIds": re.findall(r"\b([MALGP]\d\d)\b", f.get("If... then...", "")),
            "window": f.get("Window"), "stopIf": f.get("Stop if"), "escalateIf": f.get("Escalate if"),
            "doneWhen": f.get("Done when"), "stance": stance_field(f.get("Stance", "")),
            "usedBy": {"primary": ids(prim, "P"), "alternative": ids(alt, "P")},
            "whoDecides": f.get("Who decides"),
        })
    return out


def build_moves(pages: list[str]) -> list[dict[str, Any]]:
    rows = layout_rows(pages, ["Move", "Use when", "Never when", "Stance", "Tasks", "Done when"], r"^M\d\d\b",
                       stop="Gambit", first_page=55, skip=MOVE_TABLE_HEADINGS)
    out = {}
    for move, use, never_when, stance, tasks, done in rows:
        m = re.match(r"(M\d\d)\s*(.*)", move)
        default = re.search(r"●\s*([\w-]+)", stance)
        out[m.group(1)] = {
            "id": m.group(1), "name": m.group(2).strip(), "useWhen": use, "neverWhen": never_when,
            "stance": {"default": default.group(1) if default else None,
                       "never": stance_names(stance.split("×", 1)[1]) if "×" in stance else [],
                       "everyStance": "every stance" in stance},
            "tasks": ids(tasks, "A"), "doneWhen": done,
        }
    return sorted(out.values(), key=lambda m: m["id"])


def build_gambits(text: str, pages: list[str]) -> list[dict[str, Any]]:
    terms = {
        r[0].split()[0]: r
        for r in layout_rows(pages, ["Gambit", "Give", "Get", "Max loss", "Fallback", "Approver"], r"^G\d\d\b",
                             stop="G01 · Concierge", first_page=60, skip=r"^\(illustrative\)")
    }
    out = []
    for gid, name, _, body in cards(text, "13 Gambits", "14 Actions", "G"):
        body = re.sub(GAMBIT_TABLE_IN_CARD, "", body)
        f = fields(body)
        t = terms[gid]
        out.append({
            "id": gid, "name": name, "give": t[1], "get": t[2], "maxLossIllustrative": t[3],
            "fallback": t[4], "approver": t[5],
            "useWhen": f.get("Use when"), "dontUseWhen": f.get("Don't use when"), "mustBeTrue": f.get("Must be true"),
            "stance": stance_field(f.get("Stance", "")),
            "usedWith": ids(f.get("Used with", ""), "P"), "netValueCheck": f.get("Net-value check"),
        })
    return out


def build_actions(pages: list[str]) -> list[dict[str, Any]]:
    tiers: dict[str, tuple[int, str]] = {}
    current: tuple[int, str] | None = None
    for page in pages[64:72]:
        for line in page.splitlines():
            t = re.match(r"\s*Tier (\d) · (.+?)\s*$", line)
            if t:
                current = (int(t.group(1)), t.group(2))
                continue
            a = re.match(r"\s*(A\d\d)\s", line)
            if a and current and a.group(1) not in tiers:
                tiers[a.group(1)] = current
    rows = layout_rows(pages, ["ID", "Action", "Shows in activity as", "Who can", "Undo"], r"^A\d\d\b",
                       stop="Part E", first_page=64, skip=r"^(Tier \d|run it\b)")
    out = {}
    for aid, action, shows, who, undo in rows:
        tier = tiers.get(aid, (None, None))
        out.setdefault(aid, {"id": aid, "name": action, "tier": tier[0], "tierName": tier[1],
                             "showsInActivityAs": shows, "whoCanRun": re.sub(r"^run it\s*", "", who), "undo": undo})
    return sorted(out.values(), key=lambda a: a["id"])


def build_tables(pages: list[str]) -> dict[str, Any]:
    stances = []
    for r in layout_rows(pages, ["Stance", "Behaviour", "Typical", "Never", "Sounds like", "Lasts until"],
                         r"^(Listen|Scout|Probe|Co-|Activate|Build|Expand|Protect)", stop="Part B", first_page=10,
                         skip=r"^Moves$"):
        name = next(s for s in STANCES if r[0].replace(" ", "").startswith(s.split("-")[0]))
        stances.append({"name": name, "behaviour": r[1], "typicalMoves": ids(r[2], "M"), "never": r[3],
                        "soundsLike": r[4], "lastsUntil": r[5]})
    hard_rules = [
        {"id": int(r[0]), "rule": r[1], "why": r[2], "example": r[3], "whenHit": r[4]}
        for r in layout_rows(pages, ["#", "Rule", "Why", "Example", "When hit, the"], r"^\d\d$", first_page=12,
                             stop="5 Who decides what",
                             skip=r"^(agent(…|\.\.\.)$|Operating mode|LIMITED|worlds|use authorization|right maturity)")
    ]
    gates = [
        {"gate": r[0], "discipline": r[1], "requiredEvidence": r[2], "ifNotMet": r[3]}
        for r in layout_rows(pages, ["Gate", "Discipline", "Required evidence", "If not met"], r"^Gate \d",
                             first_page=9, stop="2.4")
    ]
    market_types = [
        {"id": r[0].split()[0], "name": r[0].split(" ", 1)[1], "reality": r[1], "priorityPlays": ids(r[2], "P"),
         "typicalTrap": r[3]}
        for r in layout_rows(pages, ["Market type", "Market reality", "Priority", "Typical trap"], r"^AR\d\d\b",
                             first_page=26, stop="8 Situation finder", skip=r"^Plays$")
    ]
    situations = [
        {"whatYouSee": r[0], "play": ids(r[1], "P")[0], "firstStep": r[2],
         "firstStepId": (re.findall(r"\b([MA]\d\d)\b", r[2]) or [None])[0], "axis": r[3]}
        for r in layout_rows(pages, ["What you see", "Play", "First step", "Axis"], r"^P\d\d\b",
                             first_page=27, key_col=1, stop="Part D", skip=FINDER_HEADINGS)
        if ids(r[1], "P")
    ]
    calls = [
        {"axis": r[0].split()[0], "state": r[1], "showsWhen": r[2], "callsFor": ids(r[3], "S"), "callsForText": r[3]}
        for r in layout_rows(pages, ["Axis", "State", "Shows when", "Usually calls for"], r"^MP\d", first_page=6,
                             stop="2.3")
    ]
    return {"stances": stances, "hardRules": hard_rules, "gates": gates, "marketTypes": market_types,
            "situations": situations, "stateCalls": calls}


def main() -> None:
    pdf, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    text, pages = load(pdf)
    tables = build_tables(pages)
    states = [(c["axis"], c["state"]) for c in tables["stateCalls"]]
    position_stance = matrix(pages, "Axis · state", [s for _, s in states], first_page=19)
    by_axis: dict[str, dict[str, Any]] = {}
    for axis, state in states:
        by_axis.setdefault(axis, {})[state] = position_stance[state]
    strategies = build_strategies(text)
    data = {
        "strategies": strategies,
        "plays": build_plays(text),
        "lines": build_lines(text),
        "moves": build_moves(pages),
        "gambits": build_gambits(text, pages),
        "actions": build_actions(pages),
        **tables,
        "matrices": {
            "positionStance": by_axis,
            "strategyStance": matrix(pages, "Strategy", [s["id"] for s in strategies], first_page=21),
            "gambitStance": matrix(pages, "Gambit", [f"G{i:02d}" for i in range(1, 13)], first_page=25),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    header = (f"# Extracted from {pdf.name} by scripts/extract_playbook.py ({VERSION}).\n"
              "# Reviewed; edit here, not in the PDF.\n")
    for key, value in data.items():
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
        (out_dir / f"{name}.yaml").write_text(
            header + yaml.safe_dump({"version": VERSION, key: value}, sort_keys=False, allow_unicode=True, width=110),
            encoding="utf-8",
        )
        print(f"{name}.yaml: {len(value)}")


if __name__ == "__main__":
    main()
