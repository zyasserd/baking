"""From-scratch / baked-goods filters for the ratio experiment.

The experiment asks whether the base ratio (flour, liquid, egg, fat, sugar)
determines the kind of baked good. That only holds for from-scratch, oven-baked
items: a prepared ingredient (dough, mix, pastry sheet) hides its flour/fat/sugar,
so its parsed grams are meaningless, and no-bake / topping recipes are not baked
goods. ``is_excluded`` returns True for recipes that must be dropped.

The keyword lists are parameters: edit them to tune the filter.
"""

from __future__ import annotations

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

    for ing in ingredients:
        if _has_any(ing, PREPARED_INGREDIENT_KEYWORDS):
            return True

    if _has_any(title, TOPPING_TITLE_KEYWORDS) and not _has_any(
        title, TOPPING_CONTAINER_KEYWORDS
    ):
        return True

    return False
