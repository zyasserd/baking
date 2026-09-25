"""Dimensionality checks via log-ratio principal component analysis.

PCA is run on the CLR coordinates (equivalent to PCA on ILR up to rotation:
identical eigenvalues). The simplex of D parts has rank D-1, so the analysis
reports how many of those dimensions carry real variance and interprets each
retained component as a balance of parts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def pca(
    clr: np.ndarray,
    orient: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Log-ratio PCA on CLR coordinates.

    Returns ``(scores, eigenvalues, loadings, mean)`` where:
    - ``scores`` is (n, D-1) (the last CLR singular component is dropped),
    - ``eigenvalues`` is (D-1,) in descending order,
    - ``loadings`` is (D, D-1): columns are component loadings on the D CLR axes
      (one axis per part), so each component reads as a part balance,
    - ``mean`` is the (D,) CLR center used for projection.

    ``orient`` (length D) is an optional reference direction used to pin each
    component's otherwise-arbitrary sign: a component is flipped so its loading
    has a positive dot product with ``orient`` (zero dot falls back to orienting
    the largest-magnitude loading positive). Passing ``+sugar`` keeps PC1
    reading "rich > lean" across runs.
    """
    clr = np.asarray(clr, dtype=float)
    mean = clr.mean(axis=0)
    X = clr - mean

    cov = X.T @ X / X.shape[0]
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    # CLR is over-parameterized: the last eigenvalue is (numerically) zero.
    eigvals = eigvals[:-1]
    eigvecs = eigvecs[:, :-1]

    # Deterministic sign convention: eigenvector signs from eigh are arbitrary
    # (they can flip between runs). Orient each component by ``orient`` when
    # given, else make its largest-magnitude loading positive. With
    # ``orient = +sugar`` PC1 always reads rich > lean.
    for j in range(eigvecs.shape[1]):
        col = eigvecs[:, j]
        if orient is not None:
            ref = float(orient @ col)
            if ref < 0 or (ref == 0 and col[np.argmax(np.abs(col))] < 0):
                eigvecs[:, j] = -col
        elif col[np.argmax(np.abs(col))] < 0:
            eigvecs[:, j] = -col

    scores = X @ eigvecs
    return scores, eigvals, eigvecs, mean


def project(clr: np.ndarray, mean: np.ndarray, loadings: np.ndarray) -> np.ndarray:
    """Project new CLR rows onto existing PCA loadings."""
    clr = np.asarray(clr, dtype=float)
    return (clr - mean) @ loadings


def variance_table(eigvals: np.ndarray) -> pd.DataFrame:
    """Per-component eigenvalue, fraction and cumulative fraction of variance."""
    eigvals = np.asarray(eigvals, dtype=float)
    total = eigvals.sum()
    if total <= 0:
        total = 1.0
    n = len(eigvals)
    frac = eigvals / total
    return pd.DataFrame(
        {
            "component": [f"PC{i + 1}" for i in range(n)],
            "eigenvalue": eigvals,
            "variance_fraction": frac,
            "cumulative_fraction": np.cumsum(frac),
        }
    )


def loading_table(loadings: np.ndarray, parts: list[str]) -> pd.DataFrame:
    """Loadings as a (parts x components) frame for human reading."""
    loadings = np.asarray(loadings, dtype=float)
    n = loadings.shape[1]
    return pd.DataFrame(
        loadings,
        index=parts,
        columns=[f"PC{i + 1}" for i in range(n)],
    )


def interpret_components(loadings: np.ndarray, parts: list[str]) -> list[str]:
    """A one-line human reading of each component as a part balance.

    Returns a list of strings like ``"PC1: +sugar +fat vs -flour -liquid"``.
    """
    loadings = np.asarray(loadings, dtype=float)
    lines = []
    for k in range(loadings.shape[1]):
        col = loadings[:, k]
        pos = [parts[i] for i in np.argsort(-col) if col[i] > 0]
        neg = [parts[i] for i in np.argsort(col) if col[i] < 0]
        pos_s = "+" + " +".join(pos) if pos else ""
        neg_s = "-" + " -".join(neg) if neg else ""
        lines.append(f"PC{k + 1}: {pos_s} {neg_s}".strip())
    return lines
