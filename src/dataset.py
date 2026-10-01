"""The data contract between the two stages.

Stage 1 (``scripts/preprocess.py``) writes ``data/processed/
recipes_simplex.csv`` — one row per kept recipe: identity + tags + url +
structural part grams + 5-part simplex proportions (summing to 1) + flags +
Food.com nutrition. This module defines that schema and is the only way to
load the dataset: both stages import from here, so column conventions cannot
drift between writer and reader.

``load_recipes`` validates the contract and splits off flourless rows (kept =
``flour_g > 0``), returning ``(kept, excluded)``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

from .preprocess import parts

# Structural gram columns (provenance; the decomposition that produced the ratio).
GRAM_COLUMNS = parts.GRAM_COLUMNS

# Columns whose zeros matter before log-ratio transforms: the six structural
# grams that fold into the five ratio parts (liquid = milk + water).
CORE_COLUMNS = ["flour_g", "sugar_g", "fat_g", "egg_g", "milk_g", "water_g"]
SIDE_COLUMNS = ["salt_g", "leavener_g", "yeast_g"]
NUMERIC_COLUMNS = CORE_COLUMNS + SIDE_COLUMNS

# Ratio columns, in ANALYSIS_PARTS order (flour, liquid, egg, fat, sugar).
PROPORTION_COLUMNS = parts.proportion_columns()

REQUIRED_COLUMNS = (
    ["recipe_id", "name", "url", "tag_coarse", "tag_fine"] + NUMERIC_COLUMNS + PROPORTION_COLUMNS
)


def validate_schema(df: pd.DataFrame) -> None:
    """Raise if the dataset violates the contract."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    if df["recipe_id"].duplicated().any():
        raise ValueError("recipe_id column contains duplicates")

    if df[NUMERIC_COLUMNS].isna().any().any():
        raise ValueError("numeric gram columns contain missing values")

    if (df[NUMERIC_COLUMNS] < 0).any().any():
        raise ValueError("numeric gram columns contain negative values")

    P = df[PROPORTION_COLUMNS].to_numpy(dtype=float)
    totals = P.sum(axis=1)
    bad_rows = np.where((totals > 0) & (np.abs(totals - 1.0) > 1e-4))[0]
    if len(bad_rows):
        raise ValueError(
            f"proportion columns do not sum to 1 for {len(bad_rows)} rows "
            f"(example recipe_id {df.iloc[bad_rows[0]]['recipe_id']})")


def load_recipes(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and validate the preprocessed recipe dataset.

    Returns (kept, excluded) where kept has flour_g > 0 and excluded has
    flour_g == 0 (written out for later handling).
    """
    df = pd.read_csv(path)
    validate_schema(df)

    kept = df[df["flour_g"] > 0].reset_index(drop=True)
    excluded = df[df["flour_g"] == 0].reset_index(drop=True)
    return kept, excluded


def provenance_path() -> str:
    """Where stage 1 records the run statistics beside the dataset."""
    return config.PROVENANCE_JSON