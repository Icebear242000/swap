"""SQLite storage. One file, no server, which keeps deploys and demos simple."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from swap.util import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    barcode          TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    brand            TEXT,
    category         TEXT,
    ingredients_text TEXT,
    quantity_text    TEXT,
    quantity_oz      REAL,
    quantity_unit    TEXT,
    image_url        TEXT,
    source           TEXT NOT NULL,        -- 'openbeautyfacts' | 'demo'
    source_url       TEXT,
    fetched_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

CREATE TABLE IF NOT EXISTS prices (
    barcode    TEXT NOT NULL,
    price      REAL NOT NULL,
    currency   TEXT NOT NULL,
    date       TEXT,
    location   TEXT,
    source     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_barcode ON prices(barcode);

-- Remembers live lookups (including misses) so we don't call outside APIs on every scan.
CREATE TABLE IF NOT EXISTS lookups (
    kind       TEXT NOT NULL,              -- 'prices' | 'ownership'
    key        TEXT NOT NULL,
    looked_at  TEXT NOT NULL,
    found      INTEGER NOT NULL,
    PRIMARY KEY (kind, key)
);

-- Brands and companies are both nodes in one ownership graph.
CREATE TABLE IF NOT EXISTS orgs (
    key          TEXT PRIMARY KEY,         -- normalized name
    name         TEXT NOT NULL,
    wikidata_id  TEXT,
    kind         TEXT NOT NULL,            -- 'brand' | 'company'
    source       TEXT NOT NULL             -- 'override' | 'wikidata' | 'demo'
);

CREATE TABLE IF NOT EXISTS org_parents (
    child_key   TEXT NOT NULL,
    parent_key  TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_url  TEXT,
    PRIMARY KEY (child_key, parent_key)
);

-- How messy names in government records map onto orgs.
CREATE TABLE IF NOT EXISTS aliases (
    name_norm  TEXT PRIMARY KEY,
    org_key    TEXT NOT NULL,
    method     TEXT NOT NULL,              -- 'exact' | 'token' | 'manual'
    score      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS labor_cases (
    id           TEXT PRIMARY KEY,         -- 'WHD:<case_id>' | 'OSHA:<activity_nr>'
    source       TEXT NOT NULL,            -- 'WHD' | 'OSHA' | 'demo'
    raw_name     TEXT NOT NULL,
    name_norm    TEXT NOT NULL,
    state        TEXT,
    date         TEXT,
    violations   INTEGER,
    back_wages   REAL,
    penalty      REAL,
    severity     TEXT,                     -- OSHA: 'willful' | 'repeat' | 'serious' | 'other'
    url          TEXT
);
CREATE INDEX IF NOT EXISTS idx_labor_name ON labor_cases(name_norm);

-- Concluded federal EPA enforcement cases (ICIS FE&C), Superfund excluded.
CREATE TABLE IF NOT EXISTS env_cases (
    id         TEXT PRIMARY KEY,           -- 'EPA:<case_number>'
    raw_name   TEXT NOT NULL,              -- defendant name as filed
    name_norm  TEXT NOT NULL,
    case_name  TEXT,
    law        TEXT,                       -- primary law(s), e.g. 'TSCA', 'CAA,CWA'
    date       TEXT,                       -- latest settlement date, YYYY-MM-DD
    penalty    REAL,                       -- federal penalty for the whole case
    summary    TEXT,
    url        TEXT
);
CREATE INDEX IF NOT EXISTS idx_env_name ON env_cases(name_norm);

CREATE TABLE IF NOT EXISTS recalls (
    recall_number  TEXT PRIMARY KEY,
    firm           TEXT NOT NULL,
    firm_norm      TEXT NOT NULL,
    product        TEXT,
    reason         TEXT,
    classification TEXT,
    date           TEXT,
    status         TEXT,
    source         TEXT NOT NULL,
    url            TEXT
);
CREATE INDEX IF NOT EXISTS idx_recalls_firm ON recalls(firm_norm);

-- Which bulk datasets are loaded. A missing record only means "no violations found"
-- when the dataset that would contain it is actually loaded.
CREATE TABLE IF NOT EXISTS datasets (
    name       TEXT PRIMARY KEY,
    loaded_at  TEXT NOT NULL,
    rows       INTEGER NOT NULL,
    source_url TEXT
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def mark_dataset(conn: sqlite3.Connection, name: str, rows: int, source_url: str | None) -> None:
    conn.execute(
        "INSERT INTO datasets(name, loaded_at, rows, source_url) VALUES (?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET loaded_at=excluded.loaded_at, rows=excluded.rows, "
        "source_url=excluded.source_url",
        (name, now_iso(), rows, source_url),
    )


def loaded_datasets(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["name"]: r["loaded_at"] for r in conn.execute("SELECT name, loaded_at FROM datasets")}
