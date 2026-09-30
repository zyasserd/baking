"""Robustness baselines: is the reported result a fluke of one clustering?

Everything here resamples or permutes the SAME fitted analysis:
- ``permutation_null`` — ARI of the fixed clusters against shuffled labels
  (the "chance" level; the reported ARI should sit far above it);
- ``bootstrap_ari`` — resample recipes with replacement, re-cluster, score
  against the resampled labels (stability of the clustering itself);
- ``k_sweep`` — silhouette + ARI for k = 2..K (k = number of tag classes is
  currently an assumption, not a finding);
- ``pc_stability`` — bootstrap the recipes, re-run the log-ratio PCA, and
  check how stable PC1's variance share and loading direction are.

All loops are seeded from ``config.RANDOM_SEED``; B = 0 disables everything.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score

import config

from . import cluster, pca


def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(config.RANDOM_SEED if seed is None else seed)


def _b(b: int | None) -> int:
    return config.ROBUSTNESS_B if b is None else b


def permutation_null(labels: np.ndarray, clusters: np.ndarray, b: int | None = None,
                     seed: int | None = None) -> np.ndarray:
    """ARI of the fixed clusters against B random shufflings of the labels."""
    labels = np.asarray(labels)
    rng = _rng(seed)
    return np.array([
        cluster.ari(rng.permutation(labels), clusters) for _ in range(_b(b))
    ])


def bootstrap_ari(scores: np.ndarray, labels: np.ndarray, b: int | None = None,
                  seed: int | None = None) -> np.ndarray:
    """Resample recipes with replacement, re-cluster, score vs resampled labels."""
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels)
    n_clusters = int(np.unique(labels).size)
    n = len(scores)
    rng = _rng(seed)
    out = []
    for _ in range(_b(b)):
        idx = rng.integers(0, n, size=n)
        cl = cluster.run_clustering(scores[idx], n_clusters)
        out.append(cluster.ari(labels[idx], cl))
    return np.array(out)


def k_sweep(scores: np.ndarray, labels: np.ndarray, k_max: int | None = None,
            seed: int | None = None) -> pd.DataFrame:
    """Silhouette (of the clusters) and ARI (vs tag labels) for each k."""
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels)
    rows = []
    for k in range(2, (config.K_SWEEP_MAX if k_max is None else k_max) + 1):
        cl = cluster.run_clustering(scores, k, seed=seed)
        rows.append({
            "k": k,
            "ari_vs_tags": round(cluster.ari(labels, cl), 4),
            "silhouette": round(float(silhouette_score(
                scores, cl, sample_size=min(len(scores), config.SILHOUETTE_SAMPLE_MAX)
            )), 4),
        })
    return pd.DataFrame(rows)


def pc_stability(clr: np.ndarray, b: int | None = None,
                 seed: int | None = None) -> pd.DataFrame:
    """Bootstrap PC1 variance share and loading-direction stability.

    Returns per-bootstrap rows: the PC1 variance share and the absolute cosine
    between the bootstrap PC1 loadings and the full-data PC1 loadings.
    """
    clr = np.asarray(clr, dtype=float)
    orient = np.zeros(len(config.ANALYSIS_PARTS))
    orient[config.ANALYSIS_PARTS.index(config.PC1_ORIENT_PART)] = 1.0

    _, eigvals, loadings, _ = pca.pca(clr, orient=orient)
    ref_dir = loadings[:, 0]

    rng = _rng(seed)
    n = len(clr)
    rows = []
    for _ in range(_b(b)):
        idx = rng.integers(0, n, size=n)
        _, ev, ld, _ = pca.pca(clr[idx], orient=orient)
        rows.append({
            "pc1_var_share": float(ev[0] / ev.sum()),
            "pc1_cos_to_full": float(abs(np.dot(ld[:, 0], ref_dir))
                                     / (np.linalg.norm(ld[:, 0]) * np.linalg.norm(ref_dir))),
        })
    return pd.DataFrame(rows)


def write_reports(outdir: str, scores: np.ndarray, labels: np.ndarray,
                  clusters: np.ndarray, clr: np.ndarray) -> dict:
    """Run every baseline, write its CSV, print the headline numbers."""
    if config.ROBUSTNESS_B <= 0:
        return {}

    null = permutation_null(labels, clusters)
    pd.DataFrame({"ari_null": null}).to_csv(os.path.join(outdir, "ari_null.csv"), index=False)

    boot = bootstrap_ari(scores, labels)
    pd.DataFrame({"ari_bootstrap": boot}).to_csv(
        os.path.join(outdir, "ari_bootstrap.csv"), index=False)

    sweep = k_sweep(scores, labels)
    sweep.to_csv(os.path.join(outdir, "k_sweep.csv"), index=False)

    stability = pc_stability(clr)
    stability.to_csv(os.path.join(outdir, "pc_stability.csv"), index=False)

    p_value = float((null >= cluster.ari(labels, clusters)).mean())
    lo, hi = np.percentile(boot, [2.5, 97.5])
    best_k = int(sweep.loc[sweep["silhouette"].idxmax(), "k"])
    print("\nRobustness:")
    print(f"  ARI permutation p-value: {p_value:.3f} "
          f"(null mean {null.mean():.3f} +- {null.std():.3f})")
    print(f"  ARI bootstrap 95% CI: [{lo:.3f}, {hi:.3f}]")
    print(f"  k sweep: best silhouette at k={best_k}; "
          f"ARI at k=7: {sweep.loc[sweep['k'] == 7, 'ari_vs_tags'].iloc[0]:.3f}")
    print(f"  PC1 share {stability['pc1_var_share'].mean():.3f} "
          f"+- {stability['pc1_var_share'].std():.3f}; "
          f"loading direction cos {stability['pc1_cos_to_full'].mean():.3f}")
    return {"ari_p_value": p_value, "ari_ci": (float(lo), float(hi)),
            "best_k": best_k}
