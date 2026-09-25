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
from . import coda, cluster, folds, pca, validate, visualize


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
    visualize.scree(outdir, eigvals)

    interpretations = pca.interpret_components(loadings, config.ANALYSIS_PARTS)

    inliers = cluster.detect_outliers(ilr)
    df = df[inliers].reset_index(drop=True)
    clr = clr[inliers]
    ilr = ilr[inliers]
    comp = comp[inliers].reset_index(drop=True)
    scores = scores[inliers]

    arch_names, arch_clr = folds.archetype_clr()
    nearest, distance = folds.nearest_archetype(clr, arch_names, arch_clr)
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
        viz_ilr = ilr[idx]
    else:
        viz_df = df
        viz_scores = scores
        viz_ilr = ilr

    arch_scores = pca.project(arch_clr, mean, loadings)
    visualize.pca_biplot(outdir, viz_scores, loadings, viz_df, arch_scores, arch_names)
    visualize.ternary(outdir, viz_df)
    visualize.class_pc1_strip(outdir, viz_scores, viz_df)

    tetra = folds.tetrahedron_matrix(viz_df)
    tetra_coords = folds.barycentric_3d(tetra)
    arch_tetra = folds.barycentric_3d(folds.tetrahedron_archetypes())
    visualize.simplex_3d(outdir, tetra_coords, viz_df, arch_tetra, arch_names)

    viz_scores2 = viz_scores[:, :2]
    viz_scores3 = viz_scores[:, : config.N_PCS_CLUSTER]
    arch2 = arch_scores[:, :2]
    arch3 = arch_scores[:, : config.N_PCS_CLUSTER]
    visualize.pca_scatter_2d(
        outdir, viz_scores2, viz_df, arch2, arch_names,
        axis_labels=(interpretations[0], interpretations[1]),
    )
    visualize.pca_scatter_3d(outdir, viz_scores3, viz_df, arch3, arch_names)

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
    visualize.tag_confusion(outdir, table)
    visualize.cluster_scatter(outdir, viz_scores2, viz_df, clusters)

    true = viz_df["tag_coarse"].to_numpy()
    metrics["ari"] = cluster.ari(true, clusters)
    metrics["silhouette"] = silhouette_score(
        viz_scores3, true, sample_size=min(len(viz_scores3), config.SILHOUETTE_SAMPLE_MAX)
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