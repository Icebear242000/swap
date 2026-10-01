"""Command line: load data into the database.

swap seed-demo
swap load-products --pages 5
swap load-ownership
swap load-recalls
swap load-whd raw/whd/*.csv
swap load-osha path/to/osha_inspection.csv path/to/osha_violation.csv
swap load-epa raw/epa
swap check-columns whd raw/whd/<chunk>.csv
swap check-columns epa-defendants raw/epa/CASE_DEFENDANTS.csv
swap serve
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from swap import demo, ownership, records
from swap.config import get_settings
from swap.db import connect, init_schema, mark_dataset
from swap.service import Service
from swap.sources import dol, epa, openbeautyfacts
from swap.sources.http import make_client


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="swap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed-demo", help="load fictional sample products")
    lp = sub.add_parser("load-products", help="pull toothpastes from Open Beauty Facts")
    lp.add_argument("--tag", default="en:toothpastes")
    lp.add_argument("--pages", type=int, default=5)
    sub.add_parser("load-ownership", help="resolve brand owners on Wikidata")
    sub.add_parser("load-recalls", help="pull recalls from openFDA for tracked companies")
    w = sub.add_parser("load-whd", help="load Wage and Hour Division CSVs (all chunks at once)")
    w.add_argument("csv", type=Path, nargs="+")
    o = sub.add_parser("load-osha", help="load OSHA inspection + violation CSVs")
    o.add_argument("inspections", type=Path)
    o.add_argument("violations", type=Path)
    e = sub.add_parser("load-epa", help="load EPA federal enforcement cases (unzipped folder)")
    e.add_argument("folder", type=Path)
    cc = sub.add_parser("check-columns", help="compare a bulk file's header to what we expect")
    cc.add_argument("kind", choices=sorted(_expected_columns()))
    cc.add_argument("csv", type=Path)
    sv = sub.add_parser("serve", help="run the web app")
    sv.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    s = get_settings()
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("swap.api:app", host="0.0.0.0", port=args.port)
        return 0
    if args.cmd == "check-columns":
        return check_columns(args.kind, args.csv)

    conn = connect(s.db_path)
    init_schema(conn)
    ownership.load_overrides(conn)

    if args.cmd == "seed-demo":
        print(f"Seeded {demo.seed(conn)} sample products.")
    elif args.cmd in ("load-products", "load-ownership", "load-recalls"):
        with make_client(s.user_agent, s.http_timeout_s) as client:
            if args.cmd == "load-products":
                svc = Service(conn, s, client)
                total = 0
                for page in range(1, args.pages + 1):
                    batch = openbeautyfacts.search_category(client, args.tag, page)
                    if not batch:
                        break
                    for p in batch:
                        p["category"] = p["category"] or openbeautyfacts.CATEGORY_TAGS.get(args.tag)
                        svc.save_product(p)
                    total += len(batch)
                    print(f"page {page}: {len(batch)} products")
                mark_dataset(conn, f"obf:{args.tag}", total, openbeautyfacts.BASE)
                conn.commit()
                print(f"Saved {total} products.")
            elif args.cmd == "load-ownership":
                brands = [
                    r["brand"]
                    for r in conn.execute(
                        "SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL "
                        "AND source != 'demo'"
                    )
                ]
                todo = [b for b in brands if not ownership.resolve_brand_key(conn, [b])]
                print(f"Looking up {len(todo)} brands on Wikidata...")
                print(f"Added {ownership.load_from_wikidata(conn, client, todo)} ownership links.")
            else:
                print(f"Saved {records.load_recalls(conn, client)} recalls.")
    elif args.cmd == "load-whd":
        print(f"Saved {records.load_whd(conn, args.csv)} matched WHD cases.")
    elif args.cmd == "load-osha":
        print(
            f"Saved {records.load_osha(conn, args.inspections, args.violations)} "
            "matched OSHA inspections."
        )
    elif args.cmd == "load-epa":
        print(f"Saved {records.load_epa(conn, args.folder)} matched EPA cases.")
    return 0


def _expected_columns() -> dict[str, tuple[dict[str, str], str]]:
    """kind -> (expected columns, file that defines them)."""
    out = {
        "whd": (dol.WHD_COLUMNS, "swap/sources/dol.py"),
        "osha-inspection": (dol.OSHA_INSPECTION_COLUMNS, "swap/sources/dol.py"),
        "osha-violation": (dol.OSHA_VIOLATION_COLUMNS, "swap/sources/dol.py"),
    }
    for kind, cols in epa.COLUMNS.items():
        out[f"epa-{kind}"] = (cols, "swap/sources/epa.py")
    return out


def check_columns(kind: str, path: Path) -> int:
    expected, defined_in = _expected_columns()[kind]
    header = set(dol.read_header(path))
    missing = {k: v for k, v in expected.items() if v not in header}
    if missing:
        print(f"Missing columns (edit {defined_in}):")
        for field, col in missing.items():
            print(f"  {field}: expected '{col}'")
        return 1
    print("All expected columns are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
