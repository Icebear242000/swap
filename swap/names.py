"""Company-name normalization and matching.

Government records spell the same company many ways: "Colgate-Palmolive Co",
"COLGATE PALMOLIVE COMPANY INC", "Colgate Palmolive Co.". We normalize names,
then match conservatively. A wrong match would pin someone else's violations on a
company, so anything uncertain stays unmatched and shows as "unknown".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Legal-form and filler tokens that don't identify a company.
_SUFFIXES = {
    "inc",
    "incorporated",
    "co",
    "company",
    "corp",
    "corporation",
    "llc",
    "ltd",
    "limited",
    "lp",
    "llp",
    "plc",
    "pllc",
    "sa",
    "ag",
    "gmbh",
    "nv",
    "bv",
    "the",
    "dba",
    "of",
    "and",
}
_SPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")


def normalize(name: str | None) -> str:
    """'Tom's of Maine, Inc.' -> 'toms maine'. Stable, lowercase, suffix-free."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ").replace("'", "").replace("\u2019", "")
    s = s.replace(".", "")  # "L.L.C." -> "llc", "Co." -> "co"
    s = _NON_WORD.sub(" ", s)
    tokens = [t for t in _SPACE.split(s) if t and t not in _SUFFIXES]
    return " ".join(tokens)


def tokens(name_norm: str) -> set[str]:
    return set(name_norm.split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class Match:
    org_key: str
    method: str  # 'exact' | 'token'
    score: float


def best_match(raw_name: str, org_keys: list[str], threshold: float = 0.75) -> Match | None:
    """Match a raw record name to one org key, or None if it isn't clear-cut.

    Rules, strictest first:
      1. Normalized names are identical.
      2. Token Jaccard >= threshold (0.75 = 3 of 4 tokens shared), the first
         tokens agree, and the winner is unambiguous (no runner-up within 0.05).
    """
    n = normalize(raw_name)
    if not n:
        return None
    if n in org_keys:
        return Match(n, "exact", 1.0)
    nt = tokens(n)
    first = n.split()[0]
    scored = sorted(
        ((jaccard(nt, tokens(k)), k) for k in org_keys if k and k.split()[0] == first),
        reverse=True,
    )
    if not scored or scored[0][0] < threshold:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        return None
    return Match(scored[0][1], "token", round(scored[0][0], 3))
