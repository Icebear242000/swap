"""Preferences, gating and ranking of alternatives."""

from __future__ import annotations

from dataclasses import dataclass, field

from swap.checkpoints import BY_ID, FAIL, PASS, UNKNOWN, Result

IMPORTANCE = {"off": 0, "low": 1, "medium": 2, "high": 3}
# An unknown counts for less than a pass: we can't reward what we can't verify.
STATUS_VALUE = {PASS: 1.0, UNKNOWN: 0.4, FAIL: 0.0}


@dataclass
class Prefs:
    required: set[str] = field(default_factory=lambda: {"fights_cavities", "ingredients"})
    importance: dict[str, str] = field(
        default_factory=lambda: {
            "fights_cavities": "high",
            "ingredients": "high",
            "workers": "medium",
            "environment": "medium",
        }
    )
    # Opt-in: being owned by the same company isn't a failing, but some people want to
    # move their money away from a particular company.
    hide_same_owner: bool = False

    @classmethod
    def parse(cls, required: str | None, importance: str | None, hide_same_owner: bool) -> Prefs:
        p = cls()
        if required is not None:
            p.required = {r for r in required.split(",") if r in BY_ID}
        if importance:
            for pair in importance.split(","):
                cid, _, level = pair.partition(":")
                if cid in BY_ID and level in IMPORTANCE:
                    p.importance[cid] = level
        p.hide_same_owner = hide_same_owner
        return p


def score(results: list[Result], prefs: Prefs) -> float:
    total = weight_sum = 0.0
    for r in results:
        w = IMPORTANCE.get(prefs.importance.get(r.id, "medium"), 2)
        total += w * STATUS_VALUE[r.status]
        weight_sum += w
    return round(total / weight_sum, 3) if weight_sum else 0.0


def gate(results: list[Result], prefs: Prefs) -> list[str]:
    """Reasons this product should be hidden, empty if it passes every required checkpoint."""
    return [
        f"Fails \u201c{r.label}\u201d: {r.summary}"
        for r in results
        if r.id in prefs.required and r.status == FAIL
    ]


def unverified(results: list[Result], prefs: Prefs) -> list[str]:
    return [r.label for r in results if r.id in prefs.required and r.status == UNKNOWN]
