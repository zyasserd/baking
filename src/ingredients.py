"""Decompose an ingredient head into the structural baking parts.

``decompose`` returns a *weight vector* over the tracked parts::

    {"flour": w, "sugar": w, "fat": w, "egg": w, "milk": w,
     "water": w, "salt": w, "leavener": w, "yeast": w}

whose entries sum to <= 1 (the remainder is "other" and is ignored). The weight
vector comes from **USDA FoodData Central (SR Legacy)** via ``src.reference``:
each ingredient's per-100 g proximate composition is mapped to parts (water ->
water, lipid -> fat, sugars -> sugar, starch -> flour, sodium -> salt). Pure
parts are pinned to their own part at weight 1.0 so the parts stay self-
consistent (flour *is* flour; butter *is* fat, per the book convention — its 16%
water is ignored).

Ingredients are either *base* (structural: flours, sugars, fats, eggs, dairy
liquids, water, juices, broths, syrups, leaveners, salt, yeast) or *add-ins*
(chocolate, cocoa, nuts, seeds, fruit, vegetables, cheese, condiments, meats).
``decompose(name, mode="full")`` returns the full vector; ``mode="structural"``
zeroes add-ins, reproducing Ruhlman's clean flour:liquid:egg:fat:sugar ratio.
"""

from __future__ import annotations

import re

from . import reference

PARTS = ["flour", "sugar", "fat", "egg", "milk", "water", "salt", "leavener", "yeast"]

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")

# Multi-word rules, checked first (highest specificity). Each entry is
# (word sequence, vector, role). Literal vectors are USDA-derived approximations
# for products the reference does not capture well.
_MULTI: list[tuple[tuple[str, ...], dict[str, float], str]] = [
    (("baking", "powder"), {"leavener": 1.0}, "base"),
    (("baking", "soda"), {"leavener": 1.0}, "base"),
    (("bicarbonate", "of", "soda"), {"leavener": 1.0}, "base"),
    (("corn", "meal"), {"flour": 1.0}, "base"),
    (("masa", "harina"), {"flour": 1.0}, "base"),
    (("cream", "of", "tartar"), {}, "addin"),
    (("peanut", "butter"), {"fat": 0.50, "sugar": 0.10}, "addin"),
    (("almond", "butter"), {"fat": 0.55, "sugar": 0.05}, "addin"),
    (("cashew", "butter"), {"fat": 0.50, "sugar": 0.05}, "addin"),
    (("milk", "chocolate"), {"sugar": 0.55, "fat": 0.30}, "addin"),
    (("white", "chocolate"), {"sugar": 0.60, "fat": 0.30}, "addin"),
    (("unsweetened", "chocolate"), {"fat": 0.55}, "addin"),
    (("baking", "chocolate"), {"fat": 0.53}, "addin"),
    (("bitter", "chocolate"), {"fat": 0.53}, "addin"),
    (("mascarpone",), {"fat": 0.44, "milk": 0.44}, "base"),
    (("mayonnaise",), {"fat": 0.75, "water": 0.20}, "addin"),
    (("breadcrumbs",), {"flour": 0.75}, "addin"),
    (("bread", "crumbs"), {"flour": 0.75}, "addin"),
    (("tomato", "soup"), {"water": 0.90, "sugar": 0.05}, "addin"),
    (("tomato", "paste"), {"water": 0.75, "sugar": 0.12}, "addin"),
    (("vanilla", "extract"), {}, "addin"),
    (("self", "rising", "flour"), {"flour": 0.92, "leavener": 0.055, "salt": 0.025}, "base"),
    (("self", "raising", "flour"), {"flour": 0.92, "leavener": 0.055, "salt": 0.025}, "base"),
    (("self", "rising", "cornmeal"), {"flour": 0.92, "leavener": 0.055, "salt": 0.025}, "base"),
    (("egg", "whites"), {"egg": 1.0}, "base"),
    (("egg", "white"), {"egg": 1.0}, "base"),
    (("egg", "yolks"), {"egg": 1.0}, "base"),
    (("egg", "yolk"), {"egg": 1.0}, "base"),
]

# Single-word pinned pure parts (all base), checked after multi-word rules.
_SINGLE: list[tuple[str, str]] = [
    ("flour", "flour"),
    ("cornmeal", "flour"),
    ("polenta", "flour"),
    ("masa", "flour"),
    ("semolina", "flour"),
    ("sugar", "sugar"),
    ("butter", "fat"),
    ("margarine", "fat"),
    ("shortening", "fat"),
    ("oil", "fat"),
    ("lard", "fat"),
    ("ghee", "fat"),
    ("suet", "fat"),
    ("egg", "egg"),
    ("eggs", "egg"),
    ("yolk", "egg"),
    ("milk", "milk"),
    ("buttermilk", "milk"),
    ("yogurt", "milk"),
    ("yoghurt", "milk"),
    ("water", "water"),
    ("salt", "salt"),
    ("yeast", "yeast"),
    ("starter", "yeast"),
    ("bicarbonate", "leavener"),
]

# Exact heads that must resolve through the reference *before* single-word
# pinning (e.g. "condensed milk" would otherwise match the "milk" pin and lose
# its sugar). All are structural bases.
_FDC_BASE_HEADS = frozenset({
    "cream cheese",
    "cottage cheese",
    "ricotta",
    "ricotta cheese",
    "sour cream",
    "heavy cream",
    "heavy whipping cream",
    "whipping cream",
    "light cream",
    "half and half",
    "evaporated milk",
    "condensed milk",
    "sweetened condensed milk",
    "coconut milk",
    "coconut cream",
})

# Exact heads whose reference match is wrong or missing. ``_ALIAS_HEADS``
# resolve through the reference under a better-matched name (bare "cream"
# fuzzy-matches a cheese-like entry, so it is resolved as heavy whipping
# cream — the standard meaning of "1 cup cream" in baking); ``_LITERAL_HEADS``
# carry hand-set USDA vectors (ice cream's reference match reports ~5% fat,
# which is a frozen-dairy-dessert entry, not ice cream).
_ALIAS_HEADS: dict[str, str] = {
    "cream": "heavy cream",
    "double cream": "heavy cream",
    "thickened cream": "heavy cream",
    "single cream": "light cream",
}

_ICE_CREAM: dict[str, float] = {"water": 0.56, "fat": 0.11, "sugar": 0.21}
_LITERAL_HEADS: dict[str, dict[str, float]] = {
    "ice cream": _ICE_CREAM,
    "vanilla ice cream": _ICE_CREAM,
    "chocolate ice cream": _ICE_CREAM,
}

# Words that mark an FDC-resolved ingredient as a structural base (liquid or
# sweetener) rather than an add-in.
_BASE_WORDS = frozenset({
    "milk", "cream", "yogurt", "yoghurt", "buttermilk", "juice", "broth",
    "stock", "wine", "coffee", "espresso", "tea", "cider", "beer", "syrup",
    "honey", "molasses", "treacle", "agave",
})


def _words(name: str) -> list[str]:
    return _WORD_SPLIT.split(name.lower())


def _contains_seq(words: list[str], seq: tuple[str, ...]) -> bool:
    n = len(seq)
    if n == 0:
        return False
    for i in range(len(words) - n + 1):
        if tuple(words[i : i + n]) == seq:
            return True
    return False


def _resolve(name: str) -> tuple[dict[str, float], str]:
    """Return ``(vector, role)`` for an ingredient head."""
    if not name:
        return {}, "other"

    lowered = name.lower()

    if " or " in lowered:
        for arm in lowered.split(" or "):
            vec, role = _resolve(arm.strip())
            if vec or role != "other":
                return vec, role
        return {}, "other"

    words = _words(lowered)

    for seq, vec, role in _MULTI:
        if _contains_seq(words, seq):
            return dict(vec), role

    if lowered in _FDC_BASE_HEADS:
        vec = reference.fdc_compose(lowered)
        if vec:
            return vec, "base"

    if lowered in _ALIAS_HEADS:
        vec = reference.fdc_compose(_ALIAS_HEADS[lowered])
        if vec:
            return vec, "base"

    if lowered in _LITERAL_HEADS:
        return dict(_LITERAL_HEADS[lowered]), "base"

    word_set = set(words)
    for word, part in _SINGLE:
        if word in word_set:
            return {part: 1.0}, "base"

    vec = reference.fdc_compose(lowered)
    if vec:
        role = "base" if any(w in _BASE_WORDS for w in word_set) else "addin"
        return vec, role

    return {}, "other"


def decompose(name: str, mode: str = "full") -> dict[str, float]:
    """Return the part weight vector for an ingredient head.

    ``mode="structural"`` zeroes add-ins (flavor/enrichment additions), leaving
    only the base structural parts, as in Ruhlman's *Ratio*.
    """
    vec, role = _resolve(name)
    if mode == "structural" and role == "addin":
        return {}
    return vec


def role(name: str) -> str:
    """Return the ingredient's role: ``"base"``, ``"addin"``, or ``"other"``."""
    return _resolve(name)[1]


def classify(name: str) -> str:
    """Return the dominant part for an ingredient head, or ``"other"``.

    Kept as a convenience (and for the density lookup); ``decompose`` is the
    authoritative mapping.
    """
    vec = decompose(name)
    if not vec:
        return "other"
    return max(vec, key=vec.get)
