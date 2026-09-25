"""Convert parsed (amount, unit) into grams for a given ingredient.

Weight units convert directly; volume units go through a per-category grams-per-
cup density; eggs are count-based (one large egg = 50 g). Containers
(``can``/``jar``/``pkg``/``container``) use name-aware default net weights (see
``config.CONTAINER_OVERRIDES``), or a parenthetical size hint when one is
present.

All numeric parameters live in ``config`` (DENSITY section).
"""

from __future__ import annotations

import re

import config

WEIGHT_UNIT_GRAMS = config.WEIGHT_UNIT_GRAMS
VOLUME_UNIT_CUPS = config.VOLUME_UNIT_CUPS

_SIZE_HINT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(oz|ounce|ounces|g|gram|grams|lb|pound|pounds)", re.IGNORECASE)


def grams_per_cup(category: str, name: str = "") -> float:
    """Per-cup density, refined first by ingredient name then by category."""
    n = name.lower()

    # Name-first densities for ingredients whose split is non-trivial (dairy,
    # syrups, chocolate, moist produce). Checked before the category defaults.
    for key, density in config.NAME_DENSITY.items():
        if key in n:
            return density

    if category == "sugar":
        if "brown" in n:
            return config.SUGAR_DENSITY_BROWN
        if "powdered" in n or "confectioner" in n or "icing" in n:
            return config.SUGAR_DENSITY_POWDERED
        return config.SUGAR_DENSITY_DEFAULT
    if category == "fat":
        return config.FAT_DENSITY_OIL if "oil" in n else config.FAT_DENSITY_DEFAULT
    if category == "flour":
        if "whole wheat" in n or "wholemeal" in n:
            return config.FLOUR_DENSITY_WHOLE_WHEAT
        if "cake" in n:
            return config.FLOUR_DENSITY_CAKE
        if "bread" in n:
            return config.FLOUR_DENSITY_BREAD
        if "corn" in n or "masa" in n or "polenta" in n:
            return config.FLOUR_DENSITY_CORN
        return config.FLOUR_DENSITY_DEFAULT
    return config.DEFAULT_GRAMS_PER_CUP.get(category, config.FALLBACK_GRAMS_PER_CUP)


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
            return value * config.WEIGHT_UNIT_GRAMS.get(u[:2], 1.0)

    for u, sub, grams in config.CONTAINER_OVERRIDES:
        if u == unit and sub in n:
            return grams

    return config.CONTAINER_DEFAULTS.get(unit)


def to_grams(
    category: str,
    amount: float | None,
    unit: str | None,
    name: str = "",
    note: str | None = None,
) -> float | None:
    """Return grams, or ``None`` if the quantity cannot be converted."""
    if amount is None:
        return egg_grams(name) if category == "egg" else None

    if unit is None:
        return amount * egg_grams(name) if category == "egg" else None

    unit = unit.lower()

    if unit in config.WEIGHT_UNIT_GRAMS:
        return amount * config.WEIGHT_UNIT_GRAMS[unit]

    if unit in config.VOLUME_UNIT_CUPS:
        return amount * config.VOLUME_UNIT_CUPS[unit] * grams_per_cup(category, name)

    if unit == "stick":
        return amount * config.STICK_OF_BUTTER_GRAMS if category == "fat" else None

    if unit == "envelope" and category == "yeast":
        return amount * config.YEAST_PACKET_GRAMS

    if unit in ("can", "jar", "pkg", "container"):
        per = container_grams(unit, name, note)
        if per is not None:
            return amount * per

    return None