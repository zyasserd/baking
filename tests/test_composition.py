"""Tests for the 5-part simplex, log-ratio transforms, and archetype scoring."""

import numpy as np
import pandas as pd
import pytest

from src import composition, preprocess


def _df() -> pd.DataFrame:
    # Three archetype-exact recipes: bread (5:3), drop cookie (3:1:2:3),
    # pound cake (1:1:1:1).
    return pd.DataFrame(
        {
            "recipe_id": ["R1", "R2", "R3"],
            "name": ["bread", "cookie", "cake"],
            "tag_coarse": ["bread", "cookie", "cake"],
            "tag_fine": ["sourdough", "drop-cookies", "cakes"],
            "flour_g": [500.0, 300.0, 250.0],
            "sugar_g": [0.0, 300.0, 250.0],
            "fat_g": [0.0, 200.0, 250.0],
            "egg_g": [0.0, 100.0, 250.0],
            "milk_g": [0.0, 0.0, 0.0],
            "water_g": [300.0, 0.0, 0.0],
            "salt_g": [10.0, 5.0, 5.0],
            "leavener_g": [0.0, 8.0, 0.0],
            "yeast_g": [7.0, 0.0, 0.0],
        }
    )


def _pivot_contrast(D: int) -> np.ndarray:
    """The D-1 x D contrast matrix implied by the pivot ILR coordinates."""
    rows = []
    for k in range(D - 1):
        s = D - 1 - k
        coef = np.sqrt(s / (s + 1))
        row = np.zeros(D)
        row[k] = coef
        row[k + 1 :] = -coef / s
        rows.append(row)
    return np.array(rows)


def test_parts_matrix_folds_liquid():
    X = composition.parts_matrix(_df())
    # R1: flour=500, liquid=300, egg=0, fat=0, sugar=0
    np.testing.assert_allclose(X[0], [500.0, 300.0, 0.0, 0.0, 0.0])


def test_compositions_sum_to_one():
    comp = composition.compositions(_df())
    part_cols = [f"{p}_p" for p in composition.PARTS]
    np.testing.assert_allclose(comp[part_cols].to_numpy().sum(axis=1), 1.0, atol=1e-9)


def test_ilr_contrast_is_orthonormal():
    psi = _pivot_contrast(5)
    # Rows are contrasts (sum to zero) and orthonormal.
    np.testing.assert_allclose(psi.sum(axis=1), 0.0, atol=1e-12)
    np.testing.assert_allclose(psi @ psi.T, np.eye(4), atol=1e-12)


def test_ilr_default_matches_pivot_contrast():
    rng = np.random.default_rng(0)
    X = rng.uniform(1, 500, size=(30, 5))
    P = preprocess.closure(X)
    P = preprocess.multiplicative_replacement(P)
    psi = _pivot_contrast(5)
    np.testing.assert_allclose(
        preprocess.ilr(P), preprocess.ilr(P, psi=psi), atol=1e-12
    )


def test_ilr_euclidean_equals_aitchison():
    # Distance in ILR space must match distance in CLR space (Aitchison).
    rng = np.random.default_rng(1)
    X = rng.uniform(1, 500, size=(3, 5))
    P = preprocess.closure(X)
    P = preprocess.multiplicative_replacement(P)
    Z = preprocess.ilr(P)
    C = preprocess.clr(P)
    np.testing.assert_allclose(
        np.linalg.norm(Z[0] - Z[1]),
        np.linalg.norm(C[0] - C[1]),
        atol=1e-9,
    )


def test_ilr_rejects_zeros():
    with pytest.raises(ValueError):
        preprocess.ilr(np.array([[0.5, 0.5, 0.0, 0.0, 0.0]]))


def test_archetype_clr_shape():
    names, arch_clr = composition.archetype_clr()
    assert names.shape == (len(composition.ARCHETYPES),)
    assert arch_clr.shape == (len(composition.ARCHETYPES), 5)
    np.testing.assert_allclose(arch_clr.sum(axis=1), 0.0, atol=1e-9)


def test_nearest_archetype_exact_matches():
    df = _df()
    clr, _ = composition.coordinates(df)
    nearest, distance = composition.nearest_archetype(clr)
    assert list(nearest) == ["bread", "cookie", "pound_cake"]
    # Archetype-exact recipes are at (near) zero Aitchison distance.
    np.testing.assert_allclose(distance, 0.0, atol=1e-6)


def test_nearest_archetype_returns_nonnegative_distances():
    df = _df()
    clr, _ = composition.coordinates(df)
    _, distance = composition.nearest_archetype(clr)
    assert np.all(distance >= 0.0)


def test_archtypes_match_book_parts():
    assert composition.ARCHETYPES["bread"] == [5, 3, 0, 0, 0]
    assert composition.ARCHETYPES["pie_dough"] == [3, 1, 0, 2, 0]
    assert composition.ARCHETYPES["cookie"] == [3, 0, 1, 2, 3]
    assert composition.ARCHETYPES["shortbread"] == [3, 0, 0, 2, 1]


def test_tetrahedron_matrix_folds_egg_into_liquid():
    df = _df()
    M = composition.tetrahedron_matrix(df)
    assert M.shape == (3, 4)
    # R1 (bread): flour=500, wet=300+0=300, fat=0, sugar=0
    np.testing.assert_allclose(M[0], [500.0, 300.0, 0.0, 0.0])
    # R2 (cookie): flour=300, wet=0+100=100, fat=200, sugar=300
    np.testing.assert_allclose(M[1], [300.0, 100.0, 200.0, 300.0])


def test_barycentric_3d_points_lie_in_tetrahedron():
    rng = np.random.default_rng(0)
    M = rng.uniform(0.1, 10, size=(50, 4))
    coords = composition.barycentric_3d(M)
    assert coords.shape == (50, 3)
    # Vertices span the tetrahedron; all points are convex combinations (>= 0
    # and bounded by the vertex extents).
    assert np.all(coords >= -1e-9)
    assert np.all(coords <= 1.0 + 1e-9)


def test_tetrahedron_fold_preserves_separation():
    # Folding egg into liquid keeps every pair of book archetypes at Aitchison
    # distance >= 0.4 (min 0.57, biscuit vs quick_bread) — the best of all ten
    # single-pair merges, which is why the tetrahedron uses flour / liquid+egg /
    # fat / sugar. This regression test documents that choice.
    M = composition.tetrahedron_archetypes()
    P = preprocess.closure(M)
    P = preprocess.multiplicative_replacement(P)
    C = preprocess.clr(P)
    D = np.linalg.norm(C[:, None, :] - C[None, :, :], axis=2)
    iu = np.triu_indices(len(composition.ARCHETYPES), k=1)
    assert D[iu].min() > 0.4


def test_tetrahedron_archetypes_shape():
    A = composition.tetrahedron_archetypes()
    assert A.shape == (len(composition.ARCHETYPES), 4)
    # bread: flour 5, liquid+egg 3+0, fat 0, sugar 0
    bread_idx = list(composition.ARCHETYPES).index("bread")
    assert A[bread_idx, 1] == 3.0
    assert A[bread_idx, 2] == 0.0
    assert A[bread_idx, 3] == 0.0
    # cookie: flour 3, liquid+egg 0+1, fat 2, sugar 3
    cookie_idx = list(composition.ARCHETYPES).index("cookie")
    assert A[cookie_idx, 1] == 1.0
    assert A[cookie_idx, 3] == 3.0
