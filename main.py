"""End-to-end baking-ratio dimensionality-reduction pipeline."""

from __future__ import annotations

import argparse
import os

from src import cluster, preprocess, reduce, visualize


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dimensionality reduction on the baking-ingredient simplex."
    )
    parser.add_argument("--input", required=True, help="Path to data/recipes.csv")
    parser.add_argument("--outdir", default="output", help="Directory for output files")
    parser.add_argument(
        "--cluster",
        action="store_true",
        help="Run optional HDBSCAN clustering on the full CLR coordinates",
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    df, excluded = preprocess.load_recipes(args.input)
    excluded.to_csv(os.path.join(args.outdir, "excluded_flourless.csv"), index=False)
    print(f"Loaded {len(df)} recipes ({len(excluded)} flourless rows excluded).")

    Y = preprocess.build_clr_matrix(df)

    pca, Z, W = reduce.fit_pca(Y, n_components=3)
    axis_names = reduce.name_axes(W)
    reduce.write_outputs(
        args.outdir, df, Z, W, pca.explained_variance_ratio_, axis_names
    )

    visualize.biplot(args.outdir, df, Z, W)
    visualize.scatter_3d(args.outdir, df, Z)
    visualize.umap_2d(args.outdir, Y, df)

    if args.cluster:
        labels = cluster.run_clustering(Y, df)
        cluster.write_outputs(args.outdir, df, labels)

    total_var = float(pca.explained_variance_ratio_.sum())
    print(f"Explained variance ratio (total): {total_var:.4f}")
    for name, ratio in zip(axis_names, pca.explained_variance_ratio_):
        print(f"  [{ratio:.4f}] {name}")
    print(f"Outputs written to {args.outdir}/")


if __name__ == "__main__":
    main()
