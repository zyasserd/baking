"""Validate the estimated part masses against Food.com per-recipe nutrition.

The Food.com nutrition (per serving, supplied by the platform — NOT used in the
decomposition) should correlate with our estimated structural grams: fat vs
fat_g, sugar vs sugar_g, carbs vs flour+sugar grams. Spearman correlations per
class (and overall) are written to ``output/nutrition_validation.csv``.

This is a *diagnostic*; nothing downstream uses it.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from scipy.stats import spearmanr

import config

# (check name, estimated-mass column(s), nutrition column)
_CHECKS = [
    ("fat_g vs nutrition_fat", ["fat_g"], "nutrition_fat"),
    ("sugar_g vs nutrition_sugar", ["sugar_g"], "nutrition_sugar"),
    ("flour+sugar vs nutrition_carbs", ["flour_g", "sugar_g"], "nutrition_carbs"),
]


def _spearman(x: pd.Series, y: pd.Series) -> float:
    if len(x) < config.VALIDATION_MIN_ROWS:
        return float("nan")
    rho = spearmanr(x, y)
    return float(rho.statistic)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, est_cols, nut_col in _CHECKS:
        est = df[est_cols].sum(axis=1)
        rows.append({
            "class": "ALL",
            "check": name,
            "spearman": round(_spearman(est, df[nut_col]), 3),
        })
        for cls in config.CLASS_PRIORITY:
            sub = df[df["tag_coarse"] == cls]
            if len(sub) == 0:
                continue
            rows.append({
                "class": cls,
                "check": name,
                "spearman": round(_spearman(est[sub.index], sub[nut_col]), 3),
            })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate decomposition vs nutrition correlations.")
    parser.add_argument("--input", default=config.PROCESSED_RECIPES_CSV, help="Preprocessed dataset path")
    parser.add_argument("--outdir", default=config.OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    os.makedirs(args.outdir, exist_ok=True)

    report = validate(df)
    report.to_csv(os.path.join(args.outdir, "nutrition_validation.csv"), index=False)
    print(report.to_string(index=False))
    print(f"wrote {args.outdir}/nutrition_validation.csv")


if __name__ == "__main__":
    main()