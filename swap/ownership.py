"""The ownership graph: brand -> parent company -> the parent's parent.

Sources, in priority order:
  1. rules/ownership_overrides.csv, facts you have checked yourself
  2. Wikidata (owned by / parent organization), loaded in bulk or on a scan miss
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from importlib import resources

import httpx

from swap.names import normalize
from swap.sources import wikidata
from swap.util import now_iso

MAX_DEPTH = 6


def upsert_org(
    conn: sqlite3.Connection, name: str, kind: str, source: str, wikidata_id: str | None = None
) -> str:
    key = normalize(name)
    conn.execute(
        "INSERT INTO orgs(key, name, wikidata_id, kind, source) VALUES (?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET "
        "wikidata_id=COALESCE(orgs.wikidata_id, excluded.wikidata_id), "
        # An override or a brand classification should not be downgraded by a later load.
        "kind=CASE WHEN orgs.source='override' THEN orgs.kind ELSE excluded.kind END",
        (key, name, wikidata_id, kind, source),
    )
    return key


def add_parent(
    conn: sqlite3.Connection, child_key: str, parent_key: str, source: str, url: str | None
) -> None:
    if child_key == parent_key:
        return
    conn.execute(
        "INSERT OR IGNORE INTO org_parents(child_key, parent_key, source, source_url) "
        "VALUES (?,?,?,?)",
        (child_key, parent_key, source, url),
    )


def load_overrides(conn: sqlite3.Connection) -> int:
    path = resources.files("swap").joinpath("rules/ownership_overrides.csv")
    n = 0
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            child = upsert_org(conn, row["child"], row["child_kind"], "override")
            parent = upsert_org(conn, row["parent"], "company", "override")
            add_parent(conn, child, parent, f"override: {row['source_note']}", None)
            n += 1
    conn.commit()
    return n


def load_from_wikidata(
    conn: sqlite3.Connection, client: httpx.Client, brand_names: list[str], batch: int = 20
) -> int:
    """Resolve brands on Wikidata, then walk up parent companies level by level."""
    added = 0
    frontier: list[str] = []
    for i in range(0, len(brand_names), batch):
        chunk = brand_names[i : i + batch]
        entities = wikidata.lookup_labels(client, chunk)
        ids_by_key: dict[str, set[str]] = {}
        for entity in entities:
            ids_by_key.setdefault(normalize(entity["label"] or entity["name"]), set()).add(
                entity["id"]
            )
        for entity in entities:
            # Several different items share this name (e.g. "Signal" is a record label and
            # a toothpaste). Picking one is a guess, and a wrong owner is worse than none.
            if len(ids_by_key[normalize(entity["label"] or entity["name"])]) > 1:
                continue
            child = upsert_org(
                conn, entity["label"] or entity["name"], "brand", "wikidata", entity["id"]
            )
            for p in entity["parents"]:
                parent = upsert_org(conn, p["name"], "company", "wikidata", p["id"])
                add_parent(conn, child, parent, "wikidata", wikidata.entity_url(entity["id"]))
                frontier.append(p["id"])
                added += 1
        for name in chunk:
            _record_lookup(conn, normalize(name))
    seen: set[str] = set()
    for _ in range(MAX_DEPTH):
        todo = [q for q in dict.fromkeys(frontier) if q not in seen]
        if not todo:
            break
        seen.update(todo)
        frontier = []
        for entity in wikidata.lookup_ids(client, todo):
            child = upsert_org(conn, entity["name"], "company", "wikidata", entity["id"])
            for p in entity["parents"]:
                parent = upsert_org(conn, p["name"], "company", "wikidata", p["id"])
                add_parent(conn, child, parent, "wikidata", wikidata.entity_url(entity["id"]))
                frontier.append(p["id"])
                added += 1
    conn.commit()
    return added


def _record_lookup(conn: sqlite3.Connection, key: str) -> None:
    found = conn.execute("SELECT 1 FROM orgs WHERE key=?", (key,)).fetchone() is not None
    conn.execute(
        "INSERT INTO lookups(kind, key, looked_at, found) VALUES ('ownership',?,?,?) "
        "ON CONFLICT(kind, key) DO UPDATE SET looked_at=excluded.looked_at, found=excluded.found",
        (key, now_iso(), int(found)),
    )


def was_looked_up(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT 1 FROM lookups WHERE kind='ownership' AND key=?", (key,)).fetchone()
    return row is not None


@dataclass
class Link:
    key: str
    name: str
    kind: str
    source: str  # where the link *to* this node came from
    source_url: str | None


@dataclass
class Ownership:
    known: bool  # is the brand in our ownership data at all?
    chain: list[Link]  # brand first, ultimate parent last
    note: str | None = None

    @property
    def ultimate(self) -> Link | None:
        return self.chain[-1] if self.chain else None

    @property
    def has_parent(self) -> bool:
        return len(self.chain) > 1


def resolve_brand_key(conn: sqlite3.Connection, brands: list[str]) -> str | None:
    for b in brands:
        key = normalize(b)
        if key and conn.execute("SELECT 1 FROM orgs WHERE key=?", (key,)).fetchone():
            return key
    return None


def chain_for(conn: sqlite3.Connection, key: str | None) -> Ownership:
    if not key:
        return Ownership(False, [])
    row = conn.execute("SELECT key, name, kind, source FROM orgs WHERE key=?", (key,)).fetchone()
    if not row:
        return Ownership(False, [])
    chain = [Link(row["key"], row["name"], row["kind"], row["source"], None)]
    note = None
    seen = {key}
    current = key
    for _ in range(MAX_DEPTH):
        parents = conn.execute(
            "SELECT p.parent_key, p.source, p.source_url, o.name, o.kind FROM org_parents p "
            "JOIN orgs o ON o.key = p.parent_key WHERE p.child_key=? "
            # Prefer checked overrides, then a stable order.
            "ORDER BY CASE WHEN p.source LIKE 'override%' THEN 0 ELSE 1 END, p.parent_key",
            (current,),
        ).fetchall()
        if not parents:
            break
        if len(parents) > 1:
            names = ", ".join(p["name"] for p in parents)
            note = f"More than one owner on record ({names}); showing the first."
        p = parents[0]
        if p["parent_key"] in seen:
            note = "Ownership records loop back on themselves; stopped there."
            break
        seen.add(p["parent_key"])
        chain.append(Link(p["parent_key"], p["name"], p["kind"], p["source"], p["source_url"]))
        current = p["parent_key"]
    return Ownership(True, chain, note)


def descendants(conn: sqlite3.Connection, key: str) -> list[dict[str, str]]:
    """Every brand/company under `key` in the graph (breadth-first, cycle-safe)."""
    out, seen, queue = [], {key}, [key]
    while queue:
        current = queue.pop(0)
        for r in conn.execute(
            "SELECT o.key, o.name, o.kind FROM org_parents p JOIN orgs o ON o.key=p.child_key "
            "WHERE p.parent_key=? ORDER BY o.name",
            (current,),
        ):
            if r["key"] not in seen:
                seen.add(r["key"])
                out.append(dict(r))
                queue.append(r["key"])
    return out
