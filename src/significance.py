"""Mass-significance rule: which ingredients contribute to the ratio.

An ingredient is *significant* in a recipe if its mass is large enough to matter
structurally, OR if it is a functional ingredient that acts at tiny mass
(leavener, salt, yeast). Trace flavorings (vanilla, spices) fall below the
threshold and are ignored.

The rule is a parameter: ``share_min`` (fraction of total recipe mass),
``grams_min`` (absolute floor), and the functional whitelist are all tunable.
"""

from __future__ import annotations

SHARE_MIN = 0.02
GRAMS_MIN = 2.0

# Parts that bypass the mass threshold (powerful at small amounts).
FUNCTIONAL_PARTS = frozenset({"leavener", "salt", "yeast"})


def qualifies(grams: float | None, total: float, functional: bool = False) -> bool:
    """Return True if an ingredient of ``grams`` is significant in a recipe.

    ``total`` is the recipe's summed ingredient mass. ``functional`` should be
    True when the ingredient maps to a functional part (leavener/salt/yeast).
    """
    if functional:
        return True
    if grams is None or grams <= 0 or total <= 0:
        return False
    return grams >= GRAMS_MIN and (grams / total) >= SHARE_MIN
