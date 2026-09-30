"""Ingredient checks. Everything here is a rule you can read, not a model."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from importlib import resources

FLUORIDE_TERMS = (
    "sodium fluoride",
    "stannous fluoride",
    "sodium monofluorophosphate",
    "monofluorophosphate",
    "amine fluoride",
    "olaflur",
    "potassium fluoride",
)
HYDROXYAPATITE_TERMS = ("hydroxyapatite", "hydroxylapatite")

# PFAS show up in personal care as fluoropolymers (PTFE) and per/polyfluoro compounds.
# Fluoride salts are not PFAS, so the pattern must never match "sodium fluoride".
PFAS_PATTERN = re.compile(
    r"\b(ptfe|pfas|pfoa|pfos)\b|polytetrafluoroethylene|perfluoro|polyfluoro|"
    r"fluoroalkyl|fluoropolymer|tetrafluoro",
    re.IGNORECASE,
)

_SPLIT = re.compile(r"[,;.](?![0-9])|\(|\)|\[|\]")


def split_ingredients(text: str | None) -> list[str]:
    """Split a label's ingredient text into cleaned, lowercase entries."""
    if not text:
        return []
    cleaned = re.sub(r"(?i)^\s*(active )?ingredients?\s*:", "", text)
    cleaned = re.sub(r"(?i)(inactive|active) ingredients?\s*:", ",", cleaned)
    parts = [p.strip(" *_-:\n\t").lower() for p in _SPLIT.split(cleaned)]
    return [p for p in parts if len(p) > 1]


@dataclass(frozen=True)
class RestrictedRule:
    name: str
    aliases: tuple[str, ...]
    severity: str  # 'fail' | 'caution'
    source: str
    note: str


def load_restricted_rules() -> list[RestrictedRule]:
    path = resources.files("swap").joinpath("rules/restricted_ingredients.csv")
    rules = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aliases = tuple(a.strip().lower() for a in row["aliases"].split("|") if a.strip())
            rules.append(
                RestrictedRule(
                    name=row["name"].strip(),
                    aliases=(row["name"].strip().lower(), *aliases),
                    severity=row["severity"].strip(),
                    source=row["source"].strip(),
                    note=row["note"].strip(),
                )
            )
    return rules


@dataclass(frozen=True)
class IngredientFindings:
    listed: bool
    fluoride: list[str]
    hydroxyapatite: list[str]
    pfas: list[str]
    restricted: list[tuple[RestrictedRule, str]]


def analyze(text: str | None, rules: list[RestrictedRule] | None = None) -> IngredientFindings:
    items = split_ingredients(text)
    rules = rules if rules is not None else load_restricted_rules()
    fluoride = [i for i in items if any(t in i for t in FLUORIDE_TERMS)]
    hydroxy = [i for i in items if any(t in i for t in HYDROXYAPATITE_TERMS)]
    pfas = [i for i in items if PFAS_PATTERN.search(i)]
    restricted = []
    for item in items:
        for rule in rules:
            if any(re.search(rf"\b{re.escape(a)}\b", item) for a in rule.aliases):
                restricted.append((rule, item))
    return IngredientFindings(bool(items), fluoride, hydroxy, pfas, restricted)
