"""Diagnostics for the preprocessed dataset — independent checks, not metrics.

``title_agreement``: for each tag class, how many recipe titles contain a
class-defining keyword (``config.VALIDATION_TITLE_KEYWORDS``) — the labels come
from tags, so titles are an independent source to eyeball against.

``nutrition_correlations``: the estimated structural grams should correlate
with Food.com's per-serving nutrition (supplied by the platform, NOT used in
the decomposition): fat vs fat_g, sugar vs sugar_g, carbs vs flour+sugar
grams. Spearman correlations per class (and overall).

These reports are part of stage 2's output (``validate.write_reports``); they
are diagnostics only — nothing downstream uses them.
"""

from __future__ import annotations

import os
import random

import pandas as pd
from scipy.stats import spearmanr

import config


def title_agreement(df: pd.DataFrame) -> pd.DataFrame:
    """Per class: fraction of titles containing a class-defining keyword."""
    rows = []
    for cls in config.CLASS_PRIORITY:
        sub = df[df["tag_coarse"] == cls]
        if len(sub) == 0:
            continue
        keywords = config.VALIDATION_TITLE_KEYWORDS.get(cls, ())
        hit = sub["name"].str.lower().apply(lambda t: any(k in t for k in keywords))
        rows.append(
            {
                "class": cls,
                "n": len(sub),
                "title_agreement": round(float(hit.mean()), 3) if len(sub) else None,
                "n_matching_title": int(hit.sum()),
            }
        )
    return pd.DataFrame(rows)


def title_samples(df: pd.DataFrame, n_samples: int, seed: int = config.RANDOM_SEED) -> pd.DataFrame:
    """Random sample of recipes per class for eyeballing."""
    rng = random.Random(seed)
    samples = []
    for cls in config.CLASS_PRIORITY:
        sub = df[df["tag_coarse"] == cls]
        if len(sub) == 0:
            continue
        idx = rng.sample(range(len(sub)), min(n_samples, len(sub)))
        for i in idx:
            r = sub.iloc[i]
            samples.append({"class": cls, "name": r["name"], "tag_fine": r["tag_fine"],
                            "confidence": r["tag_confidence"]})
    return pd.DataFrame(samples)


# (check name, estimated-mass column(s), nutrition column)
_NUTRITION_CHECKS = [
    ("fat_g vs nutrition_fat", ["fat_g"], "nutrition_fat"),
    ("sugar_g vs nutrition_sugar", ["sugar_g"], "nutrition_sugar"),
    ("flour+sugar vs nutrition_carbs", ["flour_g", "sugar_g"], "nutrition_carbs"),
]


def _spearman(x: pd.Series, y: pd.Series) -> float:
    if len(x) < config.VALIDATION_MIN_ROWS:
        return float("nan")
    rho = spearmanr(x, y)
    return float(rho.statistic)


def nutrition_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlation of estimated structural mass vs Food.com nutrition."""
    rows = []
    for name, est_cols, nut_col in _NUTRITION_CHECKS:
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


def write_reports(df: pd.DataFrame, outdir: str) -> None:
    """Write tag_validation.{csv,txt}, tag_samples.csv and nutrition_validation.csv."""
    agreement = title_agreement(df)
    agreement.to_csv(os.path.join(outdir, "tag_validation.csv"), index=False)
    samples = title_samples(df, config.VALIDATION_SAMPLE_ROWS)
    samples.to_csv(os.path.join(outdir, "tag_samples.csv"), index=False)

    lines = ["Tag validation: title agreement per class", ""]
    for _, row in agreement.iterrows():
        lines.append(f"  {row['class']:<13} n={row['n']:<6} title agreement={row['title_agreement']}")
    lines.append("")
    lines.append("Random samples per class for eyeballing:")
    for cls in config.CLASS_PRIORITY:
        sub = samples[samples["class"] == cls]
        if len(sub) == 0:
            continue
        lines.append(f"\n[{cls}]")
        for _, r in sub.iterrows():
            lines.append(f"  - {r['name']}  (tag_fine={r['tag_fine']}, confidence={r['confidence']})")
    with open(os.path.join(outdir, "tag_validation.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    nut = nutrition_correlations(df)
    nut.to_csv(os.path.join(outdir, "nutrition_validation.csv"), index=False)
    print("Tag title agreement:")
    print(agreement.to_string(index=False))
    print("Nutrition correlations:")
    print(nut.to_string(index=False))