"""Baked-goods taxonomy over Food.com tags.

Each recipe's raw Food.com tags are resolved to a ``(coarse, fine,
confidence)`` triple (see the TAG TAXONOMY section of ``config`` for the full
documentation of the class design):

- ``coarse`` — one of the primary classes plus the ``dessert_other`` weak tier.
- ``fine`` — the most specific matched tag (kept for transparency).
- ``confidence`` — ``strong`` (a single leaf tag), ``medium`` (parent tag only,
  or leaf tags spanning classes), ``weak`` (``desserts`` only, or a non-dish
  facet). Weak recipes are excluded from primary scoring.
"""

from __future__ import annotations

import config


def _leaf_class(tag: str) -> str | None:
    for cls, mapping in config.TAG_TAXONOMY.items():
        if tag in mapping["leaves"]:
            return cls
    return None


def _parent_class(tag: str) -> str | None:
    for cls, mapping in config.TAG_TAXONOMY.items():
        if tag in mapping["parents"]:
            return cls
    return None


def _pick(classes: list[str]) -> str:
    """Deterministic tie-break: earliest class in ``config.CLASS_PRIORITY``."""
    return min(classes, key=config.CLASS_PRIORITY.index)


def classify(tags: list[str] | set[str]) -> tuple[str, str, str] | None:
    """Resolve a recipe's Food.com tags to ``(coarse, fine, confidence)``.

    Returns ``None`` when no tag identifies a baked-good class.
    """
    tags = set(tags) - config.TAG_DROPPED
    if not tags:
        return None

    leaf_hits: dict[str, list[str]] = {}
    parent_hits: dict[str, list[str]] = {}
    for t in tags:
        lc = _leaf_class(t)
        if lc is not None:
            leaf_hits.setdefault(lc, []).append(t)
            continue
        pc = _parent_class(t)
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
    return any(k in t for k in config.PASTRY_TITLE_KEYWORDS)


# Brownies are filed under Food.com's generic "bar-cookies" leaf, so the
# explicit "brownies" leaf is nearly empty; the title is the reliable signal.
def is_brownie_title(title: str) -> bool:
    """True if the recipe title names a brownie/blondie."""
    t = (title or "").lower()
    return any(k in t for k in config.BROWNIE_TITLE_KEYWORDS)