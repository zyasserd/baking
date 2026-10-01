"""Tests for the dataset contract (src/dataset.py)."""

import numpy as np
import pandas as pd
import pytest

import config
from src.dataset import (
    CORE_COLUMNS,
    PROPORTION_COLUMNS,
    REQUIRED_COLUMNS,
    load_recipes,
    validate_schema,
)


def make_frame(n: int = 3, flour: float = 100.0, **overrides) -> pd.DataFrame:
    rows = []
    for i in range(n):
        row = {"recipe_id": str(100 + i), "name": f"Recipe {i}",
               "url": f"https://www.food.com/recipe/r-{100 + i}",
               "tag_coarse": "cake", "tag_fine": "cakes",
               "flour_g": flour, "sugar_g": 50.0, "fat_g": 25.0,
               "egg_g": 10.0, "milk_g": 5.0, "water_g": 0.0,
               "salt_g": 1.0, "leavener_g": 2.0, "yeast_g": 0.0}
        for col in PROPORTION_COLUMNS:
            row[col] = 0.2
        rows.append(row)
    df = pd.DataFrame(rows)
    return df.assign(**overrides) if overrides else df


def test_validate_schema_accepts_a_contract_row():
    validate_schema(make_frame())


def test_validate_schema_rejects_missing_columns():
    df = make_frame().drop(columns=[REQUIRED_COLUMNS[0]])
    with pytest.raises(ValueError, match="missing required columns"):
        validate_schema(df)


def test_validate_schema_rejects_duplicate_ids():
    df = make_frame()
    df.loc[1, "recipe_id"] = df.loc[0, "recipe_id"]
    with pytest.raises(ValueError, match="duplicates"):
        validate_schema(df)


def test_validate_schema_rejects_missing_grams():
    df = make_frame()
    df.loc[0, CORE_COLUMNS[0]] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        validate_schema(df)


def test_validate_schema_rejects_negative_grams():
    df = make_frame()
    df.loc[0, "fat_g"] = -1.0
    with pytest.raises(ValueError, match="negative"):
        validate_schema(df)


def test_validate_schema_rejects_unclosed_proportions():
    df = make_frame()
    df.loc[0, PROPORTION_COLUMNS[0]] = 0.5
    with pytest.raises(ValueError, match="sum to 1"):
        validate_schema(df)


def test_load_recipes_splits_off_flourless(tmp_path):
    df = make_frame(n=3)
    df.loc[0, "flour_g"] = 0.0
    path = tmp_path / "recipes.csv"
    df.to_csv(path, index=False)

    kept, excluded = load_recipes(str(path))
    assert len(kept) == 2
    assert len(excluded) == 1
    assert (kept["flour_g"] > 0).all()


def test_committed_dataset_satisfies_contract():
    # The committed dataset is what every result is built on: validate it
    # against the contract (schema, ids, proportions) rather than pinning a
    # brittle hash that breaks on harmless formatting changes.
    kept, excluded = load_recipes(config.PROCESSED_RECIPES_CSV)
    assert len(kept) > 0
    assert not kept["url"].isna().any()