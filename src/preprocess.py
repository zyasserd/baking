"""Loading, validation, and the closure/zero-replacement/CLR transforms."""

from __future__ import annotations

import numpy as np
import pandas as pd

CORE_COLUMNS = ["flour_g", "sugar_g", "fat_g", "egg_g", "milk_g", "water_g"]
SIDE_COLUMNS = ["salt_g", "leavener_g", "yeast_g"]
NUMERIC_COLUMNS = CORE_COLUMNS + SIDE_COLUMNS
REQUIRED_COLUMNS = ["recipe_id", "name", "family"] + NUMERIC_COLUMNS


def closure(X: np.ndarray) -> np.ndarray:
    """Normalize each row of X to sum to 1 (map recipes onto the simplex)."""
    X = np.asarray(X, dtype=float)
    row_sums = X.sum(axis=1, keepdims=True)
    if np.any(row_sums <= 0):
        raise ValueError("closure: every row must have a positive sum")
    return X / row_sums


def multiplicative_replacement(P: np.ndarray) -> np.ndarray:
    """Replace zeros with a per-row delta and re-normalize.

    For each row, delta = 0.5 * min(positive values in the row). Every zero is
    set to delta, then the row is re-normalized to sum to 1 (multiplicative
    replacement as in Martin-Fernandez et al.).
    """
    P = np.asarray(P, dtype=float).copy()
    if np.any(P < 0):
        raise ValueError("multiplicative_replacement: proportions must be >= 0")

    zeros = P == 0
    # min positive per row (rows with no zeros get +inf delta, which is unused)
    min_positive = np.where(P > 0, P, np.inf).min(axis=1, keepdims=True)
    delta = 0.5 * min_positive

    P = np.where(zeros, delta, P)
    return P / P.sum(axis=1, keepdims=True)


def clr(P: np.ndarray) -> np.ndarray:
    """Centered log-ratio transform (rows -> zero-sum log space)."""
    P = np.asarray(P, dtype=float)
    if np.any(P <= 0):
        raise ValueError("clr: proportions must be strictly positive (apply replacement first)")
    log_P = np.log(P)
    return log_P - log_P.mean(axis=1, keepdims=True)


def load_recipes(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and validate the recipe CSV.

    Returns (kept, excluded) where kept has flour_g > 0 and excluded has
    flour_g == 0 (to be written out for later handling).
    """
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    if df["recipe_id"].duplicated().any():
        raise ValueError("recipe_id column contains duplicates")

    if df[NUMERIC_COLUMNS].isna().any().any():
        raise ValueError("numeric gram columns contain missing values")

    if (df[NUMERIC_COLUMNS] < 0).any().any():
        raise ValueError("numeric gram columns contain negative values")

    kept = df[df["flour_g"] > 0].reset_index(drop=True)
    excluded = df[df["flour_g"] == 0].reset_index(drop=True)
    return kept, excluded


def build_clr_matrix(df: pd.DataFrame) -> np.ndarray:
    """Run the full simplex transform on the core ingredient columns."""
    X = df[CORE_COLUMNS].to_numpy(dtype=float)
    P = closure(X)
    P = multiplicative_replacement(P)
    return clr(P)
