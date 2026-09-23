"""USDA FoodData Central (SR Legacy) reference for ingredient composition.

This module is the *reference* behind ``src.ingredients``: instead of hand-tuned
numbers, an ingredient's weight vector into the baking parts comes from USDA's
proximate composition (per 100 g). ``fetch_fdc.py`` builds the backing CSV
(``data/reference/fdc_srlegacy.csv``); this module loads it, maps a cleaned
ingredient head to a food, and converts its nutrients to a part vector.

Nutrient -> part transform (documented, tunable):

    water   -> ``water``
    lipid   -> ``fat``
    sugars  -> ``sugar``
    starch  -> ``flour``   (carb - sugar - fiber), *only* for grain/legume/
                             vegetable/starch food categories
    sodium  -> ``salt``    (Na x 2.5, as NaCl)
    protein, fiber, ash, and any starch from non-starch categories -> "other"
                                                                     (ignored)

The ``flour`` part is deliberately restricted to starchy food categories so that
e.g. cocoa or dried fruit do not leak into "flour" through their carbohydrate.
Pure parts (flour, sugar, butter, egg, milk, water, …) are *pinned* to their own
part in ``src.ingredients`` and never reach this module.
"""

from __future__ import annotations

import csv
import os
import re
from functools import lru_cache

# Food categories whose carbohydrate is treated as starch ("flour" part).
STARCH_CATEGORIES = frozenset({
    "Cereal Grains and Pasta",
    "Legumes and Legume Products",
    "Vegetables and Vegetable Products",
    "Breakfast Cereals",
    "Baked Products",
    "Snacks",
    "Meals, Entrees, and Side Dishes",
})

# Curated head -> SR Legacy fdc_id. Hand-checked against the USDA descriptions;
# the long tail is resolved by the fuzzy matcher below.
CURATED: dict[str, int] = {
    "cream cheese": 173418,
    "cottage cheese": 172179,
    "ricotta": 170851,
    "ricotta cheese": 170851,
    "sour cream": 171257,
    "yogurt": 171284,
    "yoghurt": 171284,
    "plain yogurt": 171284,
    "greek yogurt": 171284,
    "buttermilk": 170874,
    "heavy cream": 170859,
    "heavy whipping cream": 170859,
    "whipping cream": 170859,
    "light cream": 170857,
    "half and half": 171255,
    "whole milk": 171265,
    "evaporated milk": 171276,
    "condensed milk": 171275,
    "sweetened condensed milk": 171275,
    "honey": 169640,
    "maple syrup": 169661,
    "corn syrup": 168837,
    "dark corn syrup": 168836,
    "molasses": 168820,
    "golden syrup": 168837,
    "brown sugar": 168833,
    "powdered sugar": 169656,
    "confectioners sugar": 169656,
    "icing sugar": 169656,
    "granulated sugar": 169655,
    "white sugar": 169655,
    "caster sugar": 169655,
    "chocolate": 170271,
    "dark chocolate": 170273,
    "semisweet chocolate": 167976,
    "chocolate chips": 167976,
    "cocoa": 169593,
    "cocoa powder": 169593,
    "unsweetened cocoa": 169593,
    "dutch cocoa": 169593,
    "oats": 173904,
    "rolled oats": 173904,
    "quick oats": 173904,
    "old fashioned oats": 173904,
    "pecans": 169424,
    "pecan": 169424,
    "walnuts": 170186,
    "walnut": 170186,
    "almonds": 170158,
    "almond": 170158,
    "raisins": 168165,
    "raisin": 168165,
    "dates": 171726,
    "dried cranberries": 171723,
    "cranberries": 171723,
    "coconut": 170170,
    "unsweetened coconut": 170170,
    "shredded coconut": 170170,
    "banana": 173944,
    "bananas": 173944,
    "pumpkin": 168450,
    "canned pumpkin": 168450,
    "pumpkin puree": 168450,
    "carrot": 168568,
    "carrots": 168568,
    "zucchini": 168469,
    "applesauce": 167772,
    "lemon juice": 167747,
    "lime juice": 167747,
    "orange juice": 169098,
    "tomato sauce": 169074,
    "mustard": 172234,
    "dijon mustard": 172234,
    "yellow mustard": 172234,
    "ketchup": 168556,
    "catsup": 168556,
    "soy sauce": 172473,
    "worcestershire sauce": 171610,
    "worcestershire": 171610,
    "vinegar": 172237,
    "distilled vinegar": 172237,
    "white vinegar": 172237,
    "balsamic vinegar": 172237,
    "cider vinegar": 172237,
    "red wine vinegar": 172237,
    "rice vinegar": 172237,
    "chicken broth": 171542,
    "chicken stock": 171542,
    "beef broth": 171542,
    "beef stock": 171542,
    "vegetable broth": 171542,
    "wine": 171872,
    "red wine": 171872,
    "white wine": 171872,
    "beer": 168746,
    "coffee": 171881,
    "cornstarch": 169698,
    "corn starch": 169698,
    "marshmallows": 167995,
    "cheddar cheese": 173414,
    "cheddar": 173414,
    "mozzarella": 170845,
    "mozzarella cheese": 170845,
    "parmesan": 171247,
    "parmesan cheese": 171247,
}

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
        toks = _variants(_tokens(head))
        if not toks:
            return None

        candidates: set[int] = set()
        for t in toks:
            for fid in self._postings.get(t, ()):
                candidates.add(fid)
                if len(candidates) > 400:
                    break
            if len(candidates) > 400:
                break

        best_fid = None
        best_score = 0.0
        for fid in candidates:
            f = self._desc_tokens[fid]
            inter = len(toks & f)
            if inter == 0:
                continue
            union = len(toks | f)
            score = inter / union
            # Prefer descriptions whose tokens are a subset (more generic).
            if f <= toks:
                score += 0.5
            if score > best_score:
                best_score = score
                best_fid = fid

        if best_fid is None or best_score < 0.4:
            return None
        return self.composition(best_fid)


_REF: _Reference | None = None


def _default_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "data", "reference", "fdc_srlegacy.csv")


def get_reference() -> _Reference:
    global _REF
    if _REF is None:
        _REF = _Reference(_default_path())
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

    starch = carb - sugar - fiber
    if starch < 0:
        starch = 0.0

    vec = {
        "water": water / 100.0,
        "fat": fat / 100.0,
        "sugar": sugar / 100.0,
        "salt": sodium * 2.5 / 100000.0,
    }
    if category in STARCH_CATEGORIES:
        vec["flour"] = starch / 100.0

    vec = {k: v for k, v in vec.items() if v > 1e-6}
    return vec


@lru_cache(maxsize=None)
def fdc_compose(head: str) -> dict[str, float] | None:
    """Return the FDC-derived part vector for a head, or ``None`` if unmatched."""
    ref = get_reference()
    fid = CURATED.get(head)
    if fid is not None:
        return ref.composition(fid)
    return ref.fuzzy(head)
