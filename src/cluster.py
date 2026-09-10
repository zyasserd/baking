"""HDBSCAN clustering on full CLR coordinates."""

from __future__ import annotations

import os

import hdbscan
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score


def run_clustering(
    Y: np.ndarray,
    df: pd.DataFrame,
    min_cluster_size: int = 5,
    min_samples: int | None = None,
) -> pd.Series:
    """Cluster CLR coordinates with HDBSCAN (Euclidean == Aitchison distance)."""
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(Y)
    return pd.Series(labels, index=df.index, name="cluster_id")


def write_outputs(outdir: str, df: pd.DataFrame, labels: pd.Series) -> None:
    """Write clusters.csv and cluster_report.txt."""
    os.makedirs(outdir, exist_ok=True)

    out = df[["recipe_id", "family"]].copy()
    out["cluster_id"] = labels.values
    out.to_csv(os.path.join(outdir, "clusters.csv"), index=False)

    ari = adjusted_rand_score(df["family"], labels.values)
    n_noise = int((labels == -1).sum())
    counts = labels.value_counts().sort_index()

    lines = [
        f"Adjusted Rand Index vs family: {ari:.3f}",
        f"Number of clusters: {int((labels >= 0).nunique())}",
        f"Noise points (cluster -1): {n_noise}",
        "",
        "Cluster sizes:",
    ]
    for cluster, size in counts.items():
        label = "noise" if cluster == -1 else str(cluster)
        lines.append(f"  cluster {label}: {size}")

    with open(os.path.join(outdir, "cluster_report.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
