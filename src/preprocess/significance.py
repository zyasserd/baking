"""Mass-significance rule: which ingredients contribute to the ratio.

An ingredient is *significant* in a recipe if its mass is large enough to matter
structurally, OR if it is a functional ingredient that acts at tiny mass
(leavener, salt, yeast). Trace flavorings (vanilla, spices) fall below the
threshold and are ignored.

The thresholds are parameters — see the SIGNIFICANCE section of ``config``.
"""

from __future__ import annotations

import config


def qualifies(grams: float | None, total: float, functional: bool = False) -> bool:
    """Return True if an ingredient of ``grams`` is significant in a recipe.

    ``total`` is the recipe's summed ingredient mass. ``functional`` should be
    True when the ingredient maps to a functional part (leavener/salt/yeast).
    """
    if functional:
        return True
    if grams is None or grams <= 0 or total <= 0:
        return False
    return (
        grams >= config.SIGNIFICANCE_GRAMS_MIN
        and (grams / total) >= config.SIGNIFICANCE_SHARE_MIN
    )