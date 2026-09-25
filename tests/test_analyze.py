"""Tests for the log-ratio PCA dimensionality check."""

import numpy as np
import pytest

import config
from src.analysis import folds, pca
from src.analysis.coda import closure, clr, ilr, multiplicative_replacement


def _clr(n=300):
    rng = np.random.default_rng(0)
    X = rng.uniform(1, 500, size=(n, 5))
    P = closure(X)
    P = multiplicative_replacement(P)
    return clr(P)


def test_pca_shapes_and_variance_sum():
    clr = _clr()
    scores, eigvals, loadings, mean = pca.pca(clr)
    assert scores.shape == (300, 4)
    assert eigvals.shape == (4,)
    assert loadings.shape == (5, 4)
    assert mean.shape == (5,)
    # Eigenvalues are non-negative and descending.
    assert np.all(eigvals >= 0)
    assert np.all(np.diff(eigvals) <= 1e-9)


def test_variance_table_cumulative_ends_at_one():
    _, eigvals, _, _ = pca.pca(_clr())
    table = pca.variance_table(eigvals)
    np.testing.assert_allclose(table["variance_fraction"].sum(), 1.0, atol=1e-9)
    assert table["cumulative_fraction"].iloc[-1] == pytest.approx(1.0, abs=1e-9)


def test_loading_table_index_is_parts():
    clr = _clr(10)
    _, _, loadings, _ = pca.pca(clr)
    table = pca.loading_table(loadings, config.ANALYSIS_PARTS)
    assert list(table.index) == config.ANALYSIS_PARTS
    assert list(table.columns) == ["PC1", "PC2", "PC3", "PC4"]


def test_interpret_components_length():
    _, _, loadings, _ = pca.pca(_clr(10))
    lines = pca.interpret_components(loadings, config.ANALYSIS_PARTS)
    assert len(lines) == 4
    assert all(line.startswith(f"PC{i + 1}:") for i, line in enumerate(lines))


def test_pca_sign_convention():
    # Component signs are arbitrary in eigh; the convention pins the largest
    # loading positive so PC1 always reads the same direction across runs.
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 4))
    scores, _, loadings, _ = pca.pca(X)
    for j in range(loadings.shape[1]):
        assert loadings[np.argmax(np.abs(loadings[:, j])), j] > 0


def test_pca_orient_pins_sugar_positive():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 5))
    orient = np.zeros(5)
    orient[4] = 1.0  # "sugar" direction
    _, _, loadings, _ = pca.pca(X, orient=orient)
    assert loadings[4, 0] > 0
