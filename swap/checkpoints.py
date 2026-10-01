"""The checkpoints, plus the recall warning.

Each checkpoint returns pass / fail / unknown with the evidence behind it.
Missing data is always "unknown", never an automatic pass.

Checkpoints judge what a product and its company do, not who owns them. Ownership
is still used to find a brand's parent company, whose records apply to the brand.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any

from swap import ingredients as ing
from swap.config import Settings
from swap.db import loaded_datasets
from swap.names import normalize
from swap.ownership import Ownership
from swap.records import env_for, labor_for, recalls_for
from swap.util import parse_date, years_ago

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


@dataclass(frozen=True)
class CheckpointDef:
    id: str
    label: str
    question: str
    categories: tuple[str, ...] | None  # None means every category


CHECKPOINTS: tuple[CheckpointDef, ...] = (
    CheckpointDef(
        "fights_cavities", "Fights cavities", "Does it contain fluoride?", ("toothpaste",)
    ),
    CheckpointDef("ingredients", "Ingredients", "Free of PFAS and restricted ingredients?", None),
    CheckpointDef(
        "workers",
        "Treats workers well",
        "No serious labor violations in recent public records?",
        None,
    ),
    CheckpointDef(
        "environment",
        "Environmental record",
        "No significant federal environmental enforcement in the last 5 years?",
        None,
    ),
)
BY_ID = {c.id: c for c in CHECKPOINTS}


def applicable(category: str | None) -> list[CheckpointDef]:
    return [c for c in CHECKPOINTS if c.categories is None or category in c.categories]


@dataclass
class Evidence:
    text: str
    source: str | None = None
    url: str | None = None


@dataclass
class Result:
    id: str
    label: str
    status: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(cid: str, status: str, summary: str, evidence=None) -> Result:
    return Result(cid, BY_ID[cid].label, status, summary, evidence or [])


def check_fights_cavities(f: ing.IngredientFindings) -> Result:
    cid = "fights_cavities"
    if not f.listed:
        return _result(cid, UNKNOWN, "No ingredient list on record for this product.")
    if f.fluoride:
        return _result(
            cid,
            PASS,
            f"Contains {f.fluoride[0]}.",
            [
                Evidence(
                    "Fluoride is the ADA-recognized cavity-fighting ingredient.",
                    "American Dental Association",
                    "https://www.ada.org/",
                )
            ],
        )
    if f.hydroxyapatite:
        return _result(
            cid,
            UNKNOWN,
            "No fluoride. Contains hydroxyapatite, where the evidence is still limited.",
        )
    # Volunteer ingredient lists are often partial or wrong, so an absent fluoride is only
    # a fail when nothing suggests the list is incomplete.
    if f.partial_label:
        return _result(
            cid,
            UNKNOWN,
            "No fluoride listed, but the ingredient list looks incomplete "
            "(only part of the label was captured).",
        )
    if f.claims_cavity_protection:
        return _result(
            cid,
            UNKNOWN,
            "The product claims cavity protection, but no fluoride is in the listed "
            "ingredients. The list may be incomplete or wrong.",
        )
    return _result(cid, FAIL, "No fluoride in the ingredient list.")


def check_ingredients(f: ing.IngredientFindings) -> Result:
    cid = "ingredients"
    if not f.listed:
        return _result(cid, UNKNOWN, "No ingredient list on record for this product.")
    ev = [Evidence(f"Lists {item}, a PFAS compound.", "Swap PFAS name rules") for item in f.pfas]
    fails = [(r, item) for r, item in f.restricted if r.severity == "fail"]
    cautions = [(r, item) for r, item in f.restricted if r.severity == "caution"]
    ev += [Evidence(f"{item}: {r.note}", r.source) for r, item in fails + cautions]
    if f.pfas:
        return _result(cid, FAIL, f"Contains PFAS ({f.pfas[0]}).", ev)
    if fails:
        return _result(cid, FAIL, f"Contains {fails[0][1]}.", ev)
    if cautions:
        return _result(cid, PASS, f"No PFAS. Note: contains {cautions[0][1]}.", ev)
    return _result(cid, PASS, "No PFAS or restricted ingredients found.")


def check_workers(conn: sqlite3.Connection, own: Ownership, s: Settings) -> Result:
    cid = "workers"
    loaded = loaded_datasets(conn)
    demo_org = bool(own.chain) and all(link.source == "demo" for link in own.chain)
    coverage = {"whd", "osha"} & loaded.keys() or (demo_org and "demo_labor" in loaded)
    if not own.known:
        return _result(cid, UNKNOWN, "We can't tell who makes this, so we can't check records.")
    if not any(link.kind == "company" for link in own.chain):
        # Records are matched to companies only, so "no cases" here would be true by
        # construction, not evidence.
        return _result(
            cid,
            UNKNOWN,
            f"We know the brand {own.chain[0].name}, but not the company behind it, "
            "so we can't check its records.",
        )
    if not coverage:
        return _result(
            cid, UNKNOWN, "Labor records (OSHA, Wage and Hour Division) aren't loaded yet."
        )
    keys = [link.key for link in own.chain]
    since = years_ago(s.labor_lookback_years)
    cases = [c for c in labor_for(conn, keys) if (d := parse_date(c["date"])) and d >= since]
    ev = [_labor_evidence(c) for c in cases[:12]]
    serious = [c for c in cases if c["severity"] in ("willful", "repeat")]
    wages = sum(c["back_wages"] or 0 for c in cases if c["source"] == "WHD")
    who = own.chain[-1].name
    years = s.labor_lookback_years
    if serious:
        return _result(
            cid,
            FAIL,
            f"{len(serious)} willful or repeat OSHA violation case(s) at {who} "
            f"in the last {years} years.",
            ev,
        )
    if wages >= s.whd_back_wages_fail_usd:
        return _result(
            cid,
            FAIL,
            f"${wages:,.0f} in back wages owed to workers at {who} in the last {years} years.",
            ev,
        )
    if cases:
        return _result(
            cid,
            PASS,
            f"{len(cases)} minor case(s) in the last {years} years, below our limits.",
            ev,
        )
    sources = ", ".join(sorted(k.upper() for k in ({"whd", "osha"} & loaded.keys()))) or "sample"
    return _result(
        cid, PASS, f"No cases found in the last {years} years ({sources} records). US records only."
    )


def check_environment(conn: sqlite3.Connection, own: Ownership, s: Settings) -> Result:
    cid = "environment"
    if not own.known:
        return _result(cid, UNKNOWN, "We can't tell who makes this, so we can't check records.")
    if not any(link.kind == "company" for link in own.chain):
        return _result(
            cid,
            UNKNOWN,
            f"We know the brand {own.chain[0].name}, but not the company behind it, "
            "so we can't check its records.",
        )
    if "epa" not in loaded_datasets(conn):
        return _result(cid, UNKNOWN, "EPA enforcement records aren't loaded yet.")
    since = years_ago(s.env_lookback_years)
    keys = [link.key for link in own.chain]
    cases = [c for c in env_for(conn, keys) if (d := parse_date(c["date"])) and d >= since]
    ev = [_env_evidence(c) for c in cases[:12]]
    who = own.chain[-1].name
    years = s.env_lookback_years
    big = [c for c in cases if (c["penalty"] or 0) >= s.env_penalty_fail_usd]
    if big:
        total = sum(c["penalty"] for c in big)
        return _result(
            cid,
            FAIL,
            f"${total:,.0f} in federal environmental penalties against {who} "
            f"in the last {years} years.",
            ev,
        )
    if cases:
        return _result(
            cid,
            PASS,
            f"{len(cases)} federal case(s) in the last {years} years, below our limit.",
            ev,
        )
    return _result(
        cid,
        PASS,
        f"No federal environmental cases found in the last {years} years (EPA). "
        "US federal cases only; most routine enforcement is by states.",
    )


def _env_evidence(c: sqlite3.Row) -> Evidence:
    law = f"{c['law']}, " if c["law"] else ""
    penalty = f"${c['penalty']:,.0f} penalty" if c["penalty"] else "no penalty"
    summary = f" {c['summary'][:160].rstrip()}" if c["summary"] else ""
    text = f"EPA case ({c['date']}): {law}{penalty}.{summary} Filed as “{c['raw_name']}”."
    return Evidence(text, "EPA ECHO", c["url"])


def _labor_evidence(c: sqlite3.Row) -> Evidence:
    where = f" in {c['state']}" if c["state"] else ""
    if c["source"] == "OSHA":
        sev = f" (most serious: {c['severity']})" if c["severity"] else ""
        text = (
            f"OSHA inspection{where} ({c['date']}): {c['violations']} violation(s){sev}, "
            f"${c['penalty'] or 0:,.0f} in penalties. Filed as \u201c{c['raw_name']}\u201d."
        )
    else:
        text = (
            f"Wage and Hour case{where} ({c['date']}): {c['violations']} violation(s), "
            f"${c['back_wages'] or 0:,.0f} in back wages. Filed as \u201c{c['raw_name']}\u201d."
        )
    source = "Sample record (fictional)" if c["id"].startswith("demo:") else c["source"]
    return Evidence(text, source, c["url"])


def recall_warning(
    conn: sqlite3.Connection, own: Ownership, product_name: str, brand: str | None, s: Settings
) -> dict[str, Any] | None:
    """Product-level if a recent recall names this brand; company-level otherwise."""
    if not own.known:
        return None
    since = years_ago(s.recall_lookback_years)
    recent = [
        r
        for r in recalls_for(conn, [link.key for link in own.chain])
        if (d := parse_date(r["date"])) and d >= since
    ]
    if not recent:
        return None
    brand_n = normalize(brand)
    mentions = [r for r in recent if brand_n and brand_n in normalize(r["product"])]
    pick = (mentions or recent)[0]
    return {
        "level": "product" if mentions else "company",
        "count": len(mentions or recent),
        "date": pick["date"],
        "classification": pick["classification"],
        "reason": pick["reason"],
        "product": pick["product"],
        "url": pick["url"],
    }


def evaluate(
    conn: sqlite3.Connection,
    product: sqlite3.Row | dict,
    own: Ownership,
    s: Settings,
    rules: list[ing.RestrictedRule] | None = None,
) -> list[Result]:
    findings = ing.analyze(product["ingredients_text"], rules, name=product["name"])
    out = []
    for c in applicable(product["category"]):
        if c.id == "fights_cavities":
            out.append(check_fights_cavities(findings))
        elif c.id == "ingredients":
            out.append(check_ingredients(findings))
        elif c.id == "workers":
            out.append(check_workers(conn, own, s))
        elif c.id == "environment":
            out.append(check_environment(conn, own, s))
    return out
