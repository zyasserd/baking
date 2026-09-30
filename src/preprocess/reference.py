"""USDA FoodData Central (SR Legacy) reference for ingredient composition.

This module is the *reference* behind ``src.preprocess.ingredients``: instead of
hand-tuned numbers, an ingredient's weight vector into the baking parts comes
from USDA's proximate composition (per 100 g). ``src/preprocess/fdc.py`` builds
the backing CSV (``config.FDC_REFERENCE_CSV``) from the flake-staged SR Legacy
tables; this module loads it, maps a cleaned ingredient head to a food, and
converts its nutrients to a part vector.

Nutrient -> part transform (implemented below in ``nutrient_to_parts``):

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
import re
from functools import lru_cache

import config

# Food categories whose carbohydrate is treated as starch ("flour" part) in the
# nutrient -> part transform, so that e.g. cocoa or dried fruit do not leak into
# "flour" through their carbohydrate.
_STARCH_CATEGORIES = frozenset({
    "Cereal Grains and Pasta",
    "Legumes and Legume Products",
    "Vegetables and Vegetable Products",
    "Breakfast Cereals",
    "Baked Products",
    "Snacks",
    "Meals, Entrees, and Side Dishes",
})

# Sodium -> salt conversion (Na x 2.5 = NaCl) and the trace-composition cutoff.
SODIUM_TO_SALT = 2.5
TRACE_CUTOFF = 1e-6

# Curated head -> exact USDA SR Legacy description, resolved to an fdc_id at
# load time. These are hand-checked disambiguations for heads the fuzzy matcher
# gets wrong or misses (bare "cream" fuzzy-matches a cheese-like entry; ice
# cream's match is a frozen-dairy-dessert entry). Keyed by the human-readable
# description — validated to be unique in the table — instead of an opaque
# fdc_id, so the mapping is readable and self-verifying against the shipped
# SR Legacy release.
_CURATED_DESCRIPTIONS: dict[str, str] = {
    "cream cheese": 'Cheese, cream',
    "cottage cheese": 'Cheese, cottage, creamed, large or small curd',
    "ricotta": 'Cheese, ricotta, whole milk',
    "ricotta cheese": 'Cheese, ricotta, whole milk',
    "sour cream": 'Cream, sour, cultured',
    "yogurt": 'Yogurt, plain, whole milk',
    "yoghurt": 'Yogurt, plain, whole milk',
    "plain yogurt": 'Yogurt, plain, whole milk',
    "greek yogurt": 'Yogurt, plain, whole milk',
    "buttermilk": 'Milk, buttermilk, fluid, cultured, lowfat',
    "heavy cream": 'Cream, fluid, heavy whipping',
    "heavy whipping cream": 'Cream, fluid, heavy whipping',
    "whipping cream": 'Cream, fluid, heavy whipping',
    "light cream": 'Cream, fluid, light (coffee cream or table cream)',
    "half and half": 'Cream, fluid, half and half',
    "whole milk": 'Milk, whole, 3.25% milkfat, with added vitamin D',
    "evaporated milk": 'Milk, canned, evaporated, with added vitamin D and without added vitamin A',
    "condensed milk": 'Milk, canned, condensed, sweetened',
    "sweetened condensed milk": 'Milk, canned, condensed, sweetened',
    "honey": 'Honey',
    "maple syrup": 'Syrups, maple',
    "corn syrup": 'Syrups, corn, light',
    "dark corn syrup": 'Syrups, corn, dark',
    "molasses": 'Molasses',
    "golden syrup": 'Syrups, corn, light',
    "brown sugar": 'Sugars, brown',
    "powdered sugar": 'Sugars, powdered',
    "confectioners sugar": 'Sugars, powdered',
    "icing sugar": 'Sugars, powdered',
    "granulated sugar": 'Sugars, granulated',
    "white sugar": 'Sugars, granulated',
    "caster sugar": 'Sugars, granulated',
    "chocolate": 'Chocolate, dark, 45- 59% cacao solids',
    "dark chocolate": 'Chocolate, dark, 70-85% cacao solids',
    "semisweet chocolate": 'Candies, semisweet chocolate',
    "chocolate chips": 'Candies, semisweet chocolate',
    "cocoa": 'Cocoa, dry powder, unsweetened',
    "cocoa powder": 'Cocoa, dry powder, unsweetened',
    "unsweetened cocoa": 'Cocoa, dry powder, unsweetened',
    "dutch cocoa": 'Cocoa, dry powder, unsweetened',
    "oats": 'Cereals, oats, regular and quick, not fortified, dry',
    "rolled oats": 'Cereals, oats, regular and quick, not fortified, dry',
    "quick oats": 'Cereals, oats, regular and quick, not fortified, dry',
    "old fashioned oats": 'Cereals, oats, regular and quick, not fortified, dry',
    "pecans": 'Nuts, pecans, dry roasted, with salt added',
    "pecan": 'Nuts, pecans, dry roasted, with salt added',
    "walnuts": 'Nuts, walnuts, black, dried',
    "walnut": 'Nuts, walnuts, black, dried',
    "almonds": 'Nuts, almonds, dry roasted, without salt added',
    "almond": 'Nuts, almonds, dry roasted, without salt added',
    "raisins": "Raisins, dark, seedless (Includes foods for USDA's Food Distribution Program)",
    "raisin": "Raisins, dark, seedless (Includes foods for USDA's Food Distribution Program)",
    "dates": 'Dates, deglet noor',
    "dried cranberries": "Cranberries, dried, sweetened (Includes foods for USDA's Food Distribution Program)",
    "cranberries": "Cranberries, dried, sweetened (Includes foods for USDA's Food Distribution Program)",
    "coconut": 'Nuts, coconut meat, dried (desiccated), not sweetened',
    "unsweetened coconut": 'Nuts, coconut meat, dried (desiccated), not sweetened',
    "shredded coconut": 'Nuts, coconut meat, dried (desiccated), not sweetened',
    "banana": 'Bananas, raw',
    "bananas": 'Bananas, raw',
    "pumpkin": 'Pumpkin, canned, without salt',
    "canned pumpkin": 'Pumpkin, canned, without salt',
    "pumpkin puree": 'Pumpkin, canned, without salt',
    "carrot": 'Carrots, baby, raw',
    "carrots": 'Carrots, baby, raw',
    "zucchini": 'Squash, summer, zucchini, includes skin, frozen, unprepared',
    "applesauce": 'Applesauce, canned, unsweetened, with added ascorbic acid',
    "lemon juice": 'Lemon juice, raw',
    "lime juice": 'Lemon juice, raw',
    "orange juice": "Orange juice, raw (Includes foods for USDA's Food Distribution Program)",
    "tomato sauce": 'Tomato sauce, canned, no salt added',
    "mustard": 'Mustard, prepared, yellow',
    "dijon mustard": 'Mustard, prepared, yellow',
    "yellow mustard": 'Mustard, prepared, yellow',
    "ketchup": 'Catsup',
    "catsup": 'Catsup',
    "soy sauce": 'Soy sauce made from soy and wheat (shoyu), low sodium',
    "worcestershire sauce": 'Sauce, worcestershire',
    "worcestershire": 'Sauce, worcestershire',
    "vinegar": 'Vinegar, distilled',
    "distilled vinegar": 'Vinegar, distilled',
    "white vinegar": 'Vinegar, distilled',
    "balsamic vinegar": 'Vinegar, distilled',
    "cider vinegar": 'Vinegar, distilled',
    "red wine vinegar": 'Vinegar, distilled',
    "rice vinegar": 'Vinegar, distilled',
    "chicken broth": 'Soup, chicken broth, canned, condensed',
    "chicken stock": 'Soup, chicken broth, canned, condensed',
    "beef broth": 'Soup, chicken broth, canned, condensed',
    "beef stock": 'Soup, chicken broth, canned, condensed',
    "vegetable broth": 'Soup, chicken broth, canned, condensed',
    "wine": 'Alcoholic Beverage, wine, table, red, Gamay',
    "red wine": 'Alcoholic Beverage, wine, table, red, Gamay',
    "white wine": 'Alcoholic Beverage, wine, table, red, Gamay',
    "beer": 'Alcoholic beverage, beer, regular, all',
    "coffee": 'Beverages, coffee, brewed, breakfast blend',
    "cornstarch": 'Cornstarch',
    "corn starch": 'Cornstarch',
    "marshmallows": 'Candies, marshmallows',
    "cheddar cheese": "Cheese, cheddar (Includes foods for USDA's Food Distribution Program)",
    "cheddar": "Cheese, cheddar (Includes foods for USDA's Food Distribution Program)",
    "mozzarella": 'Cheese, mozzarella, whole milk',
    "mozzarella cheese": 'Cheese, mozzarella, whole milk',
    "parmesan": 'Cheese, parmesan, grated',
    "parmesan cheese": 'Cheese, parmesan, grated',
    # Heads systematically unresolved by the fuzzy matcher (found via the
    # per-class extremes report): brans, the slashed-fraction-bearing
    # "quick cooking oatmeal", and broth heads that token similarity still
    # routes to canned chicken meat ('Chicken, canned, no broth').
    "wheat bran": 'Wheat bran, crude',
    "oat bran": 'Oat bran, raw',
    "natural bran": 'Wheat bran, crude',
    "quick cooking oatmeal": 'Cereals, oats, regular and quick, not fortified, dry',
    "dates pitted": 'Dates, deglet noor',
    "fat free chicken broth": 'Soup, chicken broth, ready-to-serve',
    "fat chicken broth": 'Soup, chicken broth, ready-to-serve',
    # Generic heads: every "Nuts, <kind> nuts" description ties at the same
    # Jaccard score, and the winner was a coin flip (ginkgo nuts, 55% water,
    # for 453 rows). Pin to the generic blend.
    "nuts": 'Nuts, mixed nuts, dry roasted, with peanuts, without salt added',
    "mixed nuts": 'Nuts, mixed nuts, dry roasted, with peanuts, without salt added',
    # Batch from the standing unresolved-heads queue (data_quality loop):
    # chocolate-chip variants ("semisweet" is one token in USDA descriptions,
    # "semi sweet" two in the recipes — token overlap cannot bridge it),
    # canned/raw produce, jams, spices and cereals the fuzzy matcher misses.
    "semi sweet chocolate chips": 'Candies, semisweet chocolate',
    "butterscotch chips": 'Candies, butterscotch',
    "mini chocolate chip": 'Candies, semisweet chocolate',
    "miniature semisweet chocolate chips": 'Candies, semisweet chocolate',
    "semisweet chocolate chunks": 'Candies, semisweet chocolate',
    "semisweet chocolate morsels": 'Candies, semisweet chocolate',
    "semisweet mini chocolate chips": 'Candies, semisweet chocolate',
    "dark chocolate chips": 'Candies, chocolate, dark, NFS '
        '(45-59% cacao solids 90%; 60-69% cacao solids 5%; 70-85% cacao solids 5%)',
    "bittersweet chocolate": 'Chocolate, dark, 60-69% cacao solids',
    "m m s chocolate candy": 'Candies, milk chocolate',
    "toffee": 'Candies, toffee, prepared-from-recipe',
    "raspberry jam": 'Jams and preserves',
    "strawberry jam": 'Jams and preserves',
    "jam": 'Jams and preserves',
    "pineapple": 'Pineapple, raw, all varieties',
    "pineapple undrained": 'Pineapple, canned, juice pack, solids and liquids',
    "creamed corn": 'Corn, sweet, yellow, canned, cream style, regular pack',
    "maraschino cherry": 'Maraschino cherries, canned, drained',
    "candied cherry": 'Candied fruit',
    "crystallized ginger": 'Candied fruit',
    "nutmeg": 'Spices, nutmeg, ground',
    "flax seed meal": 'Seeds, flaxseed',
    "potato starch": 'Cornstarch',
    "rice krispies": 'Cereals ready-to-eat, rice, puffed, fortified',
    "all bran cereal": 'Wheat bran, crude',
    "flaked coconut": 'Nuts, coconut meat, dried (desiccated), sweetened, flaked, packaged',
    "desiccated coconut": 'Nuts, coconut meat, dried (desiccated), not sweetened',
    "hazelnuts": 'Nuts, hazelnuts or filberts',
    "pecan halves": 'Nuts, pecans, dry roasted, with salt added',
    "sultana": 'Raisins, golden, seedless',
    "sultanas": 'Raisins, golden, seedless',
    "apple cider": 'Apple juice, canned or bottled, unsweetened, with added ascorbic acid',
    "agave nectar": 'Sweetener, syrup, agave',
    "cool whip": 'Whipped topping, frozen, low fat',
    "baking cocoa": 'Cocoa, dry powder, unsweetened',
    "raw zucchini": 'Squash, summer, zucchini, includes skin, frozen, unprepared',
    "quick cooking oats": 'Cereals, oats, regular and quick, not fortified, dry',
    "quick cooking rolled oats": 'Cereals, oats, regular and quick, not fortified, dry',
    "old fashioned oatmeal": 'Cereals, oats, regular and quick, not fortified, dry',
    "quick oatmeal": 'Cereals, oats, regular and quick, not fortified, dry',
    "blended oatmeal": 'Cereals, oats, regular and quick, not fortified, dry',
}

# Stopwords dropped from both heads and FDC descriptions when matching.
_STOP = frozenset({
    "the", "a", "an", "of", "and", "or", "with", "for", "in", "on", "as",
    "raw", "canned", "fresh", "frozen", "dried", "cooked", "plain", "generic",
    "salted", "unsalted", "regular", "prepared", "ready", "to", "made", "from",
    "all", "purpose", "style", "nonfat", "low", "reduced", "light", "heavy",
    "whole", "without", "added", "uncooked", "unprepared", "household",
    # Variety/quality words that carry no compositional information
    # ("dates pitted organic", "organic whole wheat flour").
    "pitted", "organic",
    # Pure noise in compound heads ("fat free chicken broth",
    # "sugar free chocolate pudding"): the remaining tokens carry the food.
    # "fat" is always a diet qualifier in this corpus ("low fat", "fat free"),
    # never the food itself (butter/oil/lard are named directly).
    "free", "fat",
})

_WORD_RE = re.compile(r"[a-z0-9]+")

# Words whose naive "ies" -> "y" depluralization is wrong.
_PLURAL_EXCEPTIONS = {"cookies": "cookie", "brownies": "brownie"}

# Minimum description-token count for the subset bonus (see ``fuzzy``).
_SUBSET_BONUS_MIN_TOKENS = 3


def _tokens(text: str) -> list[str]:
    out = []
    for w in _WORD_RE.findall(text.lower()):
        if w in _STOP or w.isdigit() or len(w) < 2:
            continue
        out.append(w)
    return out


def _canonical(tokens: list[str]) -> set[str]:
    """Tokens mapped to singular forms — applied to BOTH match sides.

    Keeping the plural alongside the singular (the earlier ``_variants``) made
    descriptions contribute two tokens for one word ({banana, bananas}), so a
    singular head ("ripe banana") paid a phantom union term and fell below the
    match threshold while its plural form ("ripe bananas") passed.
    """
    out = set()
    for w in tokens:
        if w.endswith("ies"):
            out.add(_PLURAL_EXCEPTIONS.get(w, w[:-3] + "y"))
        elif w.endswith("oes"):
            out.add(w[:-2])
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us")):
            out.add(w[:-1])
        else:
            out.add(w)
    return out


class _Reference:
    """Lazily loaded SR Legacy table with a fuzzy-matching index."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._by_id: dict[int, dict] = {}
        self._descriptions: list[tuple[int, str]] = []
        self._by_description: dict[str, list[int]] = {}
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
                self._by_description.setdefault(row["description"], []).append(fid)
                toks = _canonical(_tokens(row["description"])) 
                self._desc_tokens[fid] = toks
                for t in toks:
                    self._postings.setdefault(t, []).append(fid)
        self._loaded = True

    def by_description(self, description: str) -> list[int]:
        """fdc_ids whose exact description equals ``description``."""
        self._load()
        return self._by_description.get(description, [])

    def composition(self, fdc_id: int) -> dict[str, float] | None:
        row = self._by_id.get(fdc_id)
        if row is None:
            return None
        return nutrient_to_parts(row)

    def fuzzy(self, head: str) -> dict[str, float] | None:
        self._load()
        tok_set = _canonical(_tokens(head))    
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
            # Only for multi-token descriptions: a short desc like
            # "Fat, chicken" (schmaltz) is a *different food* that happens to
            # be a token subset of "fat free chicken broth", and the bonus
            # would hand it the win over the actual broths.
            if f <= tok_set and len(f) >= _SUBSET_BONUS_MIN_TOKENS:
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


@lru_cache(maxsize=None)
def _curated_ids() -> dict[str, int]:
    """Resolve curated descriptions to fdc_ids, validating them at first use."""
    ref = get_reference()
    ids: dict[str, int] = {}
    for head, description in _CURATED_DESCRIPTIONS.items():
        matches = ref.by_description(description)
        if len(matches) != 1:
            state = "missing" if not matches else f"ambiguous ({len(matches)} entries)"
            raise SystemExit(
                f"curated USDA description for {head!r} is {state}: {description!r}"
            )
        ids[head] = matches[0]
    return ids


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
        "salt": sodium * SODIUM_TO_SALT / 100000.0,
    }
    if category in _STARCH_CATEGORIES:
        vec["flour"] = starch / 100.0

    vec = {k: v for k, v in vec.items() if v > TRACE_CUTOFF}
    return vec


@lru_cache(maxsize=None)
def fdc_compose(head: str) -> dict[str, float] | None:
    """Return the FDC-derived part vector for a head, or ``None`` if unmatched."""
    ref = get_reference()
    fid = _curated_ids().get(head)
    if fid is not None:
        return ref.composition(fid)
    return ref.fuzzy(head)