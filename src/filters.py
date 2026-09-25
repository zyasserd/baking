"""From-scratch / baked-goods filters for the ratio experiment.

The experiment asks whether the base ratio (flour, liquid, egg, fat, sugar)
determines the kind of baked good. That only holds for from-scratch, oven-baked
items: a prepared ingredient (dough, mix, pastry sheet) hides its flour/fat/sugar,
so its parsed grams are meaningless, and no-bake / topping recipes are not baked
goods. ``is_excluded`` returns True for recipes that must be dropped.

The keyword lists are parameters: edit them to tune the filter.
"""

from __future__ import annotations

import re

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

_PREPARED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE) for p in PREPARED_INGREDIENT_PATTERNS
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


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


def is_excluded(title: str, ingredients: list[str]) -> bool:
    """Return True when a recipe is not a from-scratch baked good."""
    if _has_any(title, NO_BAKE_TITLE_KEYWORDS):
        return True

    patterns = _PREPARED_PATTERNS
    for ing in ingredients:
        if _has_any(ing, PREPARED_INGREDIENT_KEYWORDS):
            return True
        if any(p.search(ing) for p in patterns):
            return True

    if _has_any(title, TOPPING_TITLE_KEYWORDS) and not _has_any(
        title, TOPPING_CONTAINER_KEYWORDS
    ):
        return True

    return False
