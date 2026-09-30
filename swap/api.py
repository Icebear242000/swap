"""HTTP API and static web app."""

from __future__ import annotations

import re
import threading
from contextlib import asynccontextmanager
from importlib import resources

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from swap import demo
from swap.checkpoints import CHECKPOINTS
from swap.config import Settings, get_settings
from swap.db import connect, init_schema, loaded_datasets
from swap.ownership import load_overrides
from swap.ranking import IMPORTANCE, Prefs
from swap.service import Service
from swap.sources.http import make_client

BARCODE = re.compile(r"^\d{6,14}$")


def create_app(settings: Settings | None = None, client: httpx.Client | None = None) -> FastAPI:
    s = settings or get_settings()
    state: dict = {}
    lock = threading.Lock()  # SQLite connection shared across worker threads

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        conn = connect(s.db_path)
        init_schema(conn)
        load_overrides(conn)
        if s.seed_demo_if_empty and demo.is_empty(conn):
            demo.seed(conn)
        http = client or make_client(s.user_agent, s.http_timeout_s)
        state["svc"] = Service(conn, s, http)
        yield
        if client is None:
            http.close()
        conn.close()

    app = FastAPI(title="Swap", version="0.1.0", lifespan=lifespan)

    def svc() -> Service:
        return state["svc"]

    def prefs(required: str | None, importance: str | None, hide_same_owner: bool) -> Prefs:
        return Prefs.parse(required, importance, hide_same_owner)

    @app.get("/api/health")
    def health():
        with lock:
            n = svc().conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            return {"ok": True, "products": n, "datasets": loaded_datasets(svc().conn)}

    @app.get("/api/checkpoints")
    def checkpoint_defs():
        d = Prefs()
        return {
            "checkpoints": [
                {
                    "id": c.id,
                    "label": c.label,
                    "question": c.question,
                    "categories": c.categories,
                    "default_required": c.id in d.required,
                    "default_importance": d.importance[c.id],
                }
                for c in CHECKPOINTS
            ],
            "importance_levels": [k for k in IMPORTANCE if k != "off"],
        }

    @app.get("/api/samples")
    def samples():
        with lock:
            return {"samples": svc().samples()}

    @app.get("/api/search")
    def search(q: str = Query(min_length=2, max_length=80)):
        with lock:
            return {"results": svc().search(q)}

    def _barcode(barcode: str) -> str:
        b = barcode.strip()
        if not BARCODE.match(b):
            raise HTTPException(400, "A barcode is 6 to 14 digits.")
        return b

    @app.get("/api/products/{barcode}")
    def product(
        barcode: str,
        required: str | None = None,
        importance: str | None = None,
        hide_same_owner: bool = False,
    ):
        with lock:
            rep = svc().report(_barcode(barcode), prefs(required, importance, hide_same_owner))
        if not rep:
            raise HTTPException(
                404, "We don't have this product yet, and Open Beauty Facts doesn't list it either."
            )
        return rep

    @app.get("/api/products/{barcode}/alternatives")
    def alternatives(
        barcode: str,
        required: str | None = None,
        importance: str | None = None,
        hide_same_owner: bool = False,
    ):
        with lock:
            alts = svc().alternatives(
                _barcode(barcode), prefs(required, importance, hide_same_owner)
            )
        if alts is None:
            raise HTTPException(404, "Product not found.")
        return alts

    web = resources.files("swap").joinpath("web")
    app.mount("/static", StaticFiles(directory=str(web)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(web.joinpath("index.html")))

    return app


app = create_app()
