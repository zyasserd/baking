"""STAGE 2 — Analysis pipeline: the preprocessed dataset -> results.

The input is ``data/processed/recipes_simplex.csv`` (written by stage 1): one
row per recipe with structural part grams and 5-part simplex proportions
(summing to 1). The *features* are the ratios; the *labels* are the independent
Food.com tag classes (``tag_coarse``). The book ratios are used only as
reference archetypes, never as labels.

Analysis runs in Aitchison geometry (CLR/ILR — see ``src.analysis.coda``):
log-ratio PCA, robust outlier elimination, clustering vs the tag classes
(ARI + confusion), and the class distribution along PC1 (the "rich vs lean"
continuum). Validation diagnostics (labels vs titles, estimated mass vs
nutrition) are written alongside the results — see ``validate.write_reports``.
Every parameter lives in ``config`` (ANALYSIS section); the entry point takes
no tuning flags.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score

import config

from ..preprocess import parts
from . import cluster, coda, folds, pca, quality, robustness, validate
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
    # Recipes -> simplex proportions (already closed by stage 1) -> log ratios.
    P = df[parts.proportion_columns()].to_numpy(dtype=float)
    P = coda.multiplicative_replacement(coda.closure(P))
    clr = coda.clr(P)
    ilr = coda.ilr(P)
    comp = df.copy()

    # Pin PC1's sign to the sugar direction so it always reads rich > lean
    # (eigenvector signs from the eigendecomposition are arbitrary).
    orient = np.zeros(len(config.ANALYSIS_PARTS))
    orient[config.ANALYSIS_PARTS.index(config.PC1_ORIENT_PART)] = 1.0
    scores, eigvals, loadings, mean = pca.pca(clr, orient=orient)
    variance = pca.variance_table(eigvals)
    loadings_df = pca.loading_table(loadings, config.ANALYSIS_PARTS)
    variance.to_csv(os.path.join(outdir, "variance.csv"), index=False)
    loadings_df.to_csv(os.path.join(outdir, "loadings.csv"))

    interpretations = pca.interpret_components(loadings, config.ANALYSIS_PARTS)

    inliers = cluster.detect_outliers(ilr)
    validate.write_envelope_outliers(df, ilr, inliers, outdir)
    df = df[inliers].reset_index(drop=True)
    clr = clr[inliers]
    ilr = ilr[inliers]
    comp = comp[inliers].reset_index(drop=True)
    scores = scores[inliers]

    # Diagnostics: per class, the recipes farthest from the class centroid —
    # candidates for processing errors, written with inspection evidence.
    validate.write_extremes(df, ilr, outdir)

    arch_names, arch_clr = folds.archetype_clr()
    nearest, distance = folds.nearest_archetype(clr, arch_names, arch_clr)
    # df feeds the HTML hover (via the viz subset); comp is the CSV export.
    df["nearest_archetype"] = nearest
    df["aitchison_distance"] = distance
    comp["nearest_archetype"] = nearest
    comp["aitchison_distance"] = distance
    comp.to_csv(os.path.join(outdir, "compositions.csv"), index=False)

    pc1 = pd.DataFrame({"tag_coarse": df["tag_coarse"], "pc1": scores[:, 0]})
    pc1_summary = pc1.groupby("tag_coarse")["pc1"].agg(mean="mean", std="std", count="size")
    pc1_summary.to_csv(os.path.join(outdir, "class_pc1_summary.csv"))
    pc1_order = tuple(pc1_summary.sort_values("mean").index)

    n = len(df)
    if config.VIZ_SAMPLE_MAX > 0 and config.VIZ_SAMPLE_MAX < n:
        rng = np.random.default_rng(config.RANDOM_SEED)
        idx = np.sort(rng.choice(n, size=config.VIZ_SAMPLE_MAX, replace=False))
        viz_df = df.iloc[idx].reset_index(drop=True)
        viz_scores = scores[idx]
    else:
        viz_df = df
        viz_scores = scores

    arch_scores = pca.project(arch_clr, mean, loadings)

    tetra = folds.tetrahedron_matrix(viz_df)
    tetra_coords = folds.barycentric_3d(tetra)
    arch_tetra = folds.barycentric_3d(folds.tetrahedron_archetypes())

    viz_scores3 = viz_scores[:, : config.N_PCS_CLUSTER]

    metrics: dict = {"n": int(len(df)), "pc1_order": pc1_order, "ari": None, "silhouette": None}

    # Cluster in the top-3 log-ratio PCs (see config.N_PCS_CLUSTER); k is the
    # number of tag classes.
    n_clusters = int(df["tag_coarse"].nunique())
    clusters = cluster.run_clustering(viz_scores3, n_clusters)
    labels = {
        "tag_coarse": viz_df["tag_coarse"].to_numpy(),
        "tag_fine": viz_df["tag_fine"].to_numpy(),
    }
    cluster.write_outputs(outdir, viz_df, clusters, labels)

    table = cluster.confusion_table(viz_df["tag_coarse"].to_numpy(), clusters)
    table.to_csv(os.path.join(outdir, "tag_confusion.csv"))

    true = viz_df["tag_coarse"].to_numpy()
    metrics["ari"] = cluster.ari(true, clusters)
    metrics["silhouette"] = silhouette_score(
        viz_scores3, true, sample_size=min(len(viz_scores3), config.SILHOUETTE_SAMPLE_MAX)
    )
    metrics.update(robustness.write_reports(outdir, viz_scores3, true, clusters, clr))

    # One self-contained HTML page replaces every standalone figure.
    html_report.write_html(
        outdir, viz_df, viz_scores, arch_scores, arch_names, arch_tetra,
        tetra_coords, clusters, table, variance, interpretations, metrics,
    )
    return metrics


def report(df: pd.DataFrame, outdir: str) -> dict:
    print(f"\n===== structural simplex ({len(df)} recipes) =====")
    print("Class distribution:")
    for name, count in df["tag_coarse"].value_counts().items():
        print(f"  {name:<12} {count}")

    metrics = analyze(df, outdir)
    print("\nClass ordering along PC1 (rich vs lean):")
    for name in metrics["pc1_order"]:
        print(f"  {name}")
    print(f"\nARI vs tag_coarse: {metrics['ari']:.3f}")
    print(f"Silhouette (vs tag classes): {metrics['silhouette']:.3f}")
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

    # Diagnostics on the full dataset, before any filtering (see validate.py).
    validate.write_reports(df, outdir)

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