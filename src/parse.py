"""Parse a raw ingredient string into a standard form.

An ingredient line like ``"1/2 cup firmly packed brown sugar"`` or
``"1 (8 oz.) pkg. cream cheese, softened"`` is reduced to::

    Parsed(qty=0.5, unit="cup", head="brown sugar", props=["firmly","packed"],
           note="8 oz.", raw=...)

``head`` is the canonical ingredient (prep adjectives stripped, compositional
modifiers kept), ``props`` are the preparation descriptors, and ``note`` carries
parenthetical size hints / qualifiers. Amount/unit parsing (fractions, mangled
slashes, package sizes) is delegated to ``src.units``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import units

# Preparation/quantity descriptors stripped from the head (moved to ``props``).
# Compositional modifiers ("brown", "powdered", "whole wheat", "unsweetened",
# "self-rising", "skim", "heavy", "sour", …) are intentionally NOT listed here.
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
})

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Stray unit/measure words that leak into the name when the amount carries a
# parenthetical size ("1 (8 oz.) pkg. cream cheese" -> head "cream cheese").
_UNIT_WORDS = frozenset({
    "pkg", "package", "packages", "packet", "packets", "can", "jar", "bottle",
    "bottles", "box", "boxes", "bag", "bags", "container", "containers",
    "stick", "sticks", "envelope", "envelopes", "dash", "pinch", "drop",
    "drops", "slice", "slices", "piece", "pieces",
})


@dataclass
class Parsed:
    qty: float | None
    unit: str | None
    head: str
    props: list[str] = field(default_factory=list)
    note: str | None = None
    raw: str = ""


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
        for token in _WORD_RE.findall(chunk):
            if token in _PREP_PROPS or token in _UNIT_WORDS:
                props.append(token)
            else:
                kept.append(token)
    return " ".join(kept).strip(), props


def parse_ingredient(s: str) -> Parsed:
    raw = s or ""
    qty, unit = units.parse_ingredient_amount(raw)
    name = units.strip_amount(raw).strip()

    # Parentheticals (size hints, qualifiers) -> note.
    notes = [m.strip() for m in _PAREN_RE.findall(name)]
    name = _PAREN_RE.sub(" ", name)

    name = _resolve_or(name)
    head, props = _strip_props(name)

    return Parsed(
        qty=qty,
        unit=unit,
        head=head,
        props=props,
        note="; ".join(notes) if notes else None,
        raw=raw,
    )
