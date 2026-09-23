"""Baked-goods taxonomy over Food.com tags.

The classification is a *parameter*, not a fixed fact: the tag-to-class mapping
lives in ``TAXONOMY`` and is deliberately easy to edit (merge/split/drop classes)
without touching the pipeline. Each recipe's raw Food.com tags are resolved to a
``(coarse, fine, confidence)`` triple:

- ``coarse`` — one of the 7 primary classes plus the ``dessert_other`` weak tier.
- ``fine`` — the most specific matched tag (kept for transparency).
- ``confidence`` — ``strong`` (a single leaf tag), ``medium`` (parent tag only,
  or leaf tags spanning classes), ``weak`` (``desserts`` only, or a non-dish
  facet). Weak recipes are excluded from primary scoring.

The taxonomy is the reconciliation of three sources:

- Food.com's tag hierarchy (the actual labels in the data),
- Michael Ruhlman's *Ratio* doughs/batters (bread, cookie, pie dough, choux,
  pound/sponge/quick cakes, crepe/pancake),
- Wikipedia's "List of baked goods" (bread, cake, cookie, pastry, pie, tart,
  viennoiserie).

Classes nobody cares about (angel food, genoise, choux-as-its-own-class) are
folded into their parents; ``cake-fillings-and-frostings`` is dropped because a
frosting is not itself a baked good; the book's ambiguous "biscuit" is dropped as
a class (US biscuit -> ``quick_bread``, UK biscuit -> ``cookie``).

The taxonomy folds the *compositional* families together: muffins and scones sit
with ``quick_bread`` (same 2:2:1:1 batter as a loaf); pie dough and laminated
pastry are one ``pie_pastry`` family (both are fat-dominant, egg-free, water-poor
doughs that differ only in technique); and ``brownies`` are split out of
``cookie`` (their richer, eggier, low-leavener ratio is a distinct archetype).
"""

from __future__ import annotations

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

PRIMARY_CLASSES = CLASS_PRIORITY[:-1]

# Tag -> class. Each entry lists the specific leaf tags and the coarser parent
# tags that fall under it. ``dessert_other`` is the weak tier.
TAXONOMY: dict[str, dict[str, list[str]]] = {
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
DROPPED_TAGS = frozenset(
    {"cake-fillings-and-frostings", "baking", "bread-machine", "yeast"}
)

# Title keywords that rescue the under-tagged ``pie_pastry`` class (croissants,
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


def leaf_class(tag: str) -> str | None:
    for cls, mapping in TAXONOMY.items():
        if tag in mapping["leaves"]:
            return cls
    return None


def parent_class(tag: str) -> str | None:
    for cls, mapping in TAXONOMY.items():
        if tag in mapping["parents"]:
            return cls
    return None


def _pick(classes: list[str]) -> str:
    """Deterministic tie-break: earliest class in ``CLASS_PRIORITY``."""
    return min(classes, key=lambda c: CLASS_PRIORITY.index(c))


def classify(tags: list[str] | set[str]) -> tuple[str, str, str] | None:
    """Resolve a recipe's Food.com tags to ``(coarse, fine, confidence)``.

    Returns ``None`` when no tag identifies a baked-good class.
    """
    tags = set(tags) - DROPPED_TAGS
    if not tags:
        return None

    leaf_hits: dict[str, list[str]] = {}
    parent_hits: dict[str, list[str]] = {}
    for t in tags:
        lc = leaf_class(t)
        if lc is not None:
            leaf_hits.setdefault(lc, []).append(t)
            continue
        pc = parent_class(t)
        if pc is not None:
            parent_hits.setdefault(pc, []).append(t)

    if leaf_hits:
        coarse = _pick(list(leaf_hits))
        fine = sorted(leaf_hits[coarse])[0]
        confidence = "strong" if len(leaf_hits) == 1 else "medium"
        return coarse, fine, confidence

    if parent_hits:
        coarse = _pick(list(parent_hits))
        fine = sorted(parent_hits[coarse])[0]
        confidence = "medium" if len(parent_hits) == 1 else "weak"
        return coarse, fine, confidence

    # Only the broad "desserts" umbrella remains (it co-occurs with every
    # class, so it is only used as a class when nothing more specific is tagged).
    if "desserts" in tags:
        return "dessert_other", "desserts", "weak"

    return None


def is_pastry_title(title: str) -> bool:
    """True if a title names a laminated/choux/viennoiserie product."""
    t = (title or "").lower()
    return any(k in t for k in PASTRY_TITLE_KEYWORDS)


# Brownies are filed under Food.com's generic "bar-cookies" leaf, so the
# explicit "brownies" leaf is nearly empty; the title is the reliable signal.
BROWNIE_TITLE_KEYWORDS = ("brownie", "brownies", "blondie", "blondies")


def is_brownie_title(title: str) -> bool:
    """True if the recipe title names a brownie/blondie."""
    t = (title or "").lower()
    return any(k in t for k in BROWNIE_TITLE_KEYWORDS)
