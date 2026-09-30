"""Book archetypes and the tetrahedron fold for the analysis stage.

The book archetypes (Ruhlman's *Ratio*) are used only as reference points on
the simplex — never as labels. The 4-part tetrahedron sub-composition folds egg
into liquid ("wet") for the 3-D figure; the merge is chosen empirically
(documented in ``config.TETRAHEDRON_PARTS``).
"""

from __future__ import annotations

import numpy as np

import config

from . import coda


def archetype_matrix() -> tuple[np.ndarray, list[str]]:
    """(k, 5) mass matrix of the book archetypes, and their names."""
    names = list(config.ARCHETYPES.keys())
    A = np.array([config.ARCHETYPES[n] for n in names], dtype=float)
    return A, names


def _closed_archetypes() -> np.ndarray:
    A, _ = archetype_matrix()
    P = coda.closure(A)
    return coda.multiplicative_replacement(P)


def archetype_ilr() -> tuple[np.ndarray, np.ndarray]:
    """Return (names, ILR) for the book archetypes."""
    P = _closed_archetypes()
    return np.array(list(config.ARCHETYPES.keys())), coda.ilr(P)


def nearest_archetype(
    coords: np.ndarray,
    names: np.ndarray | None = None,
    arch_coords: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Assign each coordinate row to its nearest book archetype.

    Returns (archetype names, Aitchison distance to the nearest archetype).
    Aitchison distance is the Euclidean norm in any orthonormal log-ratio
    coordinate system (CLR or ILR — isometric transforms).
    """
    if names is None or arch_coords is None:
        names, arch_coords = archetype_ilr()
    coords = np.asarray(coords, dtype=float)
    arch_coords = np.asarray(arch_coords, dtype=float)

    # (n, k, D) differences -> (n, k) squared distances
    diff = coords[:, None, :] - arch_coords[None, :, :]
    dist2 = np.einsum("nkd,nkd->nk", diff, diff)
    idx = dist2.argmin(axis=1)
    return names[idx], np.sqrt(dist2[np.arange(coords.shape[0]), idx])


_TETRA_SOURCES = config.TETRAHEDRON_SOURCES


def tetrahedron_matrix(df) -> np.ndarray:
    """(n, 4) sub-composition [flour, liquid+egg, fat, sugar] (not yet closed)."""
    cols = []
    for sources in _TETRA_SOURCES:
        cols.append(df[sources].to_numpy(dtype=float).sum(axis=1))
    return np.column_stack(cols)


def tetrahedron_archetypes() -> np.ndarray:
    """(k, 4) mass matrix of the book archetypes in tetrahedron parts order."""
    idx = {p: i for i, p in enumerate(config.ANALYSIS_PARTS)}
    A = np.array([config.ARCHETYPES[n] for n in config.ARCHETYPES], dtype=float)
    out = np.zeros((len(config.ARCHETYPES), 4))
    out[:, 0] = A[:, idx["flour"]]
    out[:, 1] = A[:, idx["liquid"]] + A[:, idx["egg"]]
    out[:, 2] = A[:, idx["fat"]]
    out[:, 3] = A[:, idx["sugar"]]
    return out


def barycentric_3d(M: np.ndarray) -> np.ndarray:
    """Map a (n, 4) composition (rows summing to 1) onto a regular tetrahedron.

    The four vertices are flour=(0,0,0), liquid+egg=(1,0,0), fat=(0.5, √3/2, 0),
    sugar=(0.5, √3/6, √(2/3)); a point is the weighted sum of the vertices.
    """
    M = np.asarray(M, dtype=float)
    P = coda.closure(M)
    v0 = np.array([0.0, 0.0, 0.0])
    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([0.5, np.sqrt(3.0) / 2.0, 0.0])
    v3 = np.array([0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)])
    return (
        P[:, [0]] * v0
        + P[:, [1]] * v1
        + P[:, [2]] * v2
        + P[:, [3]] * v3
    )


def tetrahedron_vertices() -> np.ndarray:
    """(4, 3) coordinates of the four tetrahedron corners."""
    return np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0, 0.0],
            [0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)],
        ]
    )