"""Wikidata: who owns which brand, via SPARQL.

We read two ownership properties: P127 (owned by) and P749 (parent organization).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from swap.sources.http import get_json

ENDPOINT = "https://query.wikidata.org/sparql"
OWNERSHIP_PROPS = "wdt:P127|wdt:P749"
# brand, trademark, business, enterprise, company, public company, subsidiary
ORG_TYPES = "wd:Q431289 wd:Q167270 wd:Q4830453 wd:Q6881511 wd:Q783794 wd:Q891723 wd:Q658255"


def entity_url(qid: str) -> str:
    return f"https://www.wikidata.org/wiki/{qid}"


def _literal(label: str) -> str:
    return json.dumps(label) + "@en"


def labels_query(labels: list[str]) -> str:
    values = " ".join(_literal(label) for label in labels)
    return f"""
SELECT ?label ?item ?itemLabel ?parent ?parentLabel WHERE {{
  VALUES ?label {{ {values} }}
  VALUES ?type {{ {ORG_TYPES} }}
  ?item rdfs:label ?label ;
        wdt:P31/wdt:P279? ?type .
  OPTIONAL {{ ?item {OWNERSHIP_PROPS} ?parent . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def ids_query(qids: list[str]) -> str:
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?itemLabel ?parent ?parentLabel WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item {OWNERSHIP_PROPS} ?parent . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def _qid(uri: str | None) -> str | None:
    return uri.rsplit("/", 1)[-1] if uri else None


def parse_rows(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Group SPARQL bindings into [{label, id, name, parents: [{id, name}]}]."""
    if not data:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for b in data.get("results", {}).get("bindings", []):
        qid = _qid(b.get("item", {}).get("value"))
        if not qid:
            continue
        entry = grouped.setdefault(
            qid,
            {
                "label": b.get("label", {}).get("value"),
                "id": qid,
                "name": b.get("itemLabel", {}).get("value", qid),
                "parents": [],
            },
        )
        pid = _qid(b.get("parent", {}).get("value"))
        if pid and pid not in {p["id"] for p in entry["parents"]}:
            entry["parents"].append({"id": pid, "name": b.get("parentLabel", {}).get("value", pid)})
    return list(grouped.values())


def _run(client: httpx.Client, query: str) -> dict[str, Any] | None:
    return get_json(client, ENDPOINT, {"query": query, "format": "json"})


def lookup_labels(client: httpx.Client, labels: list[str]) -> list[dict[str, Any]]:
    variants: list[str] = []
    for label in labels:
        for v in (label, label.title()):
            if v not in variants:
                variants.append(v)
    return parse_rows(_run(client, labels_query(variants))) if variants else []


def lookup_ids(client: httpx.Client, qids: list[str]) -> list[dict[str, Any]]:
    return parse_rows(_run(client, ids_query(qids))) if qids else []
