"""EPA federal enforcement cases (ICIS FE&C bulk download).

Download case_downloads.zip from https://echo.epa.gov/tools/data-downloads and unzip it into
one folder. A case is spread over several CSVs joined by case number; we read four of them.

Only concluded cases count (a settlement or final order): a pending case isn't a finding.
Superfund (CERCLA) cases are skipped: liability there doesn't depend on wrongdoing, and one
case can name hundreds of companies that once sent waste to a site. These are federal cases
only; most routine enforcement is done by states and isn't in this dataset.

Column names below follow the real files. If EPA renames one, change it here.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from swap.names import Match
from swap.sources.dol import Matcher
from swap.util import parse_date

FILES = {
    "defendants": "CASE_DEFENDANTS.csv",
    "cases": "CASE_ENFORCEMENTS.csv",
    "penalties": "CASE_PENALTIES.csv",
    "conclusions": "CASE_ENFORCEMENT_CONCLUSIONS.csv",
}
COLUMNS = {
    "defendants": {"case": "case_number", "name": "defendant_name"},
    "cases": {"case": "case_number", "name": "case_name", "summary": "enf_summary_text"},
    # The case file has its own penalty column, but it's blank on recent cases.
    "penalties": {"case": "case_number", "federal": "fed_penalty"},
    "conclusions": {
        "case": "case_number",
        "law": "primary_law",
        "entered": "settlement_entered_date",
        "lodged": "settlement_lodged_date",
    },
}
EXCLUDED_LAWS = {"CERCLA"}
SOURCE_URL = "https://echo.epa.gov/tools/data-downloads"
_SPACES = re.compile(r"\s+")


def case_url(case_number: str) -> str:
    return f"https://echo.epa.gov/enforcement-case-report?id={case_number}"


def _rows(path: Path) -> Iterator[dict[str, str]]:
    # Values are space-padded ("CHING MEI U.S.A. LTD      "), so strip everything.
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip().lower() for h in next(reader, [])]
        for row in reader:
            yield {k: v.strip() for k, v in zip(header, row, strict=False)}


def _num(value: str | None) -> float:
    try:
        return float((value or "").replace(",", "").replace("$", "") or 0)
    except ValueError:
        return 0.0


def read_epa(folder: Path, match: Matcher) -> Iterator[tuple[dict[str, Any], Match]]:
    c = COLUMNS
    # 1. Defendants: keep only cases that name a company we track.
    hits: dict[str, tuple[str, Match]] = {}
    for row in _rows(folder / FILES["defendants"]):
        case, name = row.get(c["defendants"]["case"], ""), row.get(c["defendants"]["name"], "")
        if case and name and case not in hits and (m := match(name)):
            hits[case] = (name, m)
    if not hits:
        return
    # 2. Conclusions: the laws involved and when the case was settled.
    laws: dict[str, set[str]] = defaultdict(set)
    settled: dict[str, date] = {}
    for row in _rows(folder / FILES["conclusions"]):
        case = row.get(c["conclusions"]["case"], "")
        if case not in hits:
            continue
        if law := row.get(c["conclusions"]["law"]):
            laws[case].add(law)
        day = parse_date(row.get(c["conclusions"]["entered"])) or parse_date(
            row.get(c["conclusions"]["lodged"])
        )
        if day and (case not in settled or day > settled[case]):
            settled[case] = day
    # 3. Penalties.
    penalties: dict[str, float] = defaultdict(float)
    for row in _rows(folder / FILES["penalties"]):
        case = row.get(c["penalties"]["case"], "")
        if case in hits:
            penalties[case] += _num(row.get(c["penalties"]["federal"]))
    # 4. Cases.
    for row in _rows(folder / FILES["cases"]):
        case = row.get(c["cases"]["case"], "")
        if case not in hits or case not in settled:
            continue  # not tracked, or not concluded yet
        if laws[case] and laws[case] <= EXCLUDED_LAWS:
            continue
        raw, m = hits[case]
        yield (
            {
                "id": f"EPA:{case}",
                "raw_name": raw,
                "case_name": row.get(c["cases"]["name"]),
                "law": ",".join(sorted(laws[case])) or None,
                "date": settled[case].isoformat(),
                "penalty": penalties.get(case, 0.0),
                "summary": _SPACES.sub(" ", row.get(c["cases"]["summary"], "")) or None,
                "url": case_url(case),
            },
            m,
        )
