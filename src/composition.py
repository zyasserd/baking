"""The 5-part baking simplex and its Aitchison geometry.

Each recipe is expressed as a composition of five structural parts — flour,
liquid, eggs, fat and sugar — normalized to sum to 1 (the "simplex"), following
Michael Ruhlman's *Ratio*. Salt, leavener, yeast and flavor add-ins (chocolate,
nuts, fruit, …) are deliberately excluded from the ratio, as in the book.

The simplex is not Euclidean, so all analysis (PCA, clustering, distances) runs
in log-ratio coordinates: the centered log-ratio (CLR, interpretable axes) and
the isometric log-ratio (ILR, orthonormal balances). See ``preprocess`` for the
underlying transforms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import preprocess

# The five parts, in the order used by the book's ratios.
PARTS = ["flour", "liquid", "egg", "fat", "sugar"]

# Gram columns that contribute to each part. Liquid folds water + milk (and
# cream/yogurt/buttermilk, which the parser already maps to ``milk_g``).
_PART_SOURCES: dict[str, list[str]] = {
    "flour": ["flour_g"],
    "liquid": ["water_g", "milk_g"],
    "egg": ["egg_g"],
    "fat": ["fat_g"],
    "sugar": ["sugar_g"],
}

# Book archetypes (Ruhlman's *Ratio*), parts by weight in PARTS order.
# Zeros are structural (e.g. bread has no egg/fat/sugar); they are handled by
# the same multiplicative-replacement used for the data.
#
# ``cookie`` is a drop cookie (3 flour : 1 egg : 2 fat : 3 sugar) and
# ``shortbread`` is the book's bare 1-2-3 ratio (1 sugar : 2 fat : 3 flour, no
# egg). Both map to the ``cookie`` family: as the book notes, real cookies
# almost always add egg (pulling them toward cake), so using the egg-bearing
# drop-cookie ratio keeps chocolate-chip cookies from being misread as pound
# cake, while the no-egg shortbread catches short cookies and wedding cookies.
ARCHETYPES: dict[str, list[float]] = {
    "bread":       [5, 3, 0, 0, 0],
    "pie_dough":   [3, 1, 0, 2, 0],
    "biscuit":     [3, 2, 0, 1, 0],
    "cookie":      [3, 0, 1, 2, 3],
    "shortbread":  [3, 0, 0, 2, 1],
    "choux":       [1, 2, 2, 1, 0],
    "pound_cake":  [1, 0, 1, 1, 1],
    "angel_food":  [1, 0, 3, 0, 3],
    "quick_bread": [2, 2, 1, 1, 0],
    "pancake":     [2, 2, 1, 0.5, 0],
    "crepe":       [0.5, 1, 1, 0, 0],
}


def parts_matrix(df: pd.DataFrame) -> np.ndarray:
    """Return an (n, 5) mass matrix [flour, liquid, egg, fat, sugar]."""
    columns = []
    for part in PARTS:
        cols = _PART_SOURCES[part]
        columns.append(df[cols].to_numpy(dtype=float).sum(axis=1))
    return np.column_stack(columns)


def compositions(df: pd.DataFrame) -> pd.DataFrame:
    """Per-recipe simplex proportions (rows sum to 1), with id/labels.

    The five ``*_p`` columns are the parts as fractions of the structural mass
    (not of the whole recipe — flavor add-ins are excluded). The ``link`` and
    ``source`` columns are carried through when present.
    """
    P = preprocess.closure(parts_matrix(df))
    meta = ["recipe_id", "name", "tag_coarse", "tag_fine"]
    meta += [c for c in ("tag_confidence", "link", "source") if c in df.columns]
    out = df[meta].copy()
    for i, part in enumerate(PARTS):
        out[f"{part}_p"] = P[:, i]
    return out


def coordinates(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return (CLR, ILR) coordinates for a recipe frame.

    Applies closure then multiplicative zero-replacement so both transforms are
    well-defined even though bread has zero sugar/egg/fat.
    """
    P = preprocess.closure(parts_matrix(df))
    P = preprocess.multiplicative_replacement(P)
    return preprocess.clr(P), preprocess.ilr(P)


def archetype_clr() -> tuple[np.ndarray, np.ndarray]:
    """Return (names, CLR) for the book archetypes.

    Uses the same closure + zero-replacement as the data so distances are
    comparable.
    """
    names = np.array(list(ARCHETYPES.keys()))
    A = np.array([ARCHETYPES[n] for n in names], dtype=float)
    P = preprocess.closure(A)
    P = preprocess.multiplicative_replacement(P)
    return names, preprocess.clr(P)


def archetype_ilr() -> tuple[np.ndarray, np.ndarray]:
    """Return (names, ILR) for the book archetypes (for UMAP/t-SNE embedding)."""
    names = np.array(list(ARCHETYPES.keys()))
    A = np.array([ARCHETYPES[n] for n in names], dtype=float)
    P = preprocess.closure(A)
    P = preprocess.multiplicative_replacement(P)
    return names, preprocess.ilr(P)


def nearest_archetype(
    clr: np.ndarray,
    names: np.ndarray | None = None,
    arch_clr: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Assign each CLR row to its nearest book archetype.

    Returns (archetype names, Aitchison distance to the nearest archetype).
    Aitchison distance between two compositions is the Euclidean norm of their
    CLR difference.
    """
    if names is None or arch_clr is None:
        names, arch_clr = archetype_clr()
    clr = np.asarray(clr, dtype=float)
    arch_clr = np.asarray(arch_clr, dtype=float)

    # (n, k, D) differences -> (n, k) squared distances
    diff = clr[:, None, :] - arch_clr[None, :, :]
    dist2 = np.einsum("nkd,nkd->nk", diff, diff)
    idx = dist2.argmin(axis=1)
    return names[idx], np.sqrt(dist2[np.arange(clr.shape[0]), idx])


# The 4-part sub-composition used to draw the 4-D simplex in 3-D. Folding
# fat+sugar into one "richness" axis keeps the book archetypes separated
# (min Aitchison distance 0.44, no collisions) while keeping sugar visible.
TETRAHEDRON_PARTS: list[str] = ["flour", "liquid", "egg", "fat+sugar"]

_TETRA_SOURCES: list[list[str]] = [
    ["flour_g"],
    ["water_g", "milk_g"],
    ["egg_g"],
    ["fat_g", "sugar_g"],
]


def tetrahedron_matrix(df: pd.DataFrame) -> np.ndarray:
    """(n, 4) sub-composition [flour, liquid, egg, fat+sugar] (not yet closed)."""
    cols = []
    for sources in _TETRA_SOURCES:
        cols.append(df[sources].to_numpy(dtype=float).sum(axis=1))
    return np.column_stack(cols)


def tetrahedron_archetypes() -> np.ndarray:
    """(k, 4) mass matrix of the book archetypes in tetrahedron parts order."""
    idx = {p: i for i, p in enumerate(PARTS)}
    A = np.array([ARCHETYPES[n] for n in ARCHETYPES], dtype=float)
    out = np.zeros((len(ARCHETYPES), 4))
    out[:, 0] = A[:, idx["flour"]]
    out[:, 1] = A[:, idx["liquid"]]
    out[:, 2] = A[:, idx["egg"]]
    out[:, 3] = A[:, idx["fat"]] + A[:, idx["sugar"]]
    return out


def barycentric_3d(M: np.ndarray) -> np.ndarray:
    """Map a (n, 4) composition (rows summing to 1) onto a regular tetrahedron.

    The four vertices are flour=(0,0,0), liquid=(1,0,0), egg=(0.5, √3/2, 0),
    fat+sugar=(0.5, √3/6, √(2/3)); a point is the weighted sum of the vertices.
    """
    M = np.asarray(M, dtype=float)
    P = preprocess.closure(M)
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
