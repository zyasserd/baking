"""STAGE 2 — Analysis pipeline: the preprocessed dataset -> results.

The input is ``data/processed/recipes_simplex.csv`` (written by stage 1): one
row per recipe with structural part grams and 5-part simplex proportions
(summing to 1). The *features* are the ratios; the *labels* are the independent
Food.com tag classes (``tag_coarse``). The book ratios are used only as
reference archetypes, never as labels.

The tag classes are DESCRIBED in ratio space, not predicted: recipes are
placed as balances of the simplex (flour/liquid/egg/fat/sugar — ILR, see
``src.method.coda``), far-out parse errors are gated out, and the classes are
summarized by their separation (mean silhouette of the tag labels; ~0 = the
continuum finding) and the richness ordering by distribution mode. No
clustering, no statistical components. Suspect-recipe diagnostics
(``validate.py``, ``quality.py``) are internal CSVs for the maintainer; the
Aid builder (``src.aid``) recomputes all geometry client-side. Every parameter
lives in ``config`` (ANALYSIS section); the entry point takes no tuning flags.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde
from sklearn.metrics import silhouette_score

import config

from .. import dataset
from ..aid import pack as aid_pack
from ..aid import web as aid_web
from ..preprocess import parts
from . import coda, outliers, quality, validate


def _apply_full_mode(df: pd.DataFrame) -> pd.DataFrame:
    """Swap the structural gram/proportion columns for the pooled add-in ones.

    Reads the ``full_grams`` sidecar stage 1 wrote (see config
    DECOMPOSITION_MODE) — the losing convention from the comparison that chose
    the structural decomposition, kept reproducible rather than folklore.
    """
    if not os.path.exists(config.FULL_GRAMS_CSV):
        raise SystemExit(
            f"DECOMPOSITION_MODE=full needs {config.FULL_GRAMS_CSV} — "
            "re-run scripts/preprocess.py once"
        )
    grams_cols = [f"{p}_g" for p in config.INGREDIENT_PARTS]
    full = pd.read_csv(config.FULL_GRAMS_CSV, dtype={"recipe_id": str})
    df = df.copy()
    df["recipe_id"] = df["recipe_id"].astype(str)
    df = df.drop(columns=grams_cols + parts.proportion_columns())
    df = df.merge(full, on="recipe_id", how="left")
    df[grams_cols] = df[grams_cols].fillna(0.0)
    df[parts.proportion_columns()] = parts.proportions(df)
    return df


def mode_estimate(values: np.ndarray) -> float:
    """The peak of the distribution's KDE — where the class bulges the most.

    The richness distributions are skewed, so their mean sits in the tail; the
    KDE mode is the honest "typical value" for ordering the classes.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return float("nan")
    if len(np.unique(values)) < 2:
        return float(values[0])
    grid = np.linspace(values.min(), values.max(), 512)
    return float(grid[np.argmax(gaussian_kde(values)(grid))])


def describe(df: pd.DataFrame, outdir: str) -> dict:
    """Gate outliers, write diagnostics, and describe the tag classes."""
    # Recipes -> simplex proportions (already closed by stage 1) -> balances.
    P = df[parts.proportion_columns()].to_numpy(dtype=float)
    P = coda.multiplicative_replacement(coda.closure(P))
    ilr = coda.ilr(P)

    inliers = outliers.detect_outliers(ilr)
    validate.write_envelope_outliers(df, ilr, inliers, outdir)
    df = df[inliers].reset_index(drop=True)
    ilr = ilr[inliers]

    # Internal diagnostics (CSV only): per class, the recipes farthest from
    # the class centroid — the maintainer's loop for finding stage-1 bugs.
    validate.write_extremes(df, ilr, outdir)

    # Manual axis (no statistical component): richness = fat + sugar share, in
    # percent of the composition. The ordering uses the distribution MODE
    # (where the class bulges) — the mean sits in the skew tail.
    richness = (df["fat_p"] + df["sugar_p"]) * 100.0
    richness_order = tuple(
        df.assign(richness=richness).groupby("tag_coarse")["richness"]
        .apply(lambda v: mode_estimate(v.to_numpy()))
        .sort_values().index)

    # Tag-class separation in ratio space: mean silhouette of the tag labels
    # over all recipes (no clustering involved; ~0 = the continuum finding).
    separation = silhouette_score(
        ilr, df["tag_coarse"].to_numpy(),
        sample_size=min(len(ilr), config.SILHOUETTE_SAMPLE_MAX),
        random_state=config.RANDOM_SEED)

    print(f"\n===== structural simplex ({len(df)} recipes) =====")
    print("Class distribution:")
    for name, count in df["tag_coarse"].value_counts().items():
        print(f"  {name:<12} {count}")
    print("\nClass ordering by richness (fat + sugar share), lean -> rich:")
    for name in richness_order:
        print(f"  {name}")
    print(f"\nTag-class separation (mean silhouette): {separation:.3f}")
    return {"n": int(len(df)), "richness_order": richness_order,
            "separation": float(separation)}


def run(input_csv: str, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)

    df_all, excluded = dataset.load_recipes(input_csv)
    excluded.to_csv(os.path.join(outdir, "excluded_flourless.csv"), index=False)
    print(f"Loaded {len(df_all)} recipes ({len(excluded)} flourless rows excluded).")

    # Standing data-quality report (unresolved-heads queue + basis shares).
    quality.write_reports(outdir)

    # The Aid is a browser, not an analysis: it gets the FULL loaded dataset
    # minus the weak-tier dessert_other family, which is not user-facing. The
    # method's gates (decomposition mode, weak tier, confidence) apply to the
    # description below only; the two never share a filtered frame.
    aid_df = df_all[df_all["tag_coarse"] != "dessert_other"].reset_index(drop=True)
    print(f"Aid: {len(aid_df)} recipes ({len(df_all) - len(aid_df)} dessert_other hidden).")
    df = df_all
    if config.DECOMPOSITION_MODE == "full":
        df = _apply_full_mode(df)
        print("Decomposition: FULL (add-ins pooled in)")

    if config.DROP_WEAK_TIER:
        dropped = (df["tag_coarse"] == "dessert_other").sum()
        df = df[df["tag_coarse"] != "dessert_other"].reset_index(drop=True)
        print(f"Dropped {int(dropped)} dessert_other (weak-tier) recipes.")

    if config.MIN_TAG_CONFIDENCE:
        order = {"strong": 0, "medium": 1, "weak": 2}
        keep = df["tag_confidence"].map(lambda c: order.get(c, 2) <= order[config.MIN_TAG_CONFIDENCE])
        print(f"Dropped {int((~keep).sum())} recipes below confidence {config.MIN_TAG_CONFIDENCE}.")
        df = df[keep].reset_index(drop=True)

    metrics = describe(df, outdir)

    # Product: compile the data, then pack web/ + data into the single HTML.
    data_js = aid_web.build_data(aid_df, outdir)
    html_path = aid_pack.pack(outdir)
    print(f"\nWrote {data_js} ({os.path.getsize(data_js) / 1e6:.1f} MB)")
    print(f"Wrote {html_path} ({os.path.getsize(html_path) / 1e6:.1f} MB) — the Aid")
    return metrics