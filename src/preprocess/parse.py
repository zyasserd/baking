"""Parse a raw ingredient string into a standard form.

An ingredient line like ``"1/2 cup firmly packed brown sugar"`` or
``"1 (8 oz.) pkg. cream cheese, softened"`` is reduced to::

    Parsed(qty=0.5, unit="cup", head="brown sugar", props=["firmly","packed"],
           note="8 oz.", raw=...)

``head`` is the canonical ingredient (prep adjectives stripped, compositional
modifiers kept), ``props`` are the preparation descriptors, and ``note`` carries
parenthetical size hints / qualifiers. Amount/unit parsing (fractions, mangled
slashes, package sizes) is delegated to ``src.preprocess.units``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import units

# Preparation/quantity descriptors stripped from the head (moved to `props`).
# Compositional modifiers ("brown", "powdered", "whole wheat", "unsweetened",
# "self-rising", "skim", "heavy", "sour", ...) are intentionally NOT listed here.
_PREP_PROPS = frozenset({
    "chopped", "minced", "diced", "sliced", "grated", "shredded", "crushed",
    "melted", "softened", "beaten", "divided", "optional", "peeled", "drained",
    "rinsed", "sifted", "packed", "halved", "quartered", "cubed", "julienned",
    "mashed", "pureed", "ground", "finely", "roughly", "thinly", "coarsely",
    "firmly", "lightly", "well", "seeded", "cored", "trimmed", "washed",
    "toasted", "thawed", "cooked", "boneless", "skinless", "lean", "frozen",
    "canned", "fresh", "dried", "extra", "virgin", "room", "temperature", "to",
    "taste", "large", "medium", "small", "unseasoned", "seasoned", "prepared",
    "smoked", "unsalted", "salted", "plain", "nonfat", "reduced", "low",
    # Water temperature descriptors ("boiling water") — deliberately NOT "hot"
    # ("hot cross buns" is a dish, not a prep step).
    "boiling", "lukewarm", "warm",
    # NER leakage: connective/adverb fragments left in heads ("butter cut into",
    # "dates pitted organic into", "freshly pecorino romano cheese",
    # "slightly egg whites").
    "into", "cut", "freshly", "slightly",
})

# Stray unit/measure words that leak into the name when the amount carries a
# parenthetical size ("1 (8 oz.) pkg. cream cheese" -> head "cream cheese").
_UNIT_WORDS = frozenset({
    "pkg", "package", "packages", "packet", "packets", "can", "jar", "bottle",
    "bottles", "box", "boxes", "bag", "bags", "container", "containers",
    "stick", "sticks", "envelope", "envelopes", "drop",
    "drops", "slice", "slices", "piece", "pieces",
})

# Multi-component recipes (a coffee cake = streusel + filling + batter) keep
# their section headers as quantity-less lines in the flattened ingredient
# list ("Streusel Topping", "Cream Cheese Filling", "for the glaze:").
_COMPONENT_KIND_RE = (
    r"toppings?|fillings?|streusel|crusts?|batters?|glazes?|icings?"
    r"|frostings?|doughs?|mixtures?|layers?|coatings?|ganache|drizzles?|crumbs?"
)

# Sections whose ingredients never bake into the crumb (they are spread on
# after baking or are pure decorations): their mass must not be pooled into
# the batter's ratio. Everything else (streusel, filling, crust, dough, ...)
# bakes with the recipe and stays pooled.
_NONBAKED_KINDS = frozenset({
    "glaze", "glazes", "icing", "icings", "frosting", "frostings",
    "ganache", "drizzle", "drizzles", "coating", "coatings",
})

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_WORD_RE = re.compile(r"[a-z0-9]+")

_COMPONENT_RE = re.compile(
    r"^(?:for\s+(?:the|a)\s+)?(?:[a-z][a-z' ]{0,30}?\s+)?"
    r"(?P<kind>" + _COMPONENT_KIND_RE + r")"
    r"\s*:?\s*$",
    re.IGNORECASE,
)


@dataclass
class Parsed:
    qty: float | None
    unit: str | None
    head: str
    props: list[str] = field(default_factory=list)
    note: str | None = None
    raw: str = ""
    # Quantity ranges ("1 1/2 - 2 cups"): the resolved endpoints; ``qty`` is
    # the midpoint. Both None when the quantity is not a range.
    qty_low: float | None = None
    qty_high: float | None = None


def _resolve_or(name: str) -> str:
    """``"butter or margarine"`` -> ``"butter"`` (the first listed arm)."""
    lowered = name.lower()
    if " or " in lowered:
        return name[: lowered.find(" or ")].strip()
    return name


def _strip_props(name: str) -> tuple[str, list[str]]:
    """Split prep descriptors from the canonical head."""
    kept: list[str] = []
    props: list[str] = []
    for chunk in name.split(","):
        # Lowercase before tokenizing: the word regex is lowercase-only, and
        # capitalized names ("French bread", brand names) would otherwise
        # lose their first letter(s).
        for token in _WORD_RE.findall(chunk.lower()):
            if token in _PREP_PROPS or token in _UNIT_WORDS:
                props.append(token)
            else:
                kept.append(token)
    head = " ".join(kept).strip()
    # Stray connective left when a container word moved to props
    # ("box of X" -> "of X"). Only leading; "cream of tartar" keeps its "of".
    if head.startswith("of "):
        head = head[3:]
    return head, props


def component_header(line: str) -> str | None:
    """Classify a quantity-less line as a recipe section header.

    Returns ``"drop"`` for non-baked sections (frosting, glaze, icing, ...),
    ``"keep"`` for baked sections (streusel, filling, crust, batter, ...), or
    ``None`` when the line is not a header. Headers in the corpus are Title
    Case, ALL CAPS, or prefixed ``"for the"``; a bare lowercase ingredient
    (``"tabasco sauce"``) is never mistaken for one.
    """
    s = (line or "").strip()
    if not s or units.parse_ingredient_amount(s)[0] is not None:
        return None
    m = _COMPONENT_RE.match(s)
    if m is None:
        return None
    if not (s.lower().startswith(("for the", "for a")) or s == s.title() or s.isupper()):
        return None
    if m.group("kind").lower() in _NONBAKED_KINDS or "whipped" in s.lower():
        return "drop"
    return "keep"


def parse_ingredient(s: str) -> Parsed:
    raw = s or ""
    qty, unit, qty_low, qty_high = units.parse_amount_span(raw)
    name = units.strip_amount(raw).strip()

    # Parentheticals (size hints, qualifiers) -> note.
    notes = [m.strip() for m in _PAREN_RE.findall(name)]
    name = _PAREN_RE.sub(" ", name)

    # Stray connective left after the amount is stripped ("box of X" ->
    # "of X" once "box" moves to props).
    name = re.sub(r"^of\s+", "", name, flags=re.IGNORECASE)

    name = _resolve_or(name)
    head, props = _strip_props(name)

    return Parsed(
        qty=qty,
        unit=unit,
        head=head,
        props=props,
        note="; ".join(notes) if notes else None,
        raw=raw,
        qty_low=qty_low,
        qty_high=qty_high,
    )