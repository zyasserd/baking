"""Decompose an ingredient head into tracked baking parts.

The shipped decomposition is the *structural* one: ``decompose`` returns a
weight vector over the tracked parts (see ``config.INGREDIENT_PARTS``)::

    {"flour": w, "sugar": w, "fat": w, "egg": w, "milk": w,
     "water": w, "salt": w, "leavener": w, "yeast": w}

whose entries sum to <= 1 (the remainder is "other" and is ignored). Add-ins
(chocolate, nuts, fruit, cheese, ...) are zeroed — they are flavor and
enrichment, not structure, and are excluded from the ratio as in Ruhlman's
*Ratio* (validated: the add-in-excluding decomposition classifies measurably
better than pooled add-ins, ARI 0.207 vs 0.176 — see the README).

The weights come from **USDA FoodData Central (SR Legacy)** via
``src.preprocess.reference``: each ingredient's per-100 g proximate composition
is mapped to parts (water -> water, lipid -> fat, sugars -> sugar, starch ->
flour, sodium -> salt). Pure parts are pinned to their own part at weight 1.0
so the parts stay self-consistent (flour *is* flour; butter *is* fat, per the
book convention — its 16% water is ignored).

Ingredients are either *base* (structural: flours, sugars, fats, eggs, dairy
liquids, water, juices, broths, syrups, leaveners, salt, yeast) or *add-ins*
(chocolate, cocoa, nuts, seeds, fruit, vegetables, cheese, condiments, meats).
``resolve`` returns the full ``(vector, role)`` pair — used internally to pick
each ingredient's primary part for the density lookup — while ``decompose`` is
the public structural mapping (add-ins zeroed).
"""

from __future__ import annotations

import re

import config

from . import reference

_MULTI = config.INGREDIENT_MULTI_RULES
_SINGLE = config.INGREDIENT_SINGLE_PINS
_FDC_BASE_HEADS = config.INGREDIENT_FDC_BASE_HEADS
_ALIAS_HEADS = config.INGREDIENT_ALIAS_HEADS
_LITERAL_HEADS = config.INGREDIENT_LITERAL_HEADS
_BASE_WORDS = config.INGREDIENT_BASE_WORDS

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


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


def resolve(name: str) -> tuple[dict[str, float], str]:
    """Return the full ``(vector, role)`` for an ingredient head.

    The vector is the full USDA-derived part weights (add-ins included);
    ``role`` is ``"base"`` (structural), ``"addin"`` (flavor/enrichment), or
    ``"other"`` (unresolved).
    """
    if not name:
        return {}, "other"

    lowered = name.lower()

    if " or " in lowered:
        for arm in lowered.split(" or "):
            vec, role = resolve(arm.strip())
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


def decompose(name: str) -> dict[str, float]:
    """Return the STRUCTURAL part weight vector for an ingredient head.

    Add-ins (``role == "addin"``) are zeroed — they never enter the ratio.
    Use ``resolve`` for the full vector and the ingredient's role.
    """
    vec, role = resolve(name)
    if role == "addin":
        return {}
    return vec


def primary_part(vec: dict[str, float]) -> str:
    """Return the dominant part of a resolved vector, or ``"other"``.

    Used to pick the density category for gram conversion.
    """
    if not vec:
        return "other"
    return max(vec, key=vec.get)