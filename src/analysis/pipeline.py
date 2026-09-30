"""STAGE 2 — Analysis pipeline: the preprocessed dataset -> results.

The input is ``data/processed/recipes_simplex.csv`` (written by stage 1): one
row per recipe with structural part grams and 5-part simplex proportions
(summing to 1). The *features* are the ratios; the *labels* are the independent
Food.com tag classes (``tag_coarse``). The book ratios are used only as
reference archetypes, never as labels.

The tag classes are DESCRIBED in ratio space, not predicted: recipes are
placed as balances of the simplex (flour/liquid/egg/fat/sugar — ILR, see
``src.analysis.coda``), far-out parse errors are gated out, and the classes
are summarized by a hand-picked manual axis (richness = fat + sugar share,
sorted by distribution mode), per-class centroids in the simplexes, and their
separation (mean silhouette of the tag labels; ~0 = the continuum finding).
No clustering, no statistical components. Suspect-recipe diagnostics
(``validate.py``) are internal CSVs, not report content. Every parameter
lives in ``config`` (ANALYSIS section); the entry point takes no tuning flags.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score

import config

from ..preprocess import parts
from . import coda, folds, outliers, quality, validate
from . import report as html_report


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


def analyze(df: pd.DataFrame, outdir: str) -> dict:
    # Recipes -> simplex proportions (already closed by stage 1) -> balances.
    P = df[parts.proportion_columns()].to_numpy(dtype=float)
    P = coda.multiplicative_replacement(coda.closure(P))
    ilr = coda.ilr(P)
    comp = df.copy()

    inliers = outliers.detect_outliers(ilr)
    validate.write_envelope_outliers(df, ilr, inliers, outdir)
    df = df[inliers].reset_index(drop=True)
    ilr = ilr[inliers]
    comp = comp[inliers].reset_index(drop=True)

    # Internal diagnostics (CSV only): per class, the recipes farthest from
    # the class centroid — the maintainer's loop for finding stage-1 bugs.
    validate.write_extremes(df, ilr, outdir)

    arch_names, arch_ilr = folds.archetype_ilr()
    nearest, distance = folds.nearest_archetype(ilr, arch_names, arch_ilr)
    # df feeds the HTML hover (via the viz subset); comp is the CSV export.
    df["nearest_archetype"] = nearest
    df["aitchison_distance"] = distance
    comp["nearest_archetype"] = nearest
    comp["aitchison_distance"] = distance
    comp.to_csv(os.path.join(outdir, "compositions.csv"), index=False)

    # Manual axis (no statistical component): richness = fat + sugar share, in
    # percent of the composition. The violin and the ordering sort by the
    # distribution MODE (where the class bulges) — the mean sits in the skew tail.
    rich = pd.DataFrame({
        "tag_coarse": df["tag_coarse"],
        "richness": (df["fat_p"] + df["sugar_p"]) * 100.0,
    })
    rich_summary = rich.groupby("tag_coarse")["richness"].agg(
        mean="mean", std="std", count="size")
    rich_summary["mode"] = [html_report.mode_estimate(rich.loc[rich["tag_coarse"] == cls, "richness"])
                            for cls in rich_summary.index]
    rich_summary.sort_values("mode").to_csv(
        os.path.join(outdir, "class_richness_summary.csv"))
    richness_order = tuple(rich_summary.sort_values("mode").index)

    n = len(df)
    if config.VIZ_SAMPLE_MAX > 0 and config.VIZ_SAMPLE_MAX < n:
        rng = np.random.default_rng(config.RANDOM_SEED)
        idx = np.sort(rng.choice(n, size=config.VIZ_SAMPLE_MAX, replace=False))
        viz_df = df.iloc[idx].reset_index(drop=True)
        viz_ilr = ilr[idx]
    else:
        viz_df = df
        viz_ilr = ilr

    tetra = folds.tetrahedron_matrix(viz_df)
    tetra_coords = folds.barycentric_3d(tetra)
    arch_tetra = folds.barycentric_3d(folds.tetrahedron_archetypes())

    # Tag-class separation in ratio space: mean silhouette of the tag labels
    # over all recipes (no clustering involved; ~0 = the continuum finding).
    true = viz_df["tag_coarse"].to_numpy()
    separation = silhouette_score(
        viz_ilr, true, sample_size=min(len(viz_ilr), config.SILHOUETTE_SAMPLE_MAX)
    )

    metrics: dict = {"n": int(len(df)), "richness_order": richness_order,
                     "separation": separation}

    # One self-contained HTML page replaces every standalone figure.
    html_report.write_html(
        outdir, viz_df, viz_ilr, arch_names, arch_tetra, tetra_coords, metrics,
    )
    return metrics


def report(df: pd.DataFrame, outdir: str) -> dict:
    print(f"\n===== structural simplex ({len(df)} recipes) =====")
    print("Class distribution:")
    for name, count in df["tag_coarse"].value_counts().items():
        print(f"  {name:<12} {count}")

    metrics = analyze(df, outdir)
    print("\nClass ordering by richness (fat + sugar share), lean -> rich:")
    for name in metrics["richness_order"]:
        print(f"  {name}")
    print(f"\nTag-class separation (mean silhouette): {metrics['separation']:.3f}")
    return metrics


def run(input_csv: str, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)

    df, excluded = coda.load_recipes(input_csv)
    excluded.to_csv(os.path.join(outdir, "excluded_flourless.csv"), index=False)
    print(f"Loaded {len(df)} recipes ({len(excluded)} flourless rows excluded).")

    # Standing data-quality report (unresolved-heads queue + basis shares).
    quality.write_reports(outdir)

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

    metrics = report(df, outdir)
    print(f"\nOutputs written under {outdir}/")
    return metrics