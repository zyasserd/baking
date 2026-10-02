"""Compile the dataset into ``data.js`` — the Aid's input data.

Everything the Aid needs to render and search is packed here, once, in a
deterministic order:

- ``recipes`` — parallel arrays (id, name, url, class, 5-part shares rounded
  to 4 decimals). ALL loaded recipes: the Aid is a browser, not an analysis;
  filtering happens client-side. Shares come straight from the dataset
  contract columns, so the data.js is reproducible from the committed
  dataset alone.
- ``heads`` + ``index`` — the ingredient-search index: the distinct parsed
  ingredient heads (sorted) and, per head, the sorted positions of the
  recipes listing it. Parsed from the dataset's own ``ingredients_raw`` column
  (the Food.com names), so the Aid rebuilds from the committed dataset alone —
  no stage-1 interim file required.
- ``archetypes`` — the book ratios as closed shares, projected identically
  to recipes in every partition.
- ``percentiles`` — per class and part, the p05/p25/p50/p75/p95 of the share
  (the ratio card's "where does this recipe sit in its class").
- ``meta`` — part names, class list, and stage-1 provenance (the About
  view's numbers, read from ``config.PROVENANCE_JSON``).
"""

from __future__ import annotations

import ast
import json
import os

import numpy as np
import pandas as pd

import config

from ..method import folds


def _recipes(df: pd.DataFrame) -> dict:
    from ..dataset import PROPORTION_COLUMNS

    P = df[PROPORTION_COLUMNS].to_numpy(dtype=float)
    P = np.round(P, 4)
    return {
        "id": df["recipe_id"].tolist(),
        "name": df["name"].tolist(),
        "url": ["https://" + u if not str(u).startswith("http") else u
                for u in df["url"]],
        "cls": df["tag_coarse"].tolist(),
        "P": P.tolist(),
    }


def _literal_list(value: object) -> list[str]:
    """Parse the dataset's stringified ingredient list; [] on anything odd."""
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return [str(parsed)]


def _ingredient_index(df: pd.DataFrame) -> tuple[list[str], dict[str, list[int]]]:
    """Distinct heads (sorted) and, per head, the positions of recipes listing it.

    Built from the dataset's own ``ingredients_raw`` column (the Food.com
    ingredient names), so the Aid regenerates from the committed dataset alone —
    no stage-1 interim file. Each line is normalized by the same parser stage 1
    used (``src.preprocess.parse``), so preparation words drop and spelling
    variants merge (``"firmly packed brown sugar"`` -> ``"brown sugar"``).

    Positions refer to the recipe arrays' order, so index lists stay small
    integers and the search is a pure set intersection in the browser. Heads
    with no visible recipe are dropped — a suggestion that matches nothing is
    worse than no suggestion.
    """
    from ..preprocess import parse

    if "ingredients_raw" not in df.columns:
        return [], {}

    bucket: dict[str, set[int]] = {}
    for i, raw in enumerate(df["ingredients_raw"]):
        for line in _literal_list(raw):
            head = parse.parse_ingredient(line).head
            if head:
                bucket.setdefault(head, set()).add(i)

    index = {head: sorted(rows) for head, rows in bucket.items()}
    return sorted(index), index


def _archetypes() -> list[dict]:
    matrix, names = folds.archetype_matrix()
    shares = matrix / matrix.sum(axis=1, keepdims=True)
    return [{"name": n, "P": np.round(s, 6).tolist()}
            for n, s in zip(names, shares)]


def _percentiles(df: pd.DataFrame) -> dict:
    from ..dataset import PROPORTION_COLUMNS

    out: dict[str, dict[str, list[float]]] = {}
    quantiles = [0.05, 0.25, 0.50, 0.75, 0.95]
    part_names = ["flour", "liquid", "egg", "fat", "sugar"]  # bare, for the JS side
    for cls, group in df.groupby("tag_coarse", sort=True):
        P = group[PROPORTION_COLUMNS].to_numpy(dtype=float)
        out[cls] = {
            name: [round(float(q), 4) for q in np.quantile(P[:, j], quantiles)]
            for j, name in enumerate(part_names)
        }
    return out


def _provenance() -> dict:
    if not os.path.exists(config.PROVENANCE_JSON):
        return {}
    with open(config.PROVENANCE_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def build_data(df: pd.DataFrame, outdir: str) -> str:
    """Write ``<outdir>/aid/data.js`` (``AID_DATA = {...}``) and return its path."""
    from ..dataset import PROPORTION_COLUMNS

    heads, index = _ingredient_index(df)
    data = {
        "meta": {
            "parts": PROPORTION_COLUMNS,
            "partNames": ["flour", "liquid", "egg", "fat", "sugar"],
            "classes": sorted(df["tag_coarse"].unique().tolist()),
            "n": int(len(df)),
            "provenance": _provenance(),
        },
        "recipes": _recipes(df),
        "heads": heads,
        "index": index,
        "archetypes": _archetypes(),
        "percentiles": _percentiles(df),
    }
    # "\/" keeps a literal "</script>" in recipe names from terminating the
    # inline <script> tag (valid JSON escape, decoded transparently).
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")

    aid_dir = os.path.join(outdir, "aid")
    os.makedirs(aid_dir, exist_ok=True)
    path = os.path.join(aid_dir, "data.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("AID_DATA = ")
        fh.write(payload)
        fh.write(";\n")
    return path