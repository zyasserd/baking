"""Parse a raw ingredient string into a standard form.

An ingredient line like ``"1/2 cup firmly packed brown sugar"`` or
``"1 (8 oz.) pkg. cream cheese, softened"`` is reduced to::

    Parsed(qty=0.5, unit="cup", head="brown sugar", props=["firmly","packed"],
           note="8 oz.", raw=...)

``head`` is the canonical ingredient (prep adjectives stripped, compositional
modifiers kept), ``props`` are the preparation descriptors, and ``note`` carries
parenthetical size hints / qualifiers. Amount/unit parsing (fractions, mangled
slashes, package sizes) is delegated to ``src.preprocess.units``.

The word tables and the section-header regex are parameters — see the PARSING
section of ``config``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import config

from . import units

_PREP_PROPS = config.PARSE_PREP_PROPS
_UNIT_WORDS = config.PARSE_UNIT_WORDS
_NONBAKED_KINDS = config.PARSE_NONBAKED_KINDS

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Multi-component recipes (a coffee cake = streusel + filling + batter) keep
# their section headers as quantity-less lines in the flattened ingredient
# list ("Streusel Topping", "Cream Cheese Filling", "for the glaze:").
_COMPONENT_RE = re.compile(
    r"^(?:for\s+(?:the|a)\s+)?(?:[a-z][a-z' ]{0,30}?\s+)?"
    r"(?P<kind>" + config.PARSE_COMPONENT_KIND_RE + r")"
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
    qty, unit = units.parse_ingredient_amount(raw)
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
    )