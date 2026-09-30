"""Parse leading quantity + unit from a raw ingredient string.

RecipeNLG ingredient strings look like ``"1 c. firmly packed brown sugar"``,
``"3 1/2 c. rice biscuits"``, ``"2 Tbsp. butter or margarine"``, or
``"1 (8 oz.) pkg. cream cheese"``. This module extracts the numeric amount and a
canonical unit, returning ``(None, None)`` when no parseable quantity exists
(e.g. ``"to taste"``, ``"1 can soup"`` counts as amount-only).
"""

from __future__ import annotations

import re

# RecipeNLG's ingredient strings sometimes lose the slash in a leading
# fraction: "1/4 cup" appears as "14 cup", "1/2 teaspoon" as "12 teaspoon",
# "3/4 cup" as "34 cup". Reconstruction table + the units it applies to
# (weight units like oz/g are left alone — "12 oz" is a real amount).
_MANGLED_FRACTIONS: dict[str, tuple[int, int]] = {
    "12": (1, 2), "13": (1, 3), "14": (1, 4), "18": (1, 8),
    "23": (2, 3), "34": (3, 4), "38": (3, 8),
    "58": (5, 8), "78": (7, 8), "116": (1, 16),
}
_RECONSTRUCT_UNITS = frozenset({"cup", "tbsp", "tsp", "pt", "qt", "gal", "lb"})

# Plausibility window for un-mangling a bare number into a fraction.
_MANGLE_PLAUSIBLE_MIN = 10
_MANGLE_PLAUSIBLE_MAX = 999

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
    r"|pinch(?:es)?|dash(?:es)?"
    r"|cups?|c"
    r"|cans?|jars?"
)

_AMOUNT_UNIT_RE = re.compile(
    r"\A\s*(?P<num>" + _NUMBER + r")\s*(?P<unit>" + _UNIT + r")?\b",
    re.IGNORECASE,
)

# "2 (16 oz.) pkg." -> 2 * 16 oz; "1 (8 oz.) pkg. cream cheese" -> 8 oz.
# The size may be a mangled fraction ("10 5/8 g" for "10 5/8 oz").
_PACKAGE_RE = re.compile(
    r"\A\s*(?P<count>\d+(?:\.\d+)?)\s*\(\s*(?P<size>" + _NUMBER + r")\s*"
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
    "pinch": "pinch", "pinches": "pinch",
    "dash": "dash", "dashes": "dash",
    "pkg": "pkg", "package": "pkg", "packages": "pkg", "packet": "pkg", "packets": "pkg",
    "envelope": "envelope", "envelopes": "envelope",
    "can": "can", "cans": "can",
    "jar": "jar", "jars": "jar",
    "container": "container", "containers": "container",
}

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


# Quantity ranges: "2 -3 cups", "1 1/2 - 2 cups", "1 to 2 cups". The range's
# second number and the unit would otherwise leak into the ingredient head.
_RANGE_RE = re.compile(
    r"\A\s*(?P<a>" + _NUMBER + r")\s*(?:-|–|—|to)\s*(?P<b>" + _NUMBER + r")"
    r"\s*(?P<unit>" + _UNIT + r")?\b",
    re.IGNORECASE,
)


def _unmangle(value: float) -> float | None:
    """Undo a mangled fraction ("12" -> 0.5, "34" -> 0.75) when plausible."""
    if value != int(value) or not (
        _MANGLE_PLAUSIBLE_MIN <= value <= _MANGLE_PLAUSIBLE_MAX
    ):
        return None
    frac = _MANGLED_FRACTIONS.get(str(int(value)))
    if frac is None:
        return None
    return frac[0] / frac[1]


def _range_values(a: float, b: float) -> tuple[float, float]:
    """Choose the ascending interpretation of a possibly-mangled pair.

    RecipeNLG drops slashes in fractions, so "1/4 - 1/2 cup" reaches us as
    "14-12 cup" and "3/8 - 3/4 cup" as "38-34 cup". Both numbers may need
    un-mangling; prefer the interpretation that makes the pair ascending.
    """
    if a <= b:
        # "34-38 cup" can be a mangled "3/4 - 3/8 cup": when BOTH numbers map
        # to plausible cooking fractions, they are mangled (a raw 34-38 range
        # of cups is absurd), so un-mangle both.
        ua = _unmangle(a)
        ub = _unmangle(b)
        if ua is not None and ub is not None:
            return min(ua, ub), max(ua, ub)
        return a, b
    ua = _unmangle(a)
    ub = _unmangle(b)
    candidates: list[tuple[float, float]] = []
    if ua is not None and ub is not None:
        candidates.append((ua, ub))
    if ua is not None:
        candidates.append((ua, b))
    if ub is not None:
        candidates.append((a, ub))
    for x, y in candidates:
        if x <= y:
            return x, y
    return b, b


def _parse_range(s: str) -> tuple[float, float, str | None, int] | None:
    """Match a leading range "1 1/2 - 2 cups"; return (low, high, unit, end)."""
    m = _RANGE_RE.match(s)
    if not m:
        return None
    a = _parse_number(m.group("a"))
    b = _parse_number(m.group("b"))
    if a is None or b is None:
        return None
    a, b = _range_values(a, b)
    return min(a, b), max(a, b), _canon(m.group("unit")), m.end()

_MANGLED_FRACTION_RE = re.compile(r"\A\s*(\d{2,3})\s+([A-Za-z]+)\.?")
_MANGLED_MIXED_RE = re.compile(r"\A\s*(\d+)\s+(\d{2,3})\s+([A-Za-z]+)\.?")


def _normalize_mangled_fraction(s: str) -> str:
    """Rewrite a mangled fraction ("14 cup" -> "1/4 cup", "1 23 cups" -> "1 2/3 cups")."""
    # Mixed number first: "1 23 cups" -> "1 2/3 cups".
    m = _MANGLED_MIXED_RE.match(s)
    if m:
        frac = _MANGLED_FRACTIONS.get(m.group(2))
        if frac is not None and _canon(m.group(3)) in _RECONSTRUCT_UNITS:
            num, den = frac
            return f"{m.group(1)} {num}/{den} {m.group(3)}{s[m.end():]}"

    # Bare leading fraction: "14 cup" -> "1/4 cup".
    m = _MANGLED_FRACTION_RE.match(s)
    if m:
        frac = _MANGLED_FRACTIONS.get(m.group(1))
        if frac is not None and _canon(m.group(2)) in _RECONSTRUCT_UNITS:
            num, den = frac
            return f"{num}/{den} {m.group(2)}{s[m.end():]}"

    return s


def parse_amount_span(
    s: str | None,
) -> tuple[float | None, str | None, float | None, float | None]:
    """Return ``(amount, unit, low, high)`` for the leading quantity.

    ``amount`` is a float (fractions/mixed numbers resolved) — for a range
    (``"1 1/2 - 2 cups"``) it is the midpoint, and ``low``/``high`` carry the
    resolved endpoints (mangled fractions un-mangled: ``"14-12 cup"`` spans
    0.25–0.5). For a non-range quantity the span is ``None, None``. ``unit`` is
    a canonical key such as ``"cup"``, ``"tbsp"``, ``"oz"``, ``"g"``;
    ``amount`` and ``unit`` are both ``None`` when nothing parseable is
    present. A no-quantity phrase ("salt to taste") rejects the line only
    when NO amount parses — a quantified line with a trailing phrase
    (``"1 cup vegetable oil (for frying)"``) keeps its amount.
    """
    if not s:
        return None, None, None, None

    s = _strip_abbrev_periods(s.strip())
    s = _LEADING_WORDS.sub("", s)

    rng = _parse_range(s)
    if rng:
        low, high, unit, _ = rng
        return (low + high) / 2.0, unit, low, high

    s = _normalize_mangled_fraction(s)

    m = _PACKAGE_RE.match(s)
    if m:
        count = float(m.group("count"))
        size = _parse_number(m.group("size"))
        if size is None:
            size = 0.0
        return count * size, _canon(m.group("unit")), None, None

    m = _AMOUNT_UNIT_RE.match(s)
    if m:
        amount = _parse_number(m.group("num"))
        return amount, _canon(m.group("unit")), None, None

    # Nothing parseable — a genuine no-quantity line ("salt to taste") or
    # junk: no amount either way. The phrase tables only matter downstream
    # (props/head stripping), never for the amount.
    return None, None, None, None


def parse_ingredient_amount(s: str | None) -> tuple[float | None, str | None]:
    """Return ``(amount, canonical_unit)`` for the leading quantity."""
    amount, unit, _, _ = parse_amount_span(s)
    return amount, unit


def strip_amount(s: str | None) -> str:
    """Remove the leading quantity/unit, returning the remaining name text."""
    if not s:
        return ""
    # Un-mangle fractions ("1 12 cups oil") BEFORE matching, exactly like
    # parse_ingredient_amount — otherwise the amount parses correctly but the
    # name keeps the mangled digits ("12 cups oil").
    stripped = _normalize_mangled_fraction(_strip_abbrev_periods(s.strip()))
    rng = _parse_range(stripped)
    if rng:
        return stripped[rng[3]:].strip()
    m = _AMOUNT_UNIT_RE.match(stripped)
    if m:
        return stripped[m.end():].strip()
    return s.strip()
