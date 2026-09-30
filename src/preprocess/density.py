"""Convert parsed (amount, unit) into grams for a given ingredient.

Weight units convert directly; volume units go through a per-category grams-per-
cup density; eggs are count-based (one large egg = 50 g). Containers
(``can``/``jar``/``pkg``/``container``) use name-aware default net weights (see
``_CONTAINER_OVERRIDES``), or a parenthetical size hint when one is
present.

All numeric assumptions (category densities, egg/stick/packet masses) live in
``config`` (DENSITY section); unit conversion factors and per-name lookup
tables live here.
"""

from __future__ import annotations

import re

import config

# Weight units, grams per unit.
WEIGHT_UNIT_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}

# Volume units, cups per unit.
VOLUME_UNIT_CUPS = {
    "cup": 1.0,
    "tbsp": 1.0 / 16.0,
    "tsp": 1.0 / 48.0,
    "ml": 1.0 / 236.588,
    "l": 1000.0 / 236.588,
    "pt": 2.0,
    "qt": 4.0,
    "gal": 16.0,
}

# Name-first grams-per-cup for ingredients whose mass is split across parts
# (dairy, syrups, chocolate, moist produce). Order matters: more specific
# substrings first; checked before the category defaults in ``config``.
_NAME_DENSITY: dict[str, float] = {
    "peanut butter": 258.0,
    "almond butter": 250.0,
    "cream cheese": 232.0,
    "cottage cheese": 226.0,
    "ricotta": 246.0,
    "mascarpone": 220.0,
    "sour cream": 230.0,
    "condensed milk": 306.0,
    "evaporated milk": 252.0,
    "ice cream": 148.0,
    "half and half": 242.0,
    "whipping cream": 238.0,
    "heavy cream": 238.0,
    "whipped cream": 120.0,
    "cream": 238.0,
    "coconut milk": 240.0,
    "honey": 340.0,
    "maple syrup": 315.0,
    "molasses": 330.0,
    "corn syrup": 330.0,
    "golden syrup": 330.0,
    "syrup": 330.0,
    "agave": 310.0,
    "chocolate": 170.0,
    "cocoa": 118.0,
    "pecan": 100.0,
    "walnut": 100.0,
    "almond": 100.0,
    "peanut": 130.0,
    "pumpkin": 245.0,
    "banana": 225.0,
    "applesauce": 245.0,
    "tomato": 245.0,
    "zucchini": 220.0,
    "carrot": 225.0,
    "raisins": 145.0,
    "dates": 175.0,
    "cranberries": 130.0,
    "coconut": 90.0,
    "oats": 80.0,
    "cornstarch": 128.0,
    "breadcrumbs": 100.0,
    "cheese": 110.0,
    "marshmallows": 60.0,
    "mayonnaise": 230.0,
    "ketchup": 240.0,
    "mustard": 250.0,
}

# Default net weights (grams) for container/package units with unknown mass.
# (unit, name-substring) -> grams, checked in order (most specific first).
_CONTAINER_OVERRIDES: list[tuple[str, str, float]] = [
    ("can", "tomato paste", 170.0),
    ("can", "tomato sauce", 425.0),
    ("can", "tomato", 411.0),
    ("can", "pumpkin", 425.0),
    ("can", "evaporated milk", 354.0),
    ("can", "condensed milk", 397.0),
    ("can", "beans", 439.0),
    ("can", "soup", 305.0),
    ("can", "coconut milk", 400.0),
    ("jar", "salsa", 454.0),
    ("jar", "spaghetti sauce", 680.0),
    ("jar", "pasta sauce", 680.0),
    ("jar", "peanut butter", 462.0),
    ("jar", "jam", 340.0),
    ("jar", "jelly", 340.0),
    ("jar", "preserves", 340.0),
    ("pkg", "cream cheese", 226.0),
    ("pkg", "gelatin", 7.0),
    ("pkg", "yeast", 7.0),
    ("container", "yogurt", 170.0),
    ("container", "sour cream", 454.0),
]

_CONTAINER_DEFAULTS = {
    "can": 400.0,
    "jar": 500.0,
}

_SIZE_HINT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(oz|ounce|ounces|g|gram|grams|lb|pound|pounds)", re.IGNORECASE)


def grams_per_cup(category: str, name: str = "") -> float:
    """Per-cup density, refined first by ingredient name then by category."""
    return grams_per_cup_with_basis(category, name)[0]


def grams_per_cup_with_basis(category: str, name: str = "") -> tuple[float, str]:
    """Per-cup density plus the basis it came from (``name|category|fallback``)."""
    n = name.lower()

    # Name-first densities for ingredients whose split is non-trivial (dairy,
    # syrups, chocolate, moist produce). Checked before the category defaults.
    for key, density in _NAME_DENSITY.items():
        if key in n:
            return density, "name"

    if category == "sugar":
        if "brown" in n:
            return config.SUGAR_DENSITY_BROWN, "name"
        if "powdered" in n or "confectioner" in n or "icing" in n:
            return config.SUGAR_DENSITY_POWDERED, "name"
        return config.SUGAR_DENSITY_DEFAULT, "category"
    if category == "fat":
        if "oil" in n:
            return config.FAT_DENSITY_OIL, "name"
        return config.FAT_DENSITY_DEFAULT, "category"
    if category == "flour":
        if "whole wheat" in n or "wholemeal" in n:
            return config.FLOUR_DENSITY_WHOLE_WHEAT, "name"
        if "cake" in n:
            return config.FLOUR_DENSITY_CAKE, "name"
        if "bread" in n:
            return config.FLOUR_DENSITY_BREAD, "name"
        if "corn" in n or "masa" in n or "polenta" in n:
            return config.FLOUR_DENSITY_CORN, "name"
        return config.FLOUR_DENSITY_DEFAULT, "category"
    gpc = config.DEFAULT_GRAMS_PER_CUP.get(category)
    if gpc is not None:
        return gpc, "category"
    return config.FALLBACK_GRAMS_PER_CUP, "fallback"


def egg_grams(name: str = "") -> float:
    n = name.lower()
    if "yolk" in n:
        return config.EGG_GRAMS["yolk"]
    if "white" in n:
        return config.EGG_GRAMS["white"]
    return config.EGG_GRAMS["whole"]


def container_grams(unit: str, name: str = "", note: str | None = None) -> float | None:
    """Net-weight guess for a container/package unit, or ``None`` if unknown.

    A parenthetical size hint (``"(14 oz.)"``) in ``note`` wins; otherwise a
    name-aware default is used, falling back to a per-unit default. ``pkg`` and
    ``container`` without a hint or a known name return ``None``.
    """
    n = (name or "").lower()

    if note:
        m = _SIZE_HINT_RE.search(note)
        if m:
            value = float(m.group(1))
            u = m.group(2).lower()
            return value * WEIGHT_UNIT_GRAMS.get(u[:2], 1.0)

    for u, sub, grams in _CONTAINER_OVERRIDES:
        if u == unit and sub in n:
            return grams

    return _CONTAINER_DEFAULTS.get(unit)


def to_grams(
    category: str,
    amount: float | None,
    unit: str | None,
    name: str = "",
    note: str | None = None,
) -> float | None:
    """Return grams, or ``None`` if the quantity cannot be converted."""
    return to_grams_with_basis(category, amount, unit, name, note)[0]


def to_grams_with_basis(
    category: str,
    amount: float | None,
    unit: str | None,
    name: str = "",
    note: str | None = None,
) -> tuple[float | None, str]:
    """Return ``(grams, basis)`` — how the mass was actually derived.

    ``basis`` names the conversion path (``weight``, ``volume:name``,
    ``volume:category``, ``volume:fallback``, ``egg``, ``stick``, ``envelope``,
    ``pinch``, ``dash``, ``package``, ``container``) — the data-quality
    fingerprint of the estimate; an empty basis means no conversion.
    """
    if amount is None:
        if category == "egg":
            return egg_grams(name), "egg"
        return None, ""

    if unit is None:
        if category == "egg":
            return amount * egg_grams(name), "egg"
        return None, ""

    unit = unit.lower()

    if unit in WEIGHT_UNIT_GRAMS:
        return amount * WEIGHT_UNIT_GRAMS[unit], "weight"

    if unit == "pinch":
        return amount * config.PINCH_GRAMS, "pinch"
    if unit == "dash":
        return amount * config.DASH_GRAMS, "dash"

    if unit in VOLUME_UNIT_CUPS:
        per, basis = grams_per_cup_with_basis(category, name)
        return amount * VOLUME_UNIT_CUPS[unit] * per, f"volume:{basis}"

    if unit == "stick":
        if category == "fat":
            return amount * config.STICK_OF_BUTTER_GRAMS, "stick"
        return None, ""

    if unit == "envelope" and category == "yeast":
        return amount * config.YEAST_PACKET_GRAMS, "envelope"

    if unit in ("can", "jar", "pkg", "container"):
        per = container_grams(unit, name, note)
        if per is not None:
            return amount * per, "package" if unit == "pkg" else "container"

    return None, ""