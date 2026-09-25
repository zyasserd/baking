"""USDA FoodData Central (SR Legacy) reference for ingredient composition.

This module is the *reference* behind ``src.preprocess.ingredients``: instead of
hand-tuned numbers, an ingredient's weight vector into the baking parts comes
from USDA's proximate composition (per 100 g). ``src/preprocess/fdc.py`` builds
the backing CSV (``config.FDC_REFERENCE_CSV``) from the flake-staged SR Legacy
tables; this module loads it, maps a cleaned ingredient head to a food, and
converts its nutrients to a part vector.

Nutrient -> part transform (documented, tunable — see config FDC section):

    water   -> ``water``
    lipid   -> ``fat``
    sugars  -> ``sugar``
    starch  -> ``flour``   (carb - sugar - fiber), *only* for grain/legume/
                             vegetable/starch food categories
    sodium  -> ``salt``    (Na x 2.5, as NaCl)
    protein, fiber, ash, and any starch from non-starch categories -> "other"
                                                                     (ignored)

The ``flour`` part is deliberately restricted to starchy food categories so
that e.g. cocoa or dried fruit do not leak into "flour" through their
carbohydrate. Pure parts (flour, sugar, butter, egg, milk, water, ...) are
*pinned* to their own part in ``src.preprocess.ingredients`` and never reach
this module.
"""

from __future__ import annotations

import csv
import os
import re
from functools import lru_cache

import config

_CURATED = config.FDC_CURATED
_STARCH_CATEGORIES = config.FDC_STARCH_CATEGORIES

# Stopwords dropped from both heads and FDC descriptions when matching.
_STOP = frozenset({
    "the", "a", "an", "of", "and", "or", "with", "for", "in", "on", "as",
    "raw", "canned", "fresh", "frozen", "dried", "cooked", "plain", "generic",
    "salted", "unsalted", "regular", "prepared", "ready", "to", "made", "from",
    "all", "purpose", "style", "nonfat", "low", "reduced", "light", "heavy",
    "whole", "without", "added", "uncooked", "unprepared", "household",
})

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    out = []
    for w in _WORD_RE.findall(text.lower()):
        if w in _STOP or w.isdigit() or len(w) < 2:
            continue
        out.append(w)
    return out


def _variants(tokens: list[str]) -> set[str]:
    """Tokens plus naive singulars, for fuzzy matching."""
    out = set(tokens)
    for w in tokens:
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and not w.endswith("us"):
            out.add(w[:-1])
    return out


class _Reference:
    """Lazily loaded SR Legacy table with a fuzzy-matching index."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._by_id: dict[int, dict] = {}
        self._descriptions: list[tuple[int, str]] = []
        self._postings: dict[str, list[int]] = {}
        self._desc_tokens: dict[int, set[str]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        with open(self.path, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                fid = int(row["fdc_id"])
                self._by_id[fid] = row
                self._descriptions.append((fid, row["description"]))
                toks = _variants(_tokens(row["description"]))
                self._desc_tokens[fid] = toks
                for t in toks:
                    self._postings.setdefault(t, []).append(fid)
        self._loaded = True

    def composition(self, fdc_id: int) -> dict[str, float] | None:
        row = self._by_id.get(fdc_id)
        if row is None:
            return None
        return nutrient_to_parts(row)

    def fuzzy(self, head: str) -> dict[str, float] | None:
        self._load()
        tok_set = _variants(_tokens(head))
        if not tok_set:
            return None

        # Candidate collection iterates tokens in sorted order (Python
        # randomizes string hashing per process, so raw set order would make
        # the candidate cap — and thus the chosen match — flip between runs).
        candidates: set[int] = set()
        for t in sorted(tok_set):
            for fid in self._postings.get(t, ()):
                candidates.add(fid)
                if len(candidates) > config.FDC_FUZZY_CANDIDATE_CAP:
                    break
            if len(candidates) > config.FDC_FUZZY_CANDIDATE_CAP:
                break

        best_fid = None
        best_score = 0.0
        for fid in candidates:
            f = self._desc_tokens[fid]
            inter = len(tok_set & f)
            if inter == 0:
                continue
            union = len(tok_set | f)
            score = inter / union
            # Prefer descriptions whose tokens are a subset (more generic).
            if f <= tok_set:
                score += config.FDC_FUZZY_SUBSET_BONUS
            if score > best_score:
                best_score = score
                best_fid = fid

        if best_fid is None or best_score < config.FDC_FUZZY_MIN_SCORE:
            return None
        return self.composition(best_fid)


_REF: _Reference | None = None


def get_reference() -> _Reference:
    global _REF
    if _REF is None:
        _REF = _Reference(config.FDC_REFERENCE_CSV)
        _REF._load()
    return _REF


def nutrient_to_parts(row: dict) -> dict[str, float]:
    """Convert an FDC nutrient row (per 100 g) to a part weight vector."""
    water = float(row["water_g"])
    fat = float(row["fat_g"])
    sugar = float(row["sugar_g"])
    carb = float(row["carb_g"])
    fiber = float(row["fiber_g"])
    sodium = float(row["sodium_mg"])
    category = row.get("category", "")

    starch = max(carb - sugar - fiber, 0.0)

    vec = {
        "water": water / 100.0,
        "fat": fat / 100.0,
        "sugar": sugar / 100.0,
        "salt": sodium * config.FDC_SODIUM_TO_SALT / 100000.0,
    }
    if category in config.FDC_STARCH_CATEGORIES:
        vec["flour"] = starch / 100.0

    vec = {k: v for k, v in vec.items() if v > config.FDC_TRACE_CUTOFF}
    return vec


@lru_cache(maxsize=None)
def fdc_compose(head: str) -> dict[str, float] | None:
    """Return the FDC-derived part vector for a head, or ``None`` if unmatched."""
    ref = get_reference()
    fid = config.FDC_CURATED.get(head)
    if fid is not None:
        return ref.composition(fid)
    return ref.fuzzy(head)