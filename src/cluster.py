"""Outlier elimination and clustering in Aitchison (ILR) space.

The simplex is not Euclidean, so outliers are found and recipes are clustered
using the isometric log-ratio coordinates, where Euclidean distance equals the
Aitchison distance. Robust Mahalanobis distance flags parse-error outliers;
k-means (or Gaussian mixture) clusters the cleaned data.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.covariance import EllipticEnvelope
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture


def detect_outliers(ilr: np.ndarray, contamination: float = 0.01, seed: int = 0) -> np.ndarray:
    """Boolean inlier mask from robust Mahalanobis distance in ILR space.

    ``EllipticEnvelope`` fits a robust (Minimum Covariance Determinant)
    Gaussian; points beyond the ``contamination`` tail are flagged as outliers.
    """
    ilr = np.asarray(ilr, dtype=float)
    if len(ilr) < 10:
        return np.ones(len(ilr), dtype=bool)
    detector = EllipticEnvelope(contamination=contamination, random_state=seed)
    labels = detector.fit_predict(ilr)  # +1 inlier, -1 outlier
    return labels == 1


def run_clustering(
    X: np.ndarray,
    n_clusters: int,
    method: str = "kmeans",
    seed: int = 0,
) -> np.ndarray:
    """Cluster ILR coordinates.

    ``method`` is ``"kmeans"`` (default) or ``"gmm"``.
    """
    X = np.asarray(X, dtype=float)
    if method == "gmm":
        model = GaussianMixture(
            n_components=n_clusters,
            covariance_type="full",
            random_state=seed,
            n_init=3,
        )
        return model.fit_predict(X)
    model = KMeans(n_clusters=n_clusters, n_init=10, random_state=seed)
    return model.fit_predict(X)


def ari(labels: pd.Series | np.ndarray, clusters: np.ndarray) -> float:
    """Adjusted Rand Index between true labels and cluster assignment."""
    a = np.asarray(labels)
    return adjusted_rand_score(a, np.asarray(clusters))


def write_outputs(
    outdir: str,
    df: pd.DataFrame,
    clusters: np.ndarray,
    labels: dict[str, np.ndarray],
) -> None:
    """Write ``clusters.csv`` and ``cluster_report.txt``.

    ``labels`` maps a label name (e.g. "tag_coarse", "tag_fine") to the
    per-recipe true values; the report gives an ARI for each.
    """
    os.makedirs(outdir, exist_ok=True)

    out = df[["recipe_id", "tag_coarse", "tag_fine"]].copy()
    out["cluster_id"] = clusters
    out.to_csv(os.path.join(outdir, "clusters.csv"), index=False)

    n_clusters = int(np.unique(clusters).size)
    lines = [f"Number of clusters: {n_clusters}", ""]
    for name, true in labels.items():
        lines.append(f"Adjusted Rand Index vs {name}: {ari(true, clusters):.3f}")
    lines.append("")
    lines.append("Cluster composition (top classes per cluster):")
    for c in sorted(np.unique(clusters)):
        fam = df["tag_coarse"].to_numpy()[clusters == c]
        top = pd.Series(fam).value_counts().head(3)
        parts = [f"{name} ({count})" for name, count in top.items()]
        lines.append(f"  cluster {c}: {', '.join(parts)}")

    with open(os.path.join(outdir, "cluster_report.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


def confusion_table(
    true: np.ndarray, clusters: np.ndarray
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Return a (true-class x cluster) count table with the two label vocabularies."""
    table = pd.crosstab(pd.Series(true), pd.Series(clusters, name="cluster"))
    cols = [f"cluster {c}" for c in table.columns]
    table.columns = cols
    classes = [str(c) for c in table.index]
    table.index = classes
    return table, classes, cols
