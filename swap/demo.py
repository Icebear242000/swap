"""Fictional sample data, so a fresh deploy works before any real data is loaded.

Every brand, company, case and recall here is invented. Barcodes use the GS1
prefix 2, which is reserved for in-store use, so they can never collide with a
real product. The UI labels all of it "Sample".
"""

from __future__ import annotations

import sqlite3

from swap.db import mark_dataset
from swap.names import Match, normalize
from swap.ownership import add_parent, load_overrides, upsert_org
from swap.quantity import parse_ounces
from swap.records import save_alias
from swap.util import now_iso

PRODUCTS = [
    (
        "2000000000015",
        "Tidewell Fresh Mint Toothpaste",
        "Tidewell",
        "4.0 oz (113 g)",
        5.49,
        "Active ingredient: Sodium fluoride 0.24%. Inactive ingredients: sorbitol, "
        "hydrated silica, water, glycerin, xylitol, cellulose gum, peppermint oil, sodium benzoate",
    ),
    (
        "2000000000022",
        "Harbor & Pine Stannous Care",
        "Harbor & Pine",
        "4.1 oz (116 g)",
        6.99,
        "Active ingredient: Stannous fluoride 0.454%. Inactive ingredients: glycerin, hydrated "
        "silica, sodium hexametaphosphate, propylene glycol, zinc lactate, spearmint oil",
    ),
    (
        "2000000000039",
        "Kindred Everyday Clean",
        "Kindred",
        "5.0 oz (141 g)",
        3.99,
        "Active ingredient: Sodium monofluorophosphate 0.76%. Inactive ingredients: calcium "
        "carbonate, water, sorbitol, sodium lauryl sulfate, cellulose gum, flavor",
    ),
    (
        "2000000000046",
        "Fernleaf Mineral Paste",
        "Fernleaf",
        "3.5 oz (99 g)",
        8.00,
        "Ingredients: glycerin, water, hydroxyapatite, xylitol, silica, xanthan gum, "
        "peppermint oil, stevia leaf extract",
    ),
    (
        "2000000000053",
        "Lumen Glide Whitening",
        "Lumen",
        "4.8 oz (136 g)",
        4.49,
        "Active ingredient: Sodium fluoride 0.24%. Inactive ingredients: hydrated silica, "
        "sorbitol, PTFE, sodium lauryl sulfate, titanium dioxide, flavor",
    ),
    (
        "2000000000060",
        "Brightmore Cavity Shield",
        "Brightmore",
        "6.0 oz (170 g)",
        2.99,
        "Active ingredient: Sodium fluoride 0.24%. Inactive ingredients: sorbitol, water, hydrated "
        "silica, sodium lauryl sulfate, flavor, cellulose gum, sodium saccharin",
    ),
    (
        "2000000000077",
        "Sprigg Kids Berry",
        "Sprigg",
        "4.2 oz (119 g)",
        4.29,
        "Active ingredient: Sodium fluoride 0.24%. Inactive ingredients: sorbitol, water, hydrated "
        "silica, glycerin, natural berry flavor, xanthan gum",
    ),
    (
        "2000000000084",
        "Plainfield Baking Soda Paste",
        "Plainfield",
        "4.0 oz (113 g)",
        3.49,
        "Ingredients: sodium bicarbonate, glycerin, water, calcium carbonate, xylitol, "
        "peppermint oil",
    ),
]

# (brand, parent or None). Sprigg is deliberately absent to show "unknown" ownership.
OWNERSHIP = [
    ("Tidewell", None),
    ("Harbor & Pine", None),
    ("Kindred", None),
    ("Fernleaf", None),
    ("Plainfield", None),
    ("Lumen", "Consolidated Home Brands"),
    ("Brightmore", "Consolidated Home Brands"),
]

LABOR = [
    # id, raw name as it would be filed, org, date, violations, back wages, penalty, severity
    (
        "demo:osha-1",
        "CONSOLIDATED HOME BRANDS INC",
        "Consolidated Home Brands",
        "OSHA",
        "2024-05-14",
        3,
        0.0,
        41500.0,
        "willful",
        "OH",
    ),
    (
        "demo:whd-1",
        "Harbor and Pine Co.",
        "Harbor & Pine",
        "WHD",
        "2023-08-02",
        2,
        1200.0,
        0.0,
        None,
        "ME",
    ),
]

RECALLS = [
    (
        "DEMO-R-0001",
        "Kindred Goods LLC",
        "Kindred",
        "Kindred Everyday Clean toothpaste, 5.0 oz",
        "Microbial contamination found in one production lot.",
        "Class II",
        "20251103",
        "Terminated",
    ),
]


def seed(conn: sqlite3.Connection) -> int:
    load_overrides(conn)
    ts = now_iso()
    for barcode, name, brand, qty, price, ingredients in PRODUCTS:
        oz = parse_ounces(qty)
        conn.execute(
            "INSERT OR REPLACE INTO products(barcode, name, brand, category, ingredients_text, "
            "quantity_text, quantity_oz, quantity_unit, image_url, source, source_url, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                barcode,
                name,
                brand,
                "toothpaste",
                ingredients,
                qty,
                oz[0],
                oz[1],
                None,
                "demo",
                None,
                ts,
            ),
        )
        conn.execute("DELETE FROM prices WHERE barcode=? AND source='demo'", (barcode,))
        conn.execute(
            "INSERT INTO prices(barcode, price, currency, date, location, source) "
            "VALUES (?,?,?,?,?,?)",
            (barcode, price, "USD", "2026-09-01", "Sample store", "demo"),
        )
    for brand, parent in OWNERSHIP:
        child = upsert_org(conn, brand, "brand", "demo")
        if parent:
            add_parent(conn, child, upsert_org(conn, parent, "company", "demo"), "demo", None)
    for cid, raw, org, source, date, viol, wages, penalty, sev, state in LABOR:
        name_norm = save_alias(conn, raw, Match(normalize(org), "manual", 1.0))
        conn.execute(
            "INSERT OR REPLACE INTO labor_cases(id, source, raw_name, name_norm, state, date, "
            "violations, back_wages, penalty, severity, url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cid, source, raw, name_norm, state, date, viol, wages, penalty, sev, None),
        )
    for number, firm, org, product, reason, cls, date, status in RECALLS:
        firm_norm = save_alias(conn, firm, Match(normalize(org), "manual", 1.0))
        conn.execute(
            "INSERT OR REPLACE INTO recalls(recall_number, firm, firm_norm, product, reason, "
            "classification, date, status, source, url) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (number, firm, firm_norm, product, reason, cls, date, status, "demo", None),
        )
    mark_dataset(conn, "demo_labor", len(LABOR), None)
    mark_dataset(conn, "demo_recalls", len(RECALLS), None)
    conn.commit()
    return len(PRODUCTS)


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
