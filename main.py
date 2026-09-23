"""End-to-end baking analysis: do the ratios predict the Food.com tags?

Each recipe is a point on the 5-part simplex (flour, liquid, egg, fat, sugar;
parts sum to 1). The *features* are the ratios; the *labels* are the independent
Food.com tag classes (``tag_coarse``), joined from a separate corpus. The book
ratios (Ruhlman's *Ratio*) are used only as reference archetypes, never as labels.

Two decompositions are available (built by ``scripts/build_dataset.py``):

- ``full`` (the ``*_g`` columns) — every significant ingredient contributes its
  USDA-derived component mass, including add-ins (chocolate, nuts, fruit, …);
- ``structural`` (the ``*_s_g`` columns) — add-ins are zeroed, reproducing
  Ruhlman's clean flour:liquid:egg:fat:sugar ratio.

``--simplex full|structural|both`` selects which to analyze.

Analysis runs in Aitchison geometry (CLR/ILR): log-ratio PCA, robust outlier
elimination, clustering vs the tag classes (ARI + confusion), and the class
distribution along PC1 (the "rich vs lean" continuum).
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from src import analyze, cluster, composition, manifold, preprocess, visualize

_GRAM_PARTS = ["flour", "sugar", "fat", "egg", "milk", "water"]


def _mode_frame(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == "full":
        return df
    d = df.copy()
    for part in _GRAM_PARTS:
        d[f"{part}_g"] = d[f"{part}_s_g"]
    return d


def _analyze(df: pd.DataFrame, args: argparse.Namespace, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)

    # Drop recipes whose structural mass is zero (no base ingredients survive
    # the mode — e.g. "flourless" cookies made only of add-ins like oats).
    mass = df[["flour_g", "water_g", "milk_g", "egg_g", "fat_g", "sugar_g"]].sum(axis=1)
    if (mass <= 0).any():
        df = df[mass > 0].reset_index(drop=True)

    comp = composition.compositions(df)
    clr, ilr = composition.coordinates(df)

    scores, eigvals, loadings, mean = analyze.pca(clr)
    variance = analyze.variance_table(eigvals)
    loadings_df = analyze.loading_table(loadings, composition.PARTS)
    variance.to_csv(os.path.join(outdir, "variance.csv"), index=False)
    loadings_df.to_csv(os.path.join(outdir, "loadings.csv"))
    visualize.scree(outdir, eigvals)

    interpretations = analyze.interpret_components(loadings, composition.PARTS)

    inliers = cluster.detect_outliers(ilr, contamination=args.contamination)
    n_out = int((~inliers).sum())
    df = df[inliers].reset_index(drop=True)
    clr = clr[inliers]
    ilr = ilr[inliers]
    comp = comp[inliers].reset_index(drop=True)
    scores = scores[inliers]

    arch_names, arch_clr = composition.archetype_clr()
    _, arch_ilr = composition.archetype_ilr()
    nearest, distance = composition.nearest_archetype(clr, arch_names, arch_clr)
    comp["nearest_archetype"] = nearest
    comp["aitchison_distance"] = distance
    comp.to_csv(os.path.join(outdir, "compositions.csv"), index=False)

    pc1 = pd.DataFrame({"tag_coarse": df["tag_coarse"], "pc1": scores[:, 0]})
    pc1_summary = pc1.groupby("tag_coarse")["pc1"].agg(mean="mean", std="std", count="size")
    pc1_summary.to_csv(os.path.join(outdir, "class_pc1_summary.csv"))
    pc1_order = tuple(pc1_summary.sort_values("mean").index)

    n = len(df)
    sample_n = n if args.sample is None or args.sample <= 0 or args.sample >= n else args.sample
    if sample_n < n:
        rng = np.random.default_rng(0)
        idx = np.sort(rng.choice(n, size=sample_n, replace=False))
        viz_df = df.iloc[idx].reset_index(drop=True)
        viz_comp = comp.iloc[idx].reset_index(drop=True)
        viz_scores = scores[idx]
        viz_ilr = ilr[idx]
    else:
        viz_df = df
        viz_comp = comp
        viz_scores = scores
        viz_ilr = ilr

    arch_scores = analyze.project(arch_clr, mean, loadings)
    visualize.pca_biplot(outdir, viz_scores, loadings, viz_df, arch_scores, arch_names)
    visualize.ternary(outdir, viz_comp)
    visualize.class_pc1_strip(outdir, viz_scores, viz_df)

    tetra = composition.tetrahedron_matrix(viz_df)
    tetra_coords = composition.barycentric_3d(tetra)
    arch_tetra = composition.barycentric_3d(composition.tetrahedron_archetypes())
    visualize.simplex_3d(outdir, tetra_coords, viz_df, arch_tetra, arch_names)

    if args.embed == "pca":
        emb2 = viz_scores[:, :2]
        emb3 = viz_scores[:, :3]
        arch2 = arch_scores[:, :2]
        arch3 = arch_scores[:, :3]
        axis_labels = (interpretations[0], interpretations[1]) if len(interpretations) >= 2 else None
    elif args.embed == "umap":
        emb2, arch2 = manifold.embed(viz_ilr, arch_ilr, "umap", 2)
        emb3, arch3 = manifold.embed(viz_ilr, arch_ilr, "umap", 3)
        axis_labels = None
    else:  # tsne
        emb2, arch2 = manifold.embed(viz_ilr, arch_ilr, "tsne", 2)
        emb3 = np.zeros((0, 3))
        arch3 = np.zeros((0, 3))
        axis_labels = None

    visualize.embedding_2d(outdir, args.embed, emb2, viz_df, arch2, arch_names, axis_labels)
    if args.embed != "tsne":
        visualize.embedding_3d(outdir, args.embed, emb3, viz_df, arch3, arch_names)

    metrics: dict = {"n": int(len(df)), "pc1_order": pc1_order, "ari": None, "silhouette": None}

    if args.cluster:
        n_clusters = int(df["tag_coarse"].nunique())
        clusters = cluster.run_clustering(emb2, n_clusters, method=args.cluster_method)
        labels = {
            "tag_coarse": viz_df["tag_coarse"].to_numpy(),
            "tag_fine": viz_df["tag_fine"].to_numpy(),
        }
        cluster.write_outputs(outdir, viz_df, clusters, labels)

        table, _, _ = cluster.confusion_table(viz_df["tag_coarse"].to_numpy(), clusters)
        table.to_csv(os.path.join(outdir, "tag_confusion.csv"))
        visualize.tag_confusion(outdir, table)
        visualize.cluster_scatter(outdir, emb2, viz_df, clusters)

        from sklearn.metrics import silhouette_score

        true = viz_df["tag_coarse"].to_numpy()
        metrics["ari"] = cluster.ari(true, clusters)
        metrics["silhouette"] = silhouette_score(
            emb2, true, sample_size=min(len(emb2), 20000)
        )

    return metrics


def _report(df: pd.DataFrame, args: argparse.Namespace, outdir: str, mode: str) -> dict:
    print(f"\n===== simplex = {mode} ({len(df)} recipes) =====")
    print("Class distribution:")
    for name, count in df["tag_coarse"].value_counts().items():
        print(f"  {name:<12} {count}")

    metrics = _analyze(df, args, outdir)
    print("\nClass ordering along PC1 (rich vs lean):")
    for name in metrics["pc1_order"]:
        print(f"  {name}")
    if args.cluster:
        print(f"\nARI vs tag_coarse: {metrics['ari']:.3f}")
        print(f"Silhouette (vs tag classes): {metrics['silhouette']:.3f}")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baking simplex analysis: test ratio clusters against Food.com tags."
    )
    parser.add_argument("--input", required=True, help="Path to the tagged recipe CSV")
    parser.add_argument("--outdir", default="output", help="Directory for output files")
    parser.add_argument("--cluster", action="store_true", help="Run clustering and report ARI")
    parser.add_argument(
        "--cluster-method",
        choices=["kmeans", "gmm"],
        default="kmeans",
        help="Clustering algorithm (default kmeans)",
    )
    parser.add_argument(
        "--embed",
        choices=["pca", "umap", "tsne"],
        default="pca",
        help="Embedding for visualization/clustering (default pca)",
    )
    parser.add_argument("--sample", type=int, default=20000, help="Max recipes for plots/clustering")
    parser.add_argument("--min-flour", type=float, default=0.0, help="Drop recipes below this many g flour")
    parser.add_argument("--contamination", type=float, default=0.01, help="Outlier fraction (robust Mahalanobis)")
    parser.add_argument(
        "--keep-weak-tier",
        action="store_true",
        help="Keep the dessert_other weak tier in the primary analysis (default: drop)",
    )
    parser.add_argument(
        "--min-confidence",
        choices=["strong", "medium", "weak"],
        default=None,
        help="Only keep recipes with at least this tag confidence",
    )
    parser.add_argument(
        "--simplex",
        choices=["full", "structural", "both"],
        default="full",
        help="Which decomposition to analyze (default full)",
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    df, excluded = preprocess.load_recipes(args.input)
    excluded.to_csv(os.path.join(args.outdir, "excluded_flourless.csv"), index=False)
    print(f"Loaded {len(df)} recipes ({len(excluded)} flourless rows excluded).")

    if not args.keep_weak_tier:
        dropped = (df["tag_coarse"] == "dessert_other").sum()
        df = df[df["tag_coarse"] != "dessert_other"].reset_index(drop=True)
        print(f"Dropped {int(dropped)} dessert_other (weak-tier) recipes.")

    if args.min_confidence:
        order = {"strong": 0, "medium": 1, "weak": 2}
        keep = df["tag_confidence"].map(lambda c: order.get(c, 2) <= order[args.min_confidence])
        print(f"Dropped {int((~keep).sum())} recipes below confidence {args.min_confidence}.")
        df = df[keep].reset_index(drop=True)

    if args.min_flour > 0:
        keep = df["flour_g"] >= args.min_flour
        print(f"Dropped {int((~keep).sum())} recipes below {args.min_flour} g flour.")
        df = df[keep].reset_index(drop=True)

    if args.simplex == "full":
        _report(df, args, args.outdir, "full")
    elif args.simplex == "structural":
        _report(_mode_frame(df, "structural"), args, os.path.join(args.outdir, "structural"), "structural")
    else:  # both
        m_full = _report(df, args, os.path.join(args.outdir, "full"), "full")
        m_struct = _report(
            _mode_frame(df, "structural"),
            args,
            os.path.join(args.outdir, "structural"),
            "structural",
        )

        rows = []
        for label, m in [("full", m_full), ("structural", m_struct)]:
            rows.append(
                {
                    "simplex": label,
                    "recipes": m["n"],
                    "ari_vs_tag_coarse": (round(m["ari"], 4) if m["ari"] is not None else None),
                    "silhouette": (round(m["silhouette"], 4) if m["silhouette"] is not None else None),
                    "pc1_lean_to_rich": " < ".join(m["pc1_order"]),
                }
            )
        comp_df = pd.DataFrame(rows)
        comp_df.to_csv(os.path.join(args.outdir, "simplex_comparison.csv"), index=False)
        print("\n===== full vs structural =====")
        print(comp_df.to_string(index=False))

    print(f"\nOutputs written under {args.outdir}/")


if __name__ == "__main__":
    main()