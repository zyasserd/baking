"""Parse leading quantity + unit from a raw ingredient string.

RecipeNLG ingredient strings look like ``"1 c. firmly packed brown sugar"``,
``"3 1/2 c. rice biscuits"``, ``"2 Tbsp. butter or margarine"``, or
``"1 (8 oz.) pkg. cream cheese"``. This module extracts the numeric amount and a
canonical unit, returning ``(None, None)`` when no parseable quantity exists
(e.g. ``"to taste"``, ``"1 can soup"`` counts as amount-only).
"""

from __future__ import annotations

import re

_NUMBER = r"(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+\.\d+|\d+)"

_UNIT = (
    r"tablespoons?|tbsps?|tbsp|tbs"
    r"|teaspoons?|tsps?|tsp|ts"
    r"|milliliters?|mls?"
    r"|kilograms?|kgs?"
    r"|packages?|pkgs?|packets?"
    r"|ounces?|oz"
    r"|pounds?|lbs?|lb"
    r"|liters?|litres?|l"
    r"|gallons?|gals?"
    r"|containers?"
    r"|envelopes?"
    r"|pints?|pts?"
    r"|quarts?|qts?"
    r"|sticks?"
    r"|grams?|g"
    r"|cups?|c"
    r"|cans?|jars?"
)

_AMOUNT_UNIT_RE = re.compile(
    r"\A\s*(?P<num>" + _NUMBER + r")\s*(?P<unit>" + _UNIT + r")?\b",
    re.IGNORECASE,
)

# "2 (16 oz.) pkg." -> 2 * 16 oz; "1 (8 oz.) pkg. cream cheese" -> 8 oz.
_PACKAGE_RE = re.compile(
    r"\A\s*(?P<count>\d+(?:\.\d+)?)\s*\(\s*(?P<size>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>oz|ounce|ounces|g|gram|grams|lb|pound|pounds)\s*\)",
    re.IGNORECASE,
)

_UNIT_CANON = {
    "cup": "cup", "cups": "cup", "c": "cup",
    "tbsp": "tbsp", "tbs": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "ts": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "pt": "pt", "pint": "pt", "pints": "pt",
    "qt": "qt", "quart": "qt", "quarts": "qt",
    "gal": "gal", "gallon": "gal", "gallons": "gal",
    "stick": "stick", "sticks": "stick",
    "pkg": "pkg", "package": "pkg", "packages": "pkg", "packet": "pkg", "packets": "pkg",
    "envelope": "envelope", "envelopes": "envelope",
    "can": "can", "cans": "can",
    "jar": "jar", "jars": "jar",
    "container": "container", "containers": "container",
}

_NO_QUANTITY_PHRASES = (
    "to taste",
    "as needed",
    "as required",
    "for frying",
    "for dusting",
    "for greasing",
)

_LEADING_WORDS = re.compile(
    r"\A(?:about|approx\.?|approximately|around|scant|generous|heaping|level)\s+",
    re.IGNORECASE,
)


def _strip_abbrev_periods(s: str) -> str:
    # "Tbsp." -> "Tbsp", "c." -> "c", but leave "1.5" and "1/2" untouched.
    return re.sub(r"(?<=[a-zA-Z])\.", " ", s)


def _parse_number(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    m = re.fullmatch(r"(\d+)\s+(\d+)\s*/\s*(\d+)", token)
    if m:
        return float(int(m.group(1))) + int(m.group(2)) / int(m.group(3))
    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", token)
    if m:
        return int(m.group(1)) / int(m.group(2))
    m = re.fullmatch(r"\d+\.\d+", token)
    if m:
        return float(token)
    m = re.fullmatch(r"\d+", token)
    if m:
        return float(token)
    return None


def _canon(unit: str | None) -> str | None:
    if not unit:
        return None
    unit = unit.lower().strip()
    return _UNIT_CANON.get(unit)


# RecipeNLG's ingredient strings sometimes lose the slash in a leading
# fraction: "1/4 cup" appears as "14 cup", "1/2 teaspoon" as "12 teaspoon",
# "3/4 cup" as "34 cup". Reconstruct the fraction when the mangled 2/3-digit
# token maps to a standard cooking fraction *and* is followed by an imperial
# volume unit (or pound). Weight units (oz/g/ml) are left alone because whole
# amounts like "12 oz" and "16 oz" are real and common there.
_FRACTION_MANGLE: dict[str, tuple[int, int]] = {
    "12": (1, 2), "13": (1, 3), "14": (1, 4), "18": (1, 8),
    "23": (2, 3), "34": (3, 4), "38": (3, 8),
    "58": (5, 8), "78": (7, 8), "116": (1, 16),
}

_RECONSTRUCT_UNITS = frozenset({"cup", "tbsp", "tsp", "pt", "qt", "gal", "lb"})

_MANGLED_FRACTION_RE = re.compile(r"\A\s*(\d{2,3})\s+([A-Za-z]+)\.?")
_MANGLED_MIXED_RE = re.compile(r"\A\s*(\d+)\s+(\d{2,3})\s+([A-Za-z]+)\.?")


def _normalize_mangled_fraction(s: str) -> str:
    """Rewrite a mangled fraction ("14 cup" -> "1/4 cup", "1 23 cups" -> "1 2/3 cups")."""
    # Mixed number first: "1 23 cups" -> "1 2/3 cups".
    m = _MANGLED_MIXED_RE.match(s)
    if m:
        frac = _FRACTION_MANGLE.get(m.group(2))
        if frac is not None and _canon(m.group(3)) in _RECONSTRUCT_UNITS:
            num, den = frac
            return f"{m.group(1)} {num}/{den} {m.group(3)}{s[m.end():]}"

    # Bare leading fraction: "14 cup" -> "1/4 cup".
    m = _MANGLED_FRACTION_RE.match(s)
    if m:
        frac = _FRACTION_MANGLE.get(m.group(1))
        if frac is not None and _canon(m.group(2)) in _RECONSTRUCT_UNITS:
            num, den = frac
            return f"{num}/{den} {m.group(2)}{s[m.end():]}"

    return s


def parse_ingredient_amount(s: str | None) -> tuple[float | None, str | None]:
    """Return ``(amount, canonical_unit)`` for the leading quantity.

    ``amount`` is a float (fractions/mixed numbers resolved); ``unit`` is a
    canonical key such as ``"cup"``, ``"tbsp"``, ``"oz"``, ``"g"``. Both are
    ``None`` when nothing parseable is present.
    """
    if not s:
        return None, None

    s = _strip_abbrev_periods(s.strip())

    lowered = s.lower()
    if any(phrase in lowered for phrase in _NO_QUANTITY_PHRASES):
        return None, None

    s = _LEADING_WORDS.sub("", s)

    s = _normalize_mangled_fraction(s)

    m = _PACKAGE_RE.match(s)
    if m:
        count = float(m.group("count"))
        size = float(m.group("size"))
        unit = _canon(m.group("unit"))
        return count * size, unit

    m = _AMOUNT_UNIT_RE.match(s)
    if not m:
        return None, None

    amount = _parse_number(m.group("num"))
    unit = _canon(m.group("unit"))
    return amount, unit


def strip_amount(s: str | None) -> str:
    """Remove the leading quantity/unit, returning the remaining name text."""
    if not s:
        return ""
    stripped = _strip_abbrev_periods(s.strip())
    m = _AMOUNT_UNIT_RE.match(stripped)
    if m:
        return stripped[m.end():].strip()
    return s.strip()
