"""Tests for the ILR coordinate system the analysis runs in.

There is no PCA anywhere: recipes are clustered as ILR balances of the
simplex. These tests pin the properties that make that sound — the ILR is an
isometry of the Aitchison geometry, so Euclidean distances in ILR equal the
Aitchison distances of the compositions.
"""

import numpy as np

from src.analysis.coda import closure, clr, ilr, ilr_inverse, multiplicative_replacement


def _P(n: int = 300) -> np.ndarray:
    rng = np.random.default_rng(0)
    P = closure(rng.uniform(1, 500, size=(n, 5)))
    return multiplicative_replacement(P)


def test_ilr_shape():
    Z = ilr(_P(50))
    assert Z.shape == (50, 4)


def test_ilr_preserves_aitchison_distance():
    P = _P(40)
    Z = ilr(P)
    C = clr(P)
    pair = (3, 17)
    d_ilr = np.linalg.norm(Z[pair[0]] - Z[pair[1]])
    d_clr = np.linalg.norm(C[pair[0]] - C[pair[1]])
    np.testing.assert_allclose(d_ilr, d_clr, atol=1e-10)


def test_ilr_matches_hand_computed_balance():
    # The first pivot balance: sqrt(4/5) * log(x_flour / g(rest)).
    P = _P(1)
    expected = np.sqrt(4 / 5) * (
        np.log(P[0, 0]) - np.log(P[0, 1:]).mean()
    )
    np.testing.assert_allclose(ilr(P)[0, 0], expected, atol=1e-12)


def test_ilr_inverse_roundtrips():
    P = _P(30)
    np.testing.assert_allclose(ilr_inverse(ilr(P)), P, atol=1e-10)


def test_ilr_mean_maps_to_closed_shares():
    # The class-centroid path: mean of balances must land back on the simplex.
    P = _P(25)
    Z = ilr(P)
    centroid = ilr_inverse(Z.mean(axis=0)[None, :])[0]
    np.testing.assert_allclose(centroid.sum(), 1.0, atol=1e-12)
    assert np.all(centroid > 0)