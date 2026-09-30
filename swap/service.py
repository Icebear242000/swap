"""Orchestrates one scan: product -> ownership -> checkpoints -> alternatives."""

from __future__ import annotations

import logging
import sqlite3
import statistics
from typing import Any

import httpx

from swap import checkpoints as cp
from swap import ownership
from swap.config import Settings
from swap.ingredients import RestrictedRule, load_restricted_rules
from swap.names import normalize
from swap.ranking import Prefs, gate, score, unverified
from swap.sources import openbeautyfacts, openprices
from swap.util import is_older_than, now_iso

log = logging.getLogger("swap.service")


class Service:
    def __init__(
        self, conn: sqlite3.Connection, settings: Settings, client: httpx.Client | None
    ) -> None:
        self.conn = conn
        self.s = settings
        self.client = client if settings.live_lookups else None
        self.rules: list[RestrictedRule] = load_restricted_rules()

    # ---- products -------------------------------------------------------

    def save_product(self, p: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO products(barcode, name, brand, category, ingredients_text, "
            "quantity_text, quantity_oz, quantity_unit, image_url, source, source_url, fetched_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                p["barcode"],
                p["name"],
                p["brand"],
                p["category"],
                p["ingredients_text"],
                p["quantity_text"],
                p["quantity_oz"],
                p["quantity_unit"],
                p["image_url"],
                p["source"],
                p["source_url"],
                now_iso(),
            ),
        )
        self.conn.commit()

    def get_product(self, barcode: str) -> sqlite3.Row | None:
        row = self.conn.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
        if row or not self.client:
            return row
        fetched = openbeautyfacts.fetch_product(self.client, barcode)
        if not fetched:
            return None
        self.save_product(fetched)
        self._ensure_ownership(fetched.get("brands_all") or [fetched["brand"]])
        return self.conn.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()

    def search(self, q: str, limit: int = 12) -> list[dict[str, Any]]:
        like = f"%{q.strip()}%"
        rows = self.conn.execute(
            "SELECT barcode, name, brand, source FROM products "
            "WHERE name LIKE ? OR brand LIKE ? OR barcode = ? ORDER BY name LIMIT ?",
            (like, like, q.strip(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def samples(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT barcode, name, brand FROM products WHERE source='demo' ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- ownership ------------------------------------------------------

    def _ensure_ownership(self, brands: list[str]) -> None:
        brands = [b for b in brands if b]
        if not brands or not self.client or ownership.resolve_brand_key(self.conn, brands):
            return
        todo = [b for b in brands if not ownership.was_looked_up(self.conn, normalize(b))]
        if todo:
            try:
                ownership.load_from_wikidata(self.conn, self.client, todo[:3])
            except Exception:  # an outside failure must never break a scan
                log.exception("Wikidata lookup failed for %s", todo)

    def ownership_for(self, product: sqlite3.Row) -> ownership.Ownership:
        brands = [product["brand"]] if product["brand"] else []
        return ownership.chain_for(self.conn, ownership.resolve_brand_key(self.conn, brands))

    # ---- prices ---------------------------------------------------------

    def price_per_oz(self, product: sqlite3.Row, live: bool = True) -> dict[str, Any] | None:
        barcode = product["barcode"]
        if live and self.client and product["source"] != "demo":
            looked = self.conn.execute(
                "SELECT looked_at FROM lookups WHERE kind='prices' AND key=?", (barcode,)
            ).fetchone()
            if not looked or is_older_than(looked["looked_at"], self.s.price_max_age_days):
                prices = openprices.fetch_prices(self.client, barcode)
                self.conn.execute(
                    "DELETE FROM prices WHERE barcode=? AND source='openprices'", (barcode,)
                )
                self.conn.executemany(
                    "INSERT INTO prices(barcode, price, currency, date, location, source) "
                    "VALUES (:barcode,:price,:currency,:date,:location,:source)",
                    prices,
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO lookups(kind, key, looked_at, found) "
                    "VALUES ('prices',?,?,?)",
                    (barcode, now_iso(), int(bool(prices))),
                )
                self.conn.commit()
        rows = self.conn.execute(
            "SELECT price, date, source FROM prices WHERE barcode=? AND currency='USD' "
            "ORDER BY date DESC LIMIT 5",
            (barcode,),
        ).fetchall()
        if not rows:
            return None
        price = statistics.median(r["price"] for r in rows)
        out = {
            "price": round(price, 2),
            "currency": "USD",
            "reports": len(rows),
            "latest": rows[0]["date"],
            "source": rows[0]["source"],
        }
        if product["quantity_oz"]:
            out["per_oz"] = round(price / product["quantity_oz"], 2)
            out["unit"] = product["quantity_unit"] or "oz"
        return out

    # ---- the scan -------------------------------------------------------

    def evaluate(self, product: sqlite3.Row) -> dict[str, Any]:
        own = self.ownership_for(product)
        results = cp.evaluate(self.conn, product, own, self.s, self.rules)
        return {"product": product, "ownership": own, "results": results}

    def report(self, barcode: str, prefs: Prefs) -> dict[str, Any] | None:
        product = self.get_product(barcode)
        if not product:
            return None
        ev = self.evaluate(product)
        own: ownership.Ownership = ev["ownership"]
        siblings = []
        if own.has_parent:
            siblings = [
                d
                for d in ownership.descendants(self.conn, own.ultimate.key)
                if d["kind"] == "brand" and d["key"] != own.chain[0].key
            ]
        return {
            "product": self._product_dict(product),
            "price": self.price_per_oz(product),
            "checkpoints": [r.to_dict() for r in ev["results"]],
            "failed_required": gate(ev["results"], prefs),
            "unverified_required": unverified(ev["results"], prefs),
            "score": score(ev["results"], prefs),
            "ownership": {
                "known": own.known,
                "chain": [
                    {
                        "name": link.name,
                        "kind": link.kind,
                        "source": link.source,
                        "url": link.source_url,
                    }
                    for link in own.chain
                ],
                "note": own.note,
                "siblings": [s["name"] for s in siblings][:12],
            },
            "recall": cp.recall_warning(self.conn, own, product["name"], product["brand"], self.s),
            "supported_category": product["category"] is not None,
        }

    def alternatives(self, barcode: str, prefs: Prefs, limit: int = 10) -> dict[str, Any] | None:
        product = self.get_product(barcode)
        if not product:
            return None
        base = self.evaluate(product)
        base_owner = base["ownership"].ultimate.key if base["ownership"].known else None
        base_score = score(base["results"], prefs)
        if not product["category"]:
            return {"category": None, "shown": [], "hidden": [], "base_score": base_score}
        shown, hidden = [], []
        candidates = self.conn.execute(
            "SELECT * FROM products WHERE category=? AND barcode != ?",
            (product["category"], barcode),
        ).fetchall()
        for c in candidates:
            ev = self.evaluate(c)
            own = ev["ownership"]
            item = {
                "product": self._product_dict(c),
                "checkpoints": [
                    {"id": r.id, "label": r.label, "status": r.status, "summary": r.summary}
                    for r in ev["results"]
                ],
                "score": score(ev["results"], prefs),
                "owner": own.ultimate.name if own.known else None,
            }
            reasons = gate(ev["results"], prefs)
            if (
                prefs.hide_same_owner
                and base_owner
                and own.known
                and own.ultimate.key == base_owner
            ):
                reasons.append(f"Owned by the same company as your product ({own.ultimate.name}).")
            if reasons:
                item["reasons"] = reasons
                hidden.append(item)
                continue
            item["unverified"] = unverified(ev["results"], prefs)
            item["better"] = item["score"] > base_score
            item["price"] = self.price_per_oz(c, live=False)  # cached only: keeps lists fast
            item["recall"] = cp.recall_warning(self.conn, own, c["name"], c["brand"], self.s)
            shown.append(item)
        shown.sort(
            key=lambda i: (
                -i["score"],
                bool(i["recall"]),  # among equals, a recent recall ranks lower
                len(i["unverified"]),
                (i["price"] or {}).get("per_oz", float("inf")),
                i["product"]["name"],
            )
        )
        hidden.sort(key=lambda i: i["product"]["name"])
        return {
            "category": product["category"],
            "base_score": base_score,
            "shown": shown[:limit],
            "hidden": hidden,
        }

    @staticmethod
    def _product_dict(p: sqlite3.Row) -> dict[str, Any]:
        keys = (
            "barcode",
            "name",
            "brand",
            "category",
            "quantity_text",
            "image_url",
            "source",
            "source_url",
            "ingredients_text",
        )
        return {k: p[k] for k in keys}
