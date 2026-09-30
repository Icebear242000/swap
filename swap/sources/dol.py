"""Department of Labor enforcement data (bulk CSV downloads).

- Wage and Hour Division (WHD) compliance actions: back wages owed to workers.
- OSHA inspections and violations: workplace safety citations.

Download from https://enforcedata.dol.gov/views/data_summary.php. The files are
large (OSHA runs to gigabytes), so we stream them and keep only rows whose
employer name matches a company or brand we already track.

Column names below follow DOL's published data dictionaries. If DOL renames a
column, change it here in one place.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from swap.names import Match, best_match

WHD_COLUMNS = {
    "id": "case_id",
    "trade_name": "trade_nm",
    "legal_name": "legal_name",
    "state": "st_cd",
    "violations": "case_violtn_cnt",
    "back_wages": "bw_atp_amt",
    "penalty": "cmp_assd",
    "end_date": "findings_end_date",
}
OSHA_INSPECTION_COLUMNS = {
    "id": "activity_nr",
    "name": "estab_name",
    "state": "site_state",
    "date": "open_date",
}
OSHA_VIOLATION_COLUMNS = {
    "id": "activity_nr",
    "type": "viol_type",
    "penalty": "current_penalty",
    "deleted": "delete_flag",
}
# OSHA violation type codes, most severe first.
OSHA_SEVERITY = {"W": "willful", "R": "repeat", "S": "serious", "O": "other"}
SEVERITY_RANK = {"willful": 3, "repeat": 2, "serious": 1, "other": 0}

WHD_SOURCE_URL = "https://enforcedata.dol.gov/views/data_summary.php"


def osha_case_url(activity_nr: str) -> str:
    return f"https://www.osha.gov/ords/imis/establishment.inspection_detail?id={activity_nr}"


def _num(value: str | None) -> float:
    try:
        return float((value or "").replace(",", "").replace("$", "") or 0)
    except ValueError:
        return 0.0


class Matcher:
    """Caches name -> org matches; the same employer name repeats across many rows."""

    def __init__(self, org_keys: Iterable[str]):
        self.org_keys = list(org_keys)
        self._cache: dict[str, Match | None] = {}

    def __call__(self, raw: str) -> Match | None:
        if raw not in self._cache:
            self._cache[raw] = best_match(raw, self.org_keys)
        return self._cache[raw]


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        yield from csv.DictReader(f)


def read_whd(path: Path, match: Matcher) -> Iterator[tuple[dict[str, Any], Match]]:
    c = WHD_COLUMNS
    for row in _rows(path):
        names = [row.get(c["legal_name"]) or "", row.get(c["trade_name"]) or ""]
        hit = next((m for n in names if n and (m := match(n))), None)
        if not hit:
            continue
        raw = next(n for n in names if n)
        yield (
            {
                "id": f"WHD:{row.get(c['id'])}",
                "source": "WHD",
                "raw_name": raw,
                "state": row.get(c["state"]),
                "date": row.get(c["end_date"]),
                "violations": int(_num(row.get(c["violations"]))),
                "back_wages": _num(row.get(c["back_wages"])),
                "penalty": _num(row.get(c["penalty"])),
                "severity": None,
                "url": WHD_SOURCE_URL,
            },
            hit,
        )


def read_osha(
    inspections: Path, violations: Path, match: Matcher
) -> Iterator[tuple[dict[str, Any], Match]]:
    ci, cv = OSHA_INSPECTION_COLUMNS, OSHA_VIOLATION_COLUMNS
    kept: dict[str, tuple[dict[str, Any], Match]] = {}
    for row in _rows(inspections):
        name = row.get(ci["name"]) or ""
        hit = match(name) if name else None
        if not hit:
            continue
        nr = row.get(ci["id"]) or ""
        kept[nr] = (
            {
                "id": f"OSHA:{nr}",
                "source": "OSHA",
                "raw_name": name,
                "state": row.get(ci["state"]),
                "date": row.get(ci["date"]),
                "violations": 0,
                "back_wages": 0.0,
                "penalty": 0.0,
                "severity": None,
                "url": osha_case_url(nr),
            },
            hit,
        )
    if not kept:
        return
    counts: dict[str, int] = defaultdict(int)
    for row in _rows(violations):
        nr = row.get(cv["id"]) or ""
        if nr not in kept or (row.get(cv["deleted"]) or "").strip().upper() == "X":
            continue
        case = kept[nr][0]
        counts[nr] += 1
        case["penalty"] += _num(row.get(cv["penalty"]))
        sev = OSHA_SEVERITY.get((row.get(cv["type"]) or "").strip().upper())
        if sev and SEVERITY_RANK[sev] > SEVERITY_RANK.get(case["severity"] or "", -1):
            case["severity"] = sev
    for nr, (case, hit) in kept.items():
        case["violations"] = counts.get(nr, 0)
        yield case, hit
