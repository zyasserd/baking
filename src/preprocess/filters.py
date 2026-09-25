"""From-scratch / baked-goods filters for the ratio experiment.

The experiment asks whether the base ratio (flour, liquid, egg, fat, sugar)
determines the kind of baked good. That only holds for from-scratch, oven-baked
items: a prepared ingredient (dough, mix, pastry sheet) hides its flour/fat/sugar,
so its parsed grams are meaningless, and no-bake / topping recipes are not baked
goods. ``is_excluded`` returns True for recipes that must be dropped.

The keyword tables are parameters — see the FILTERS section of ``config``.
"""

from __future__ import annotations

import re

import config

_PREPARED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE) for p in config.PREPARED_INGREDIENT_PATTERNS
)


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


def is_excluded(title: str, ingredients: list[str]) -> bool:
    """Return True when a recipe is not a from-scratch baked good."""
    if _has_any(title, config.NO_BAKE_TITLE_KEYWORDS):
        return True

    for ing in ingredients:
        if _has_any(ing, config.PREPARED_INGREDIENT_KEYWORDS):
            return True
        if any(p.search(ing) for p in _PREPARED_PATTERNS):
            return True

    if _has_any(title, config.TOPPING_TITLE_KEYWORDS) and not _has_any(
        title, config.TOPPING_CONTAINER_KEYWORDS
    ):
        return True

    return False