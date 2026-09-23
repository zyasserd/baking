"""Nonlinear dimensionality reduction for the simplex (UMAP / t-SNE).

PCA on the log-ratio coordinates is already the optimal *linear* embedding of
the 4-D simplex (it is, up to rotation, the metric MDS of the Aitchison
distance). UMAP and t-SNE are nonlinear alternatives that tighten local
clusters at the cost of global distance fidelity — useful when the recipes form
a gradient and PCA spreads them into one cloud.

The book archetypes are embedded alongside the recipes so they land in the same
map; the two parts are split back out on return.
"""

from __future__ import annotations

import numpy as np


def embed(
    ilr: np.ndarray,
    archetype_ilr: np.ndarray | None,
    method: str,
    n_components: int = 2,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Embed ILR coordinates with ``method`` (``"umap"`` or ``"tsne"``).

    Returns ``(recipe_embedding, archetype_embedding)``; the archetype part is
    an empty array if no archetypes were supplied.
    """
    ilr = np.asarray(ilr, dtype=float)
    n_rec = len(ilr)
    if archetype_ilr is None:
        combined = ilr
    else:
        combined = np.vstack([ilr, archetype_ilr])

    if method == "umap":
        import umap

        E = umap.UMAP(
            n_components=n_components,
            n_neighbors=min(30, len(combined) - 1),
            min_dist=0.1,
            random_state=seed,
        ).fit_transform(combined)
    elif method == "tsne":
        from sklearn.manifold import TSNE

        E = TSNE(
            n_components=n_components,
            init="pca",
            learning_rate="auto",
            perplexity=min(30.0, max(5.0, (len(combined) - 1) / 3.0)),
            random_state=seed,
        ).fit_transform(combined)
    else:
        raise ValueError(f"unknown embedding method: {method}")

    E = np.asarray(E, dtype=float)
    return E[:n_rec], E[n_rec:]