"""T052: build the complete, state-keyed place lists in config/metros.yaml from Census files.

Since 2026-10-07 a cited headquarters city that is not on its state's list counts as outside the metros
(research R5), so every list must name every place in its CSA:
- every incorporated place and census-designated place in the CSA's counties;
- every county subdivision (town, township, borough), because companies in New Jersey, Connecticut,
  New York, and Pennsylvania often give a town or township ("Edison, NJ", "Greenwich, CT").

Sources (all public Census files):
  list1_2023.xlsx                    CBSAs and CSAs with their counties, July 2023 (OMB Bulletin 23-01)
  national_place_by_county2020.txt   places by county, 2020
  national_cousub2020.txt            county subdivisions, 2020
  ct_cou_to_cousub_crosswalk.txt     Connecticut towns: 2020 counties -> 2022 planning regions

Connecticut: the 2023 delineation uses planning regions, the 2020 files use the old counties. Towns
are mapped to planning regions with the crosswalk. A place (such as a CDP) is included when every
town of its old county is in the CSA; places that are towns are covered by the towns.

Usage (run with -I: the downloaded files are data, never code):
  python -I scripts/build_metro_places.py --download DIR         # fetch the four files into DIR
  python -I scripts/build_metro_places.py DIR [--out PATH]       # write config/metros.yaml
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "list1_2023.xlsx": "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx",
    "national_place_by_county2020.txt": "https://www2.census.gov/geo/docs/reference/codes2020/national_place_by_county2020.txt",
    "national_cousub2020.txt": "https://www2.census.gov/geo/docs/reference/codes2020/national_cousub2020.txt",
    "ct_cou_to_cousub_crosswalk.txt": "https://www2.census.gov/geo/docs/reference/ct_change/ct_cou_to_cousub_crosswalk.txt",
}
CONNECTICUT = "09"
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# One trailing legal/statistical area description, as Census writes it ("Jersey City city").
_LSAD = re.compile(
    r"\s+(?:(?:unified|consolidated|metro|metropolitan) government \(balance\)|city and borough|"
    r"charter township|city|town|village|borough|CDP|township|municipality|\(balance\))$"
)


def clean(name: str) -> list[str]:
    """`"Jersey City city"` -> `["Jersey City"]`; `"Athens-Clarke County unified government (balance)"`
    -> `["Athens-Clarke County", "Athens"]` (a consolidated city is also known by its first part)."""
    base = _LSAD.sub("", name.strip())
    names = [base]
    if "-" in base and base.endswith(" County"):
        names.append(base.split("-", 1)[0])
    return names


def download(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for file_name, url in SOURCES.items():
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 (fixed census.gov URLs)
            (directory / file_name).write_bytes(response.read())


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    """The delineation sheet as dicts keyed by its header row (the row whose first cell is "CBSA Code")."""
    with zipfile.ZipFile(path) as book:
        shared = [
            "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
            for si in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("m:si", _NS)
        ]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
    table: list[dict[str, str]] = []
    data = sheet.find("m:sheetData", _NS)
    for row in data if data is not None else []:
        cells: dict[str, str] = {}
        for cell in row.findall("m:c", _NS):
            column = re.sub(r"\d", "", cell.get("r", ""))
            value = cell.find("m:v", _NS)
            inline = cell.find("m:is/m:t", _NS)
            if value is not None and value.text is not None:
                cells[column] = shared[int(value.text)] if cell.get("t") == "s" else value.text
            elif inline is not None and inline.text is not None:
                cells[column] = inline.text
        table.append(cells)
    header_index = next(i for i, cells in enumerate(table) if cells.get("A") == "CBSA Code")
    header = table[header_index]
    return [{header[c]: v for c, v in cells.items() if c in header} for cells in table[header_index + 1 :]]


def _pipe_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="|")
    header = [h.split("\n")[0].split(" ")[0].strip() for h in next(reader)]
    return [dict(zip(header, row, strict=False)) for row in reader if row]


def build(directory: Path, existing: dict) -> dict:
    metros = existing["metros"]
    wanted = {m["csaCode"]: m for m in metros}
    csa_counties: dict[str, set[tuple[str, str]]] = defaultdict(set)  # csa -> {(statefp, countyfp)}
    county_names: dict[tuple[str, str], str] = {}
    titles: dict[str, str] = {}
    for row in _xlsx_rows(directory / "list1_2023.xlsx"):
        csa = (row.get("CSA Code") or "").strip()
        if csa in wanted:
            key = (row["FIPS State Code"].zfill(2), row["FIPS County Code"].zfill(3))
            csa_counties[csa].add(key)
            county_names[key] = row["County/County Equivalent"]
            titles[csa] = row["CSA Title"]

    places = _pipe_rows(directory / "national_place_by_county2020.txt")
    cousubs = _pipe_rows(directory / "national_cousub2020.txt")
    postal = {r["STATEFP"]: r["STATE"] for r in places}
    crosswalk = _pipe_rows(directory / "ct_cou_to_cousub_crosswalk.txt")

    for csa, metro in wanted.items():
        counties = csa_counties.get(csa)
        if not counties:
            raise SystemExit(f"CSA {csa} ({metro['id']}) not found in list1_2023.xlsx")
        states = sorted({postal[s] for s, _ in counties}, key=metro["states"].index)
        if set(states) != set(metro["states"]):
            raise SystemExit(f"CSA {csa}: Census states {states} differ from config states {metro['states']}")

        by_state: dict[str, set[str]] = defaultdict(set)
        for row in places:
            if (row["STATEFP"], row["COUNTYFP"]) in counties and row["STATEFP"] != CONNECTICUT:
                by_state[row["STATE"]].update(clean(row["PLACENAME"]))
        for row in cousubs:
            if (
                (row["STATEFP"], row["COUNTYFP"]) in counties
                and row["STATEFP"] != CONNECTICUT
                and row["COUSUBFP"] != "00000"
                and "not defined" not in row["COUSUBNAME"]
            ):
                by_state[row["STATE"]].update(clean(row["COUSUBNAME"]))

        regions = {county for state, county in counties if state == CONNECTICUT}
        if regions:
            in_csa: dict[str, bool] = {}
            for row in crosswalk:
                if row["STATEFP"] != CONNECTICUT:
                    continue
                inside = row["NEW_COUNTYFP"] in regions
                in_csa[row["OLD_COUNTYFP"]] = in_csa.get(row["OLD_COUNTYFP"], True) and inside
                if inside:
                    by_state["CT"].update(clean(row["COUSUB_NAMELSAD"]))
            whole = {old for old, all_inside in in_csa.items() if all_inside}
            for row in places:
                if row["STATEFP"] == CONNECTICUT and row["COUNTYFP"] in whole:
                    by_state["CT"].update(clean(row["PLACENAME"]))

        metro["states"] = states
        metro["counties"] = {
            postal[s]: sorted(county_names[(s2, c)] for s2, c in counties if s2 == s)
            for s in sorted({s for s, _ in counties}, key=lambda fp: states.index(postal[fp]))
        }
        metro["places"] = {state: sorted(by_state[state]) for state in states}
        print(
            f"{metro['id']}: CSA {csa} {titles[csa]!r}: "
            + ", ".join(f"{s} {len(metro['counties'][s])} counties {len(metro['places'][s])} places" for s in states)
        )
    return existing


HEADER = """# Generated by scripts/build_metro_places.py on {today} (T052). Do not edit by hand; run it again.
#
# Each metro is its US Census combined statistical area (CSA), with its counties and EVERY place in
# them, keyed by state: incorporated places, census-designated places, and county subdivisions (towns,
# townships, boroughs), with Census suffixes such as "city" or "township" removed. Since 2026-10-07 a
# cited headquarters city that is not on its state's list counts as outside the metros (research R5).
#
# Sources:
#   CSA counties: {list1} (July 2023, OMB Bulletin 23-01)
#   Places by county: {places} (2020)
#   County subdivisions: {cousubs} (2020)
#   Connecticut towns to planning regions: {crosswalk} (2022)

"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--download", action="store_true", help="fetch the Census files into DIRECTORY")
    parser.add_argument("--out", type=Path, default=ROOT / "config" / "metros.yaml")
    args = parser.parse_args(argv)
    if args.download:
        download(args.directory)
        return 0
    existing = yaml.safe_load(args.out.read_text(encoding="utf-8"))
    data = build(args.directory, existing)
    header = HEADER.format(
        today=date.today().isoformat(),
        list1=SOURCES["list1_2023.xlsx"],
        places=SOURCES["national_place_by_county2020.txt"],
        cousubs=SOURCES["national_cousub2020.txt"],
        crosswalk=SOURCES["ct_cou_to_cousub_crosswalk.txt"],
    )
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)
    args.out.write_text(header + body, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
