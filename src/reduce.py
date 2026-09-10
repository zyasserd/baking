"""PCA on CLR coordinates and automatic ratio-based axis naming."""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from .preprocess import CORE_COLUMNS


def fit_pca(Y: np.ndarray, n_components: int = 3) -> tuple[PCA, np.ndarray, np.ndarray]:
    """Fit PCA on CLR coordinates.

    Returns (pca, Z, W) where Z is the n x n_components projection and W is the
    n_components x D loading matrix (W = pca.components_).
    """
    pca = PCA(n_components=n_components)
    Z = pca.fit_transform(Y)
    return pca, Z, pca.components_


def ingredient_label(column: str) -> str:
    """'flour_g' -> 'flour' for readable axis names."""
    return column[:-2] if column.endswith("_g") else column


def _top_positive_and_negative(w: np.ndarray, labels: list[str]) -> tuple[list[str], list[str]]:
    order = np.argsort(w)  # ascending
    positive = [labels[i] for i in order[::-1] if w[i] > 0][:2]
    negative = [labels[i] for i in order if w[i] < 0][:2]
    return positive, negative


def name_axes(W: np.ndarray, labels: list[str] | None = None) -> list[str]:
    """Auto-generate ratio interpretations for each PC.

    For each component k, take the top 2 positive and top 2 negative loadings
    and emit ``PC{k} ~ log[(pos1 * pos2) / (neg1 * neg2)]``.
    """
    if labels is None:
        labels = [ingredient_label(c) for c in CORE_COLUMNS]
    if len(labels) != W.shape[1]:
        raise ValueError("number of labels must match the loading matrix width")

    names = []
    for k in range(W.shape[0]):
        positive, negative = _top_positive_and_negative(W[k], labels)
        if len(positive) < 2 or len(negative) < 2:
            # Degenerate component: fall back to the extreme ingredients.
            order = np.argsort(W[k])
            pos = [labels[i] for i in order[::-1][:2]]
            neg = [labels[i] for i in order[:2]]
            names.append(f"PC{k + 1} ≈ log[ ({pos[0]} · {pos[1]}) / ({neg[0]} · {neg[1]}) ]")
            continue
        names.append(
            f"PC{k + 1} ≈ log[ ({positive[0]} · {positive[1]}) / ({negative[0]} · {negative[1]}) ]"
        )
    return names


def write_outputs(
    outdir: str,
    df: pd.DataFrame,
    Z: np.ndarray,
    W: np.ndarray,
    explained_variance_ratio: np.ndarray,
    axis_names: list[str],
) -> None:
    """Write coordinates.csv, loadings.csv, variance.json, axis_names.txt."""
    os.makedirs(outdir, exist_ok=True)

    coords = df[["recipe_id", "name", "family"]].copy()
    for k in range(Z.shape[1]):
        coords[f"PC{k + 1}"] = Z[:, k]
    coords.to_csv(os.path.join(outdir, "coordinates.csv"), index=False)

    loadings = pd.DataFrame(W, columns=[ingredient_label(c) for c in CORE_COLUMNS])
    loadings.index.name = "PC"
    loadings.index = [f"PC{i + 1}" for i in range(W.shape[0])]
    loadings.to_csv(os.path.join(outdir, "loadings.csv"))

    variance = {f"pc{i + 1}": float(v) for i, v in enumerate(explained_variance_ratio)}
    with open(os.path.join(outdir, "variance.json"), "w") as fh:
        json.dump(variance, fh, indent=2)

    with open(os.path.join(outdir, "axis_names.txt"), "w") as fh:
        fh.write("\n".join(axis_names) + "\n")
