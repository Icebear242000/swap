"""Parse package sizes like '4.8 oz (136 g)' or '75 ml' into ounces."""

from __future__ import annotations

import re

GRAMS_PER_OZ = 28.349523125
ML_PER_FL_OZ = 29.5735295625

_QTY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(fl\.?\s*oz|oz|g|gr|grams?|ml|mL)\b", re.IGNORECASE)


def parse_ounces(text: str | None) -> tuple[float, str] | None:
    """Return (ounces, 'oz' | 'fl oz'), preferring a stated ounce figure."""
    if not text:
        return None
    found = [
        (float(n.replace(",", ".")), u.lower().replace(".", "").replace(" ", ""))
        for n, u in _QTY.findall(text)
    ]
    if not found:
        return None
    for value, unit in found:
        if unit == "floz":
            return round(value, 3), "fl oz"
        if unit == "oz":
            return round(value, 3), "oz"
    value, unit = found[0]
    if unit.startswith("g"):
        return round(value / GRAMS_PER_OZ, 3), "oz"
    if unit == "ml":
        return round(value / ML_PER_FL_OZ, 3), "fl oz"
    return None
