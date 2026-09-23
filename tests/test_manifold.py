"""Tests for nonlinear manifold embeddings (UMAP / t-SNE)."""

import numpy as np
import pytest

from src import manifold


def _ilr(n, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.uniform(1, 500, size=(n, 5))
    from src import preprocess

    P = preprocess.closure(X)
    P = preprocess.multiplicative_replacement(P)
    return preprocess.ilr(P)


@pytest.mark.parametrize("method", ["umap", "tsne"])
def test_embed_shapes(method):
    ilr = _ilr(40)
    arch = _ilr(10, seed=1)
    rec, a = manifold.embed(ilr, arch, method, n_components=2, seed=0)
    assert rec.shape == (40, 2)
    assert a.shape == (10, 2)


def test_embed_no_archetypes():
    ilr = _ilr(40)
    rec, a = manifold.embed(ilr, None, "umap", n_components=2)
    assert rec.shape == (40, 2)
    assert a.shape == (0, 2)


def test_embed_unknown_method_raises():
    with pytest.raises(ValueError):
        manifold.embed(_ilr(10), None, "pca", n_components=2)