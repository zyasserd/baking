"""Outlier elimination and clustering in Aitchison (ILR) space.

The simplex is not Euclidean, so outliers are found and recipes are clustered
using the isometric log-ratio coordinates, where Euclidean distance equals the
Aitchison distance. Robust Mahalanobis distance flags parse-error outliers;
k-means (or Gaussian mixture) clusters the cleaned data. Parameters (contamination,
method, seed) live in the ANALYSIS section of ``config``.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.covariance import EllipticEnvelope
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture

import config


def detect_outliers(ilr: np.ndarray, contamination: float | None = None, seed: int | None = None) -> np.ndarray:
    """Boolean inlier mask from robust Mahalanobis distance in ILR space.

    ``EllipticEnvelope`` fits a robust (Minimum Covariance Determinant)
    Gaussian; points beyond the ``contamination`` tail are flagged as outliers.
    Defaults come from ``config``.
    """
    ilr = np.asarray(ilr, dtype=float)
    if len(ilr) < 10:
        return np.ones(len(ilr), dtype=bool)
    if contamination is None:
        contamination = config.OUTLIER_CONTAMINATION
    if seed is None:
        seed = config.RANDOM_SEED
    detector = EllipticEnvelope(contamination=contamination, random_state=seed)
    labels = detector.fit_predict(ilr)  # +1 inlier, -1 outlier
    return labels == 1


def run_clustering(
    X: np.ndarray,
    n_clusters: int,
    method: str | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Cluster log-ratio coordinates.

    ``method`` is ``"kmeans"`` (default from ``config``) or ``"gmm"``.
    """
    X = np.asarray(X, dtype=float)
    if method is None:
        method = config.CLUSTER_METHOD
    if seed is None:
        seed = config.CLUSTER_SEED
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


def confusion_table(true: np.ndarray, clusters: np.ndarray) -> pd.DataFrame:
    """Return a (true-class x cluster) count table."""
    table = pd.crosstab(pd.Series(true), pd.Series(clusters, name="cluster"))
    table.columns = [f"cluster {c}" for c in table.columns]
    table.index = [str(c) for c in table.index]
    return table