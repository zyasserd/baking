"""Fold the 9 tracked ingredient parts into the 5-part analysis simplex.

Each recipe's structural grams (flour, sugar, fat, egg, milk, water, salt,
leavener, yeast) are folded into five analysis parts — flour, liquid, egg,
fat, sugar — and closed (normalized) to sum to 1. Salt, leavener, yeast and
flavor add-ins are deliberately excluded from the ratio, as in Ruhlman's
*Ratio*. The part definitions are parameters — see the COMPOSITION FOLDS
section of ``config``.

This is a stage-1 concern: the proportions are written into the preprocessed
dataset (``*_p`` columns summing to 1) so stage 2 consumes them directly.
Log-ratio transforms (CLR/ILR) live in stage 2 (``src.method.coda``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config

ANALYSIS_PARTS = config.ANALYSIS_PARTS
_PART_SOURCES = config.ANALYSIS_PART_SOURCES

GRAM_COLUMNS = ["flour_g", "sugar_g", "fat_g", "egg_g", "milk_g", "water_g", "salt_g", "leavener_g", "yeast_g"]


def parts_matrix(df: pd.DataFrame) -> np.ndarray:
    """Return an (n, 5) mass matrix [flour, liquid, egg, fat, sugar]."""
    columns = []
    for part in ANALYSIS_PARTS:
        cols = _PART_SOURCES[part]
        columns.append(df[cols].to_numpy(dtype=float).sum(axis=1))
    return np.column_stack(columns)


def proportions(df: pd.DataFrame) -> np.ndarray:
    """Per-recipe simplex proportions over the analysis parts (rows sum to 1).

    Plain closure (no zero-replacement): structural zeros stay zero in the
    dataset; the analysis stage applies multiplicative replacement before the
    log-ratio transforms. Rows with zero total mass stay all-zero.
    """
    M = parts_matrix(df)
    total = M.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        P = np.where(total > 0, M / total, 0.0)
    return P


def proportion_columns() -> list[str]:
    """The ``<part>_p`` column names, in ANALYSIS_PARTS order."""
    return [f"{part}_p" for part in ANALYSIS_PARTS]