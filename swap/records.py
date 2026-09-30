"""Storing and querying public records (labor cases, recalls) linked to orgs."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

from swap.db import mark_dataset
from swap.names import Match, normalize
from swap.sources import dol, openfda


def org_keys(conn: sqlite3.Connection) -> list[str]:
    return [r["key"] for r in conn.execute("SELECT key FROM orgs")]


def save_alias(conn: sqlite3.Connection, raw_name: str, match: Match) -> str:
    n = normalize(raw_name)
    conn.execute(
        "INSERT INTO aliases(name_norm, org_key, method, score) VALUES (?,?,?,?) "
        "ON CONFLICT(name_norm) DO UPDATE SET org_key=excluded.org_key, method=excluded.method, "
        "score=excluded.score WHERE aliases.method != 'manual'",
        (n, match.org_key, match.method, match.score),
    )
    return n


def save_labor_cases(conn: sqlite3.Connection, rows: Iterable[tuple[dict[str, Any], Match]]) -> int:
    n = 0
    for case, match in rows:
        name_norm = save_alias(conn, case["raw_name"], match)
        conn.execute(
            "INSERT OR REPLACE INTO labor_cases(id, source, raw_name, name_norm, state, date, "
            "violations, back_wages, penalty, severity, url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                case["id"],
                case["source"],
                case["raw_name"],
                name_norm,
                case["state"],
                case["date"],
                case["violations"],
                case["back_wages"],
                case["penalty"],
                case["severity"],
                case["url"],
            ),
        )
        n += 1
    conn.commit()
    return n


def load_whd(conn: sqlite3.Connection, paths: list[Path]) -> int:
    """Load every chunk of the WHD download, then mark the dataset loaded once.

    Marking it per chunk would let a partial load claim "no cases" for a company.
    """
    matcher = dol.Matcher(org_keys(conn))
    n = sum(save_labor_cases(conn, dol.read_whd(path, matcher)) for path in paths)
    mark_dataset(conn, "whd", n, dol.WHD_SOURCE_URL)
    conn.commit()
    return n


def load_osha(conn: sqlite3.Connection, inspections: Path, violations: Path) -> int:
    rows = dol.read_osha(inspections, violations, dol.Matcher(org_keys(conn)))
    n = save_labor_cases(conn, rows)
    mark_dataset(conn, "osha", n, dol.WHD_SOURCE_URL)
    conn.commit()
    return n


def save_recalls(conn: sqlite3.Connection, recalls: Iterable[dict[str, Any]], matcher) -> int:
    n = 0
    for r in recalls:
        hit = matcher(r["firm"])
        if not hit:
            continue  # a recall we can't tie to a tracked company confidently is dropped
        firm_norm = save_alias(conn, r["firm"], hit)
        conn.execute(
            "INSERT OR REPLACE INTO recalls(recall_number, firm, firm_norm, product, reason, "
            "classification, date, status, source, url) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                r["recall_number"],
                r["firm"],
                firm_norm,
                r["product"],
                r["reason"],
                r["classification"],
                r["date"],
                r["status"],
                r["source"],
                r["url"],
            ),
        )
        n += 1
    conn.commit()
    return n


def load_recalls(conn: sqlite3.Connection, client: httpx.Client) -> int:
    """Query openFDA once per tracked company or brand name."""
    matcher = dol.Matcher(org_keys(conn))
    total = 0
    names = [r["name"] for r in conn.execute("SELECT name FROM orgs WHERE source != 'demo'")]
    for name in names:
        total += save_recalls(conn, openfda.fetch_firm_recalls(client, name), matcher)
    mark_dataset(conn, "openfda_recalls", total, openfda.ENDPOINT)
    conn.commit()
    return total


def _placeholders(keys: list[str]) -> str:
    return ",".join("?" for _ in keys)


def labor_for(conn: sqlite3.Connection, keys: list[str]) -> list[sqlite3.Row]:
    if not keys:
        return []
    return conn.execute(
        "SELECT l.*, a.org_key FROM labor_cases l JOIN aliases a ON a.name_norm = l.name_norm "
        f"WHERE a.org_key IN ({_placeholders(keys)}) ORDER BY l.date DESC",
        keys,
    ).fetchall()


def recalls_for(conn: sqlite3.Connection, keys: list[str]) -> list[sqlite3.Row]:
    if not keys:
        return []
    return conn.execute(
        "SELECT r.*, a.org_key FROM recalls r JOIN aliases a ON a.name_norm = r.firm_norm "
        f"WHERE a.org_key IN ({_placeholders(keys)}) ORDER BY r.date DESC",
        keys,
    ).fetchall()
