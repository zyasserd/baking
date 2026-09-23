"""Validate the decomposition against Food.com's per-serving nutrition.

The estimated part masses (``fat_g``, ``sugar_g``) are independent of the tags;
Food.com provides per-serving *percent daily value* columns (``nutrition_fat``,
``nutrition_sugar``). Although the units differ (total recipe grams vs. per-
serving PDV), they should still *rank* recipes similarly if the decomposition is
sane, so we report Spearman correlations — overall and per class — to catch
systematic errors (e.g. a systematic under/over-count of sugar from fruit or
condensed milk).
"""

from __future__ import annotations

import argparse
import os

import pandas as pd
from scipy.stats import spearmanr


def correlate(a: pd.Series, b: pd.Series) -> float:
    x = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(x) < 20:
        return float("nan")
    return float(spearmanr(x["a"], x["b"]).statistic)


def main() -> None:
    parser = argparse.ArgumentParser(description="Decomposition vs nutrition validation.")
    parser.add_argument("--input", default="data/recipes_tagged.csv")
    parser.add_argument("--outdir", default="output")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    rows = []

    def add(label: str, sub: pd.DataFrame) -> None:
        rows.append(
            {
                "group": label,
                "n": len(sub),
                "fat_spearman": correlate(sub["fat_g"], sub["nutrition_fat"]),
                "sugar_spearman": correlate(sub["sugar_g"], sub["nutrition_sugar"]),
                "sugar_vs_carbs_spearman": correlate(sub["sugar_g"], sub["nutrition_carbs"]),
            }
        )

    add("overall", df)
    df_primary = df[df["tag_coarse"] != "dessert_other"]
    for cls, sub in df_primary.groupby("tag_coarse"):
        add(cls, sub)

    report = pd.DataFrame(rows)
    os.makedirs(args.outdir, exist_ok=True)
    out = os.path.join(args.outdir, "nutrition_validation.csv")
    report.to_csv(out, index=False)

    print("Decomposition vs nutrition (Spearman rank correlation):")
    print(report.to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()