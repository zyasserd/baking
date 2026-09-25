"""Central parameter file — every tunable decision in one place.

The pipeline has two stages (see README):

1. **preprocess** (`scripts/preprocess.py`): raw corpora -> a per-recipe
   dataset of structural part grams + simplex proportions (summing to 1) and
   independent Food.com tag labels.
2. **analysis** (`scripts/analyze.py`): that dataset -> PCA, clustering,
   figures, results.

Everything a curious reader might want to re-tune lives here: the taxonomy, the
decomposition rules, densities, thresholds, folds, seeds. The modules import
from this file; pure mechanics (regex structure, algorithms) stay with the code.

Every section below is marked with the stage that consumes it:

  [STAGE 1]  preprocess-only      [STAGE 2]  analysis-only
  [SHARED]   used by both         [DATA]     raw-data locations / provenance
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# DATA — locations, provenance, content pins.  [DATA]
# ══════════════════════════════════════════════════════════════════════════════
#
# All raw datasets are pinned in flake.nix and staged as store symlinks by the
# dev shell (shellHook) at the locations below:
#
# - RecipeNLG (Bien et al. 2020, 2.3 M recipe NER+text corpus):
#   official site https://recipenlg.cs.put.poznan.pl/dataset requires a
#   registration form; the flake fetches a byte-identical public mirror
#   (Hugging Face `innovate-data/RecipeNLG`, sha256 verified against the local
#   copy) and links it at RAW_RECIPE_NLG_CSV.
#
# - USDA FoodData Central, SR Legacy (2018-04, the final Standard Reference
#   release): fetched AND unzipped by the flake; the unpacked tables the
#   pipeline reads are linked at FDC_TABLES_DIR, and the compact per-food CSV
#   used as reference is derived from them by `src/preprocess/fdc.py`
#   (no network, no extraction).
#
# - Food.com corpus (shuyangli94 on Kaggle): provides the independent *labels*
#   (tag classes) and per-recipe nutrition. Kaggle requires login, so it cannot
#   be fetched by nix; download RAW_recipes.csv manually from
#   https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions
#   into data/raw/food/. The exact file is pinned by the sha256 in flake.nix,
#   validated by the dev shell on every entry (not by this pipeline).

RAW_RECIPE_NLG_CSV = "data/raw/RecipeNLG/RecipeNLG_dataset.csv"
RAW_FOOD_RECIPES_CSV = "data/raw/food/RAW_recipes.csv"

# Unpacked SR Legacy tables (food.csv, food_category.csv, food_nutrient.csv),
# linked by flake.nix; see src/preprocess/fdc.py.
FDC_TABLES_DIR = "data/raw/fdc"
FDC_REFERENCE_CSV = "data/interim/fdc_srlegacy.csv"

# FDC nutrient ids -> SR Legacy column names (per 100 g).
FDC_NUTRIENT_IDS = {
    1051: "water_g",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carb_g",
    1079: "fiber_g",
    2000: "sugar_g",
    1007: "ash_g",
    1093: "sodium_mg",
}

# Stage-1 outputs.
INTERIM_INGREDIENTS_CSV = "data/interim/ingredients.csv"
PROCESSED_RECIPES_CSV = "data/processed/recipes_simplex.csv"

# Analysis outputs directory.
OUTPUT_DIR = "output"

# ══════════════════════════════════════════════════════════════════════════════
# INGREDIENT DECOMPOSITION — head -> 9-part weight vector.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════
#
# Each ingredient is decomposed into tracked parts (weights sum to <= 1; the
# remainder is "other" and is ignored):
#
#     flour, sugar, fat, egg, milk, water, salt, leavener, yeast
#
# The vector comes from USDA FoodData Central (SR Legacy) per-100 g proximates
# via src/preprocess/reference.py. Pure parts are pinned to their own part at
# weight 1.0 so the parts stay self-consistent (flour *is* flour; butter *is*
# fat — the book convention, its 16% water is ignored).
#
# Roles: an ingredient is *base* (structural: flours, sugars, fats, eggs, dairy
# liquids, water, juices, broths, syrups, leaveners, salt, yeast) or *add-in*
# (chocolate, cocoa, nuts, seeds, fruit, vegetables, cheese, condiments, meats).
# The shipped decomposition is STRUCTURAL: add-ins are zeroed, reproducing
# Ruhlman's clean flour:liquid:egg:fat:sugar ratio (validated: clustering with
# structural grams beats pooled add-ins, ARI 0.207 vs 0.176 — see README).

# The tracked parts, in column order (`<part>_g`).
INGREDIENT_PARTS = [
    "flour", "sugar", "fat", "egg", "milk", "water", "salt", "leavener", "yeast",
]

# Multi-word rules, checked first (highest specificity). Each entry is
# (word sequence, vector, role). Literal vectors are USDA-derived approximations
# for products the reference does not capture well.
INGREDIENT_MULTI_RULES: list[tuple[tuple[str, ...], dict[str, float], str]] = [
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
INGREDIENT_SINGLE_PINS: list[tuple[str, str]] = [
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
INGREDIENT_FDC_BASE_HEADS = frozenset({
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

# Exact heads whose reference match is wrong or missing.
# - ALIAS_HEADS resolve through the reference under a better-matched name
#   (bare "cream" fuzzy-matches a cheese-like entry, so it is resolved as heavy
#   whipping cream — the standard meaning of "1 cup cream" in baking).
# - LITERAL_HEADS carry hand-set USDA vectors (ice cream's reference match
#   reports ~5% fat: a frozen-dairy-dessert entry, not ice cream).
INGREDIENT_ALIAS_HEADS: dict[str, str] = {
    "cream": "heavy cream",
    "double cream": "heavy cream",
    "thickened cream": "heavy cream",
    "single cream": "light cream",
}

INGREDIENT_ICE_CREAM_VECTOR: dict[str, float] = {"water": 0.56, "fat": 0.11, "sugar": 0.21}
INGREDIENT_LITERAL_HEADS: dict[str, dict[str, float]] = {
    "ice cream": INGREDIENT_ICE_CREAM_VECTOR,
    "vanilla ice cream": INGREDIENT_ICE_CREAM_VECTOR,
    "chocolate ice cream": INGREDIENT_ICE_CREAM_VECTOR,
}

# Words that mark an FDC-resolved ingredient as a structural base (liquid or
# sweetener) rather than an add-in.
INGREDIENT_BASE_WORDS = frozenset({
    "milk", "cream", "yogurt", "yoghurt", "buttermilk", "juice", "broth",
    "stock", "wine", "coffee", "espresso", "tea", "cider", "beer", "syrup",
    "honey", "molasses", "treacle", "agave",
})

# ══════════════════════════════════════════════════════════════════════════════
# USDA REFERENCE MATCHING — FDC SR Legacy lookup.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════
#
# Nutrient -> part transform (documented, tunable):
#
#     water   -> water
#     lipid   -> fat
#     sugars  -> sugar
#     starch  -> flour   (carb - sugar - fiber), *only* for grain/legume/
#                         vegetable/starch food categories
#     sodium  -> salt    (Na x 2.5, as NaCl)
#     protein, fiber, ash, and any starch from non-starch categories -> "other"
#                                                                  (ignored)
#
# The flour part is deliberately restricted to starchy food categories so that
# e.g. cocoa or dried fruit do not leak into "flour" through their carbohydrate.
# Pure parts (flour, sugar, butter, egg, milk, water, ...) are pinned to their
# own part in the decomposition and never reach this mapping.

# Food categories whose carbohydrate is treated as starch ("flour" part).
FDC_STARCH_CATEGORIES = frozenset({
    "Cereal Grains and Pasta",
    "Legumes and Legume Products",
    "Vegetables and Vegetable Products",
    "Breakfast Cereals",
    "Baked Products",
    "Snacks",
    "Meals, Entrees, and Side Dishes",
})

# Curated head -> SR Legacy fdc_id. Hand-checked against the USDA descriptions;
# the long tail is resolved by the fuzzy matcher.
FDC_CURATED: dict[str, int] = {
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

# Fuzzy-matcher tuning (token-overlap scoring against FDC descriptions).
FDC_FUZZY_CANDIDATE_CAP = 400   # stop growing the candidate set past this size
FDC_FUZZY_SUBSET_BONUS = 0.5    # bonus when description tokens ⊆ head tokens
FDC_FUZZY_MIN_SCORE = 0.4       # reject matches below this Jaccard-like score

# Sodium -> salt conversion (Na x 2.5 = NaCl) and the trace-composition cutoff.
FDC_SODIUM_TO_SALT = 2.5
FDC_TRACE_CUTOFF = 1e-6

# ══════════════════════════════════════════════════════════════════════════════
# DENSITY — (amount, unit, ingredient) -> grams.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════

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

# Fallback grams-per-cup per part category.
DEFAULT_GRAMS_PER_CUP = {
    "flour": 125.0,
    "sugar": 200.0,
    "fat": 227.0,
    "egg": 243.0,
    "milk": 244.0,
    "water": 236.0,
    "salt": 288.0,
    "leavener": 220.0,
    "yeast": 150.0,
}

# Refined densities inside grams_per_cup (checked after name densities).
SUGAR_DENSITY_BROWN = 220.0
SUGAR_DENSITY_POWDERED = 120.0
SUGAR_DENSITY_DEFAULT = 200.0
FAT_DENSITY_OIL = 218.0
FAT_DENSITY_DEFAULT = 227.0
FLOUR_DENSITY_WHOLE_WHEAT = 120.0
FLOUR_DENSITY_CAKE = 120.0
FLOUR_DENSITY_BREAD = 130.0
FLOUR_DENSITY_CORN = 157.0
FLOUR_DENSITY_DEFAULT = 125.0
FALLBACK_GRAMS_PER_CUP = 200.0

# Count-based masses.
EGG_GRAMS = {"whole": 50.0, "yolk": 17.0, "white": 33.0}
STICK_OF_BUTTER_GRAMS = 113.0
YEAST_PACKET_GRAMS = 7.0

# Name-first grams-per-cup for ingredients whose mass is split across parts
# (dairy, syrups, chocolate, moist produce). Order matters: more specific
# substrings first; checked before the category defaults.
NAME_DENSITY: dict[str, float] = {
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
CONTAINER_OVERRIDES: list[tuple[str, str, float]] = [
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

CONTAINER_DEFAULTS = {
    "can": 400.0,
    "jar": 500.0,
}

# ══════════════════════════════════════════════════════════════════════════════
# SIGNIFICANCE — which ingredients contribute to the ratio.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════
# An ingredient is significant if its mass is large enough to matter
# structurally, OR it is functional (acts at tiny mass). Trace flavorings
# (vanilla, spices) fall below the threshold and are ignored.

SIGNIFICANCE_SHARE_MIN = 0.02   # minimum share of the recipe's total mass
SIGNIFICANCE_GRAMS_MIN = 2.0    # absolute floor in grams

# Parts that bypass the mass threshold (powerful at small amounts).
FUNCTIONAL_PARTS = frozenset({"leavener", "salt", "yeast"})

# ══════════════════════════════════════════════════════════════════════════════
# FILTERS — from-scratch / baked-goods exclusion.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════
# The experiment asks whether the base ratio determines the kind of baked good.
# That only holds for from-scratch, oven-baked items: a prepared ingredient
# (dough, mix, pastry sheet) hides its flour/fat/sugar, so its parsed grams are
# meaningless, and no-bake / topping recipes are not baked goods. Edit these
# tables to tune the filter.

# Ingredient text that signals a prepared (not-from-scratch) ingredient.
PREPARED_INGREDIENT_KEYWORDS = (
    "cookie dough",
    "bread dough",
    "pizza dough",
    "pie dough",
    "puff pastry",
    "phyllo",
    "filo dough",
    "crescent roll",
    "cinnamon roll",
    "croissant dough",
    "biscuit dough",
    "roll dough",
    "pie crust",
    "tart shell",
    "frozen dough",
    "refrigerated dough",
    "prepared dough",
    "refrigerated biscuits",
    "canned biscuits",
    "cake mix",
    "brownie mix",
    "cookie mix",
    "muffin mix",
    "bread mix",
    "cornbread mix",
    "pancake mix",
    "biscuit mix",
    "pie mix",
    "quick bread mix",
    "pudding mix",
    "instant pudding",
    "baking mix",
    "cheesecake mix",
    "cobbler mix",
    "stuffing mix",
    "soup mix",
    "seasoning mix",
    "crescent",
    # Purchased bread used as a base (cheese breads, stratas): the loaf's
    # flour/water/sugar is the recipe's whole structure, hidden from parsing.
    "french bread",
    "italian bread",
    "sourdough bread",
    "garlic bread",
    "ciabatta",
    "focaccia",
    "brioche",
    "challah",
    "naan",
    "flatbread",
    "baguette",
    "breadstick",
    "bread stick",
    "dinner rolls",
    "hot dog bun",
    "hamburger bun",
    "sandwich bread",
    "stale bread",
    # "Refrigerated X" is always a prepared product in this corpus
    # (refrigerated buttermilk biscuits, breadstick dough, dinner rolls).
    "refrigerated",
    # Any finished baked good used as an ingredient — the recipe is an
    # assembly, not a from-scratch bake. Breadcrumbs are a baked good too.
    "biscuit",
    "croissant",
    "bagel",
    "english muffin",
    "crumpet",
    "pita",
    "tortilla",
    "pretzel",
    "crouton",
    "breadcrumb",
    "bread crumb",
    "pancakes",
    "waffles",
    "waffle mix",
    "doughnut",
    "donut",
    "pound cake",
    "angel food",
    "sponge cake",
    "twinkie",
    "ladyfinger",
    "oreo",
    "nilla wafer",
    "vanilla wafer",
    "nutter butter",
    "ginger snap",
    "graham cracker",
    "graham crumbs",
    "graham crust",
    "saltine",
    "animal cracker",
    "ritz",
    "pie shell",
    "prebaked",
    "pre-baked",
    "prepared crust",
    "store-bought",
    "store bought",
)

# Substring matching is too blunt for a few words that name both a raw
# ingredient and a finished product. "bread" must not match "bread flour"
# (a raw high-protein flour) or "breaded" chicken; "crust" must not match
# "crustless". These are regex patterns searched against each line.
PREPARED_INGREDIENT_PATTERNS = (
    r"bread(?! ?(?:flour|crumb|spice|machine))(?!ed\b)",
    r"crust(?!less)",
)

# Title keywords that signal a no-bake / frozen item.
NO_BAKE_TITLE_KEYWORDS = (
    "no-bake",
    "no bake",
    "icebox",
    "frozen dessert",
    "popsicle",
)

# A title naming a topping/filling (not a baked good). A topping word is ignored
# when the title also names a container it goes on (a "cake with frosting" is a
# cake), so these are only dropped when the topping is the whole item.
TOPPING_TITLE_KEYWORDS = (
    "frosting",
    "icing",
    "glaze",
    "buttercream",
    "ganache",
    "filling",
    "topping",
)
TOPPING_CONTAINER_KEYWORDS = (
    "cake",
    "cookie",
    "pie",
    "bread",
    "muffin",
    "tart",
    "brownie",
    "cupcake",
    "scone",
    "roll",
    "bar",
)

# ══════════════════════════════════════════════════════════════════════════════
# PARSING — ingredient-line vocabulary.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════

# Preparation/quantity descriptors stripped from the head (moved to `props`).
# Compositional modifiers ("brown", "powdered", "whole wheat", "unsweetened",
# "self-rising", "skim", "heavy", "sour", ...) are intentionally NOT listed here.
PARSE_PREP_PROPS = frozenset({
    "chopped", "minced", "diced", "sliced", "grated", "shredded", "crushed",
    "melted", "softened", "beaten", "divided", "optional", "peeled", "drained",
    "rinsed", "sifted", "packed", "halved", "quartered", "cubed", "julienned",
    "mashed", "pureed", "ground", "finely", "roughly", "thinly", "coarsely",
    "firmly", "lightly", "well", "seeded", "cored", "trimmed", "washed",
    "toasted", "thawed", "cooked", "boneless", "skinless", "lean", "frozen",
    "canned", "fresh", "dried", "extra", "virgin", "room", "temperature", "to",
    "taste", "large", "medium", "small", "unseasoned", "seasoned", "prepared",
    "smoked", "unsalted", "salted", "plain", "nonfat", "reduced", "low",
})

# Multi-component recipes (a coffee cake = streusel + filling + batter) keep
# their section headers as quantity-less lines in the flattened ingredient
# list ("Streusel Topping", "Cream Cheese Filling", "for the glaze:").
PARSE_COMPONENT_KIND_RE = (
    r"toppings?|fillings?|streusel|crusts?|batters?|glazes?|icings?"
    r"|frostings?|doughs?|mixtures?|layers?|coatings?|ganache|drizzles?|crumbs?"
)

# Sections whose ingredients never bake into the crumb (they are spread on
# after baking or are pure decorations): their mass must not be pooled into
# the batter's ratio. Everything else (streusel, filling, crust, dough, ...)
# bakes with the recipe and stays pooled.
PARSE_NONBAKED_KINDS = frozenset({
    "glaze", "glazes", "icing", "icings", "frosting", "frostings",
    "ganache", "drizzle", "drizzles", "coating", "coatings",
})

# Stray unit/measure words that leak into the name when the amount carries a
# parenthetical size ("1 (8 oz.) pkg. cream cheese" -> head "cream cheese").
PARSE_UNIT_WORDS = frozenset({
    "pkg", "package", "packages", "packet", "packets", "can", "jar", "bottle",
    "bottles", "box", "boxes", "bag", "bags", "container", "containers",
    "stick", "sticks", "envelope", "envelopes", "dash", "pinch", "drop",
    "drops", "slice", "slices", "piece", "pieces",
})

# RecipeNLG's ingredient strings sometimes lose the slash in a leading
# fraction: "1/4 cup" appears as "14 cup", "1/2 teaspoon" as "12 teaspoon",
# "3/4 cup" as "34 cup". Reconstruction table + the units it applies to
# (weight units like oz/g are left alone — "12 oz" is a real amount).
MANGLED_FRACTIONS: dict[str, tuple[int, int]] = {
    "12": (1, 2), "13": (1, 3), "14": (1, 4), "18": (1, 8),
    "23": (2, 3), "34": (3, 4), "38": (3, 8),
    "58": (5, 8), "78": (7, 8), "116": (1, 16),
}
MANGLE_RECONSTRUCT_UNITS = frozenset({"cup", "tbsp", "tsp", "pt", "qt", "gal", "lb"})

# Plausibility window for un-mangling a bare number into a fraction.
MANGLE_PLAUSIBLE_MIN = 10
MANGLE_PLAUSIBLE_MAX = 999

# ══════════════════════════════════════════════════════════════════════════════
# TAG TAXONOMY — independent labels from Food.com tags.  [STAGE 1]
# ══════════════════════════════════════════════════════════════════════════════
#
# The classification is a *parameter*, not a fixed fact: the tag-to-class
# mapping lives in TAG_TAXONOMY and is deliberately easy to edit
# (merge/split/drop classes) without touching the pipeline. Each recipe's raw
# Food.com tags are resolved to a (coarse, fine, confidence) triple:
#
# - coarse — one of the primary classes plus the dessert_other weak tier.
# - fine — the most specific matched tag (kept for transparency).
# - confidence — strong (a single leaf tag), medium (parent tag only, or leaf
#   tags spanning classes), weak (desserts only, or a non-dish facet). Weak
#   recipes are excluded from primary scoring.
#
# The taxonomy is the reconciliation of three sources:
# - Food.com's tag hierarchy (the actual labels in the data),
# - Michael Ruhlman's *Ratio* doughs/batters (bread, cookie, pie dough, choux,
#   pound/sponge/quick cakes, crepe/pancake),
# - Wikipedia's "List of baked goods" (bread, cake, cookie, pastry, pie, tart,
#   viennoiserie).
#
# Classes nobody cares about (angel food, genoise, choux-as-its-own-class) are
# folded into their parents; cake-fillings-and-frostings is dropped because a
# frosting is not itself a baked good; the book's ambiguous "biscuit" is dropped
# as a class (US biscuit -> quick_bread, UK biscuit -> cookie).
#
# The taxonomy folds the *compositional* families together: muffins and scones
# sit with quick_bread (same 2:2:1:1 batter as a loaf); pie dough and laminated
# pastry are one pie_pastry family (both are fat-dominant, egg-free, water-poor
# doughs that differ only in technique); and brownies are split out of cookie
# (their richer, eggier, low-leavener ratio is a distinct archetype).

# Class order used for deterministic tie-breaks when a recipe carries leaf tags
# from more than one class (rare). Earliest wins.
CLASS_PRIORITY = [
    "cookie",
    "cake",
    "pie_pastry",
    "bread",
    "quick_bread",
    "brownies",
    "batter",
    "dessert_other",
]

# The classes scored in the analysis; dessert_other is the weak tier.
PRIMARY_CLASSES = CLASS_PRIORITY[:-1]

# Tag -> class. Each entry lists the specific leaf tags and the coarser parent
# tags that fall under it. dessert_other is the weak tier.
TAG_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "bread": {
        "leaves": ["sourdough", "rolls-biscuits"],
        "parents": ["breads"],
    },
    "quick_bread": {
        "leaves": ["quick-breads", "muffins", "scones", "coffee-cakes"],
        "parents": [],
    },
    "cake": {
        "leaves": ["cupcakes", "cheesecake"],
        "parents": ["cakes"],
    },
    "cookie": {
        "leaves": [
            "bar-cookies",
            "drop-cookies",
            "hand-formed-cookies",
            "rolled-cookies",
        ],
        "parents": ["cookies-and-brownies"],
    },
    "brownies": {
        "leaves": ["brownies"],
        "parents": [],
    },
    "pie_pastry": {
        "leaves": ["pies", "tarts", "savory-pies", "danish", "crusts-pastry-dough-2"],
        "parents": ["pies-and-tarts"],
    },
    "batter": {
        "leaves": ["pancakes-and-waffles"],
        "parents": [],
    },
    "dessert_other": {
        "leaves": ["cobblers-and-crisps", "puddings-and-mousses"],
        "parents": [],
    },
}

# Facet/technique tags that do not identify a dish class.
TAG_DROPPED = frozenset(
    {"cake-fillings-and-frostings", "baking", "bread-machine", "yeast"}
)

# Title keywords that rescue the under-tagged pie_pastry class (croissants,
# puff, choux are rarely tagged in Food.com). Used only when tags are weak or
# absent, so it never overrides a strong/medium tag assignment.
PASTRY_TITLE_KEYWORDS = (
    "croissant",
    "puff pastry",
    "rough puff",
    "pate feuilletee",
    "choux",
    "eclair",
    "profiterole",
    "gougere",
    "danish pastry",
    "viennoiserie",
    "laminated",
    "turnover",
    "strudel",
    "phyllo",
    "filo",
    "palmier",
    "vol au vent",
    "vol-au-vent",
    "bear claw",
    "kolache",
    "kolacz",
    "empanada",
    "cream puff",
    "mille feuille",
    "mille-feuille",
    "napoleon",
    "baklava",
    "spanakopita",
    "pate a choux",
    "puff",
)

# Brownies are filed under Food.com's generic "bar-cookies" leaf, so the
# explicit "brownies" leaf is nearly empty; the title is the reliable signal.
BROWNIE_TITLE_KEYWORDS = ("brownie", "brownies", "blondie", "blondies")

# ══════════════════════════════════════════════════════════════════════════════
# COMPOSITION FOLDS — grams -> analysis parts.  [STAGE 1 + STAGE 2]
# ══════════════════════════════════════════════════════════════════════════════

# The five analysis parts, in the order used by the book's ratios. Liquid folds
# water + milk (and cream/yogurt/buttermilk, which the parser maps to milk_g).
ANALYSIS_PARTS = ["flour", "liquid", "egg", "fat", "sugar"]

# Gram columns that contribute to each analysis part.
ANALYSIS_PART_SOURCES: dict[str, list[str]] = {
    "flour": ["flour_g"],
    "liquid": ["water_g", "milk_g"],
    "egg": ["egg_g"],
    "fat": ["fat_g"],
    "sugar": ["sugar_g"],
}

# Book archetypes (Ruhlman's *Ratio*), parts by weight in ANALYSIS_PARTS order.
# Zeros are structural (e.g. bread has no egg/fat/sugar); they are handled by
# the same multiplicative-replacement used for the data.
#
# `cookie` is a drop cookie (3 flour : 1 egg : 2 fat : 3 sugar) and
# `shortbread` is the book's bare 1-2-3 ratio (1 sugar : 2 fat : 3 flour, no
# egg). Both map to the cookie family: as the book notes, real cookies almost
# always add egg (pulling them toward cake), so using the egg-bearing
# drop-cookie ratio keeps chocolate-chip cookies from being misread as pound
# cake, while the no-egg shortbread catches short cookies and wedding cookies.
ARCHETYPES: dict[str, list[float]] = {
    "bread":       [5, 3, 0, 0, 0],
    "pie_dough":   [3, 1, 0, 2, 0],
    "biscuit":     [3, 2, 0, 1, 0],
    "cookie":      [3, 0, 1, 2, 3],
    "shortbread":  [3, 0, 0, 2, 1],
    "choux":       [1, 2, 2, 1, 0],
    "pound_cake":  [1, 0, 1, 1, 1],
    "angel_food":  [1, 0, 3, 0, 3],
    "quick_bread": [2, 2, 1, 1, 0],
    "pancake":     [2, 2, 1, 0.5, 0],
    "crepe":       [0.5, 1, 1, 0, 0],
}

# The 4-part sub-composition used to draw the 4-D simplex in 3-D. Egg folds
# into liquid ("wet": an egg is ~75% water and behaves as a hydrated structure-
# builder). This merge is chosen empirically, not by taste: clustering the tag
# classes in each candidate 4-part sub-composition (all 10 single-pair merges)
# gives ARI 0.21 for liquid+egg vs ~0.17 for every alternative (including the
# fat+sugar "richness" fold), and it also keeps the book archetypes most
# distinct (min pairwise Aitchison distance 0.57 vs 0.44 for fat+sugar).
TETRAHEDRON_PARTS = ["flour", "liquid+egg", "fat", "sugar"]

TETRAHEDRON_SOURCES: list[list[str]] = [
    ["flour_g"],
    ["water_g", "milk_g", "egg_g"],
    ["fat_g"],
    ["sugar_g"],
]

# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS — PCA, outliers, clustering, subsampling.  [STAGE 2]
# ══════════════════════════════════════════════════════════════════════════════

# Multiplicative zero-replacement: delta = ZERO_REPLACEMENT_FACTOR * min(positive).
ZERO_REPLACEMENT_DELTA = 0.5

# PC1's sign is pinned to this direction so it always reads rich > lean
# (eigenvector signs from eigendecomposition are arbitrary and can flip between
# runs). The vector is +sugar in ANALYSIS_PARTS order.
PC1_ORIENT_PART = "sugar"

# Clustering runs in the top-3 log-ratio PCs: the first three components
# separate the tag classes measurably better than two, and PC4 only adds noise.
N_PCS_CLUSTER = 3

# Outliers: robust Mahalanobis (EllipticEnvelope) tail fraction and seed.
OUTLIER_CONTAMINATION = 0.01

# Clustering method and seed. k is the number of tag classes.
CLUSTER_METHOD = "kmeans"
CLUSTER_SEED = 0

# Subsample cap for figures/clustering, and the silhouette sample cap.
VIZ_SAMPLE_MAX = 20000
SILHOUETTE_SAMPLE_MAX = 20000

# Seeds used anywhere randomness could leak in (determinism).
RANDOM_SEED = 0

# Tag-confidence gate for the primary analysis: drop the weak tier
# (dessert_other) unless overridden here. `MIN_TAG_CONFIDENCE` optionally
# restricts further ("strong" | "medium" | None).
DROP_WEAK_TIER = True
MIN_TAG_CONFIDENCE: str | None = None

# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION — diagnostic tables written by stage 2 (src/analysis/validate.py).
# ══════════════════════════════════════════════════════════════════════════════

# Title keywords used to spot-check tag correctness per class (independent of
# the tag-derived labels).
VALIDATION_TITLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cookie": ("cookie", "cookies", "shortbread", "biscotti", "snickerdoodle"),
    "cake": ("cake", "cupcake"),
    "pie_pastry": ("pie", "tart", "pastry", "croissant", "strudel", "danish",
                   "empanada", "baklava", "turnover", "strudel"),
    "bread": ("bread", "loaf", "baguette", "boule", "brioche", "challah",
              "focaccia", "sourdough", "rolls", "buns"),
    "quick_bread": ("muffin", "muffins", "scone", "scones", "banana bread",
                    "cornbread", "quick bread", "coffee cake"),
    "brownies": ("brownie", "brownies", "blondie", "blondies"),
    "batter": ("pancake", "pancakes", "waffle", "waffles", "crepe", "crepes"),
    "dessert_other": ("cobbler", "crisp", "crumble", "mousse", "pudding"),
}

# Correlations are reported per class; skip classes with fewer rows than this.
VALIDATION_MIN_ROWS = 20

# Number of random sample rows for eyeballing in src/analysis/validate.py.
VALIDATION_SAMPLE_ROWS = 8