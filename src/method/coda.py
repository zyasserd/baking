"""Compositional transforms: closure, zero replacement, CLR and ILR.

Stage 1 writes per-recipe simplex proportions (``*_p`` columns summing to 1);
the dataset contract lives in ``src.dataset`` (schema, validation, loading).
This module provides the log-ratio transforms the method uses to place
recipes as balances on the simplex.
"""

from __future__ import annotations

import numpy as np

import config


def closure(X: np.ndarray) -> np.ndarray:
    """Normalize each row of X to sum to 1 (map recipes onto the simplex)."""
    X = np.asarray(X, dtype=float)
    row_sums = X.sum(axis=1, keepdims=True)
    if np.any(row_sums <= 0):
        raise ValueError("closure: every row must have a positive sum")
    return X / row_sums


def multiplicative_replacement(P: np.ndarray) -> np.ndarray:
    """Replace zeros with a per-row delta and re-normalize.

    For each row, delta = ``config.ZERO_REPLACEMENT_DELTA`` * min(positive
    values in the row). Every zero is set to delta, then the row is
    re-normalized to sum to 1 (multiplicative replacement as in
    Martin-Fernandez et al.).
    """
    P = np.asarray(P, dtype=float).copy()
    if np.any(P < 0):
        raise ValueError("multiplicative_replacement: proportions must be >= 0")

    zeros = P == 0
    # min positive per row (rows with no zeros get +inf delta, which is unused)
    min_positive = np.where(P > 0, P, np.inf).min(axis=1, keepdims=True)
    delta = config.ZERO_REPLACEMENT_DELTA * min_positive

    P = np.where(zeros, delta, P)
    return P / P.sum(axis=1, keepdims=True)


def clr(P: np.ndarray) -> np.ndarray:
    """Centered log-ratio transform (rows -> zero-sum log space)."""
    P = np.asarray(P, dtype=float)
    if np.any(P <= 0):
        raise ValueError("clr: proportions must be strictly positive (apply replacement first)")
    log_P = np.log(P)
    return log_P - log_P.mean(axis=1, keepdims=True)


def _pivot_psi(D: int) -> np.ndarray:
    """(D-1, D) orthonormal pivot-balance basis: part k vs the geometric mean
    of the parts after it."""
    psi = np.zeros((D - 1, D))
    for k in range(D - 1):
        coef = np.sqrt((D - k - 1) / (D - k))
        psi[k, k] = coef
        psi[k, k + 1:] = -coef / (D - k - 1)
    return psi


def ilr(P: np.ndarray, psi: np.ndarray | None = None) -> np.ndarray:
    """Isometric log-ratio transform (rows -> orthonormal R^(D-1) balances).

    By default uses the sequential binary partition (pivot balances) where the
    k-th coordinate contrasts part k against the geometric mean of the parts
    that follow it:

        z_k = sqrt((D-k-1) / (D-k)) * log( x_k / g(x_{k+1}, ..., x_{D-1}) )

    Euclidean distance in this space equals the Aitchison distance, so it is
    the right coordinate system for clustering on the simplex.
    """
    P = np.asarray(P, dtype=float)
    if np.any(P <= 0):
        raise ValueError("ilr: proportions must be strictly positive (apply replacement first)")

    D = P.shape[1]
    if psi is not None:
        psi = np.asarray(psi, dtype=float)
        if psi.shape != (D - 1, D):
            raise ValueError("ilr: psi must have shape (D-1, D)")
        log_P = np.log(P)
        Z = np.zeros((P.shape[0], D - 1))
        for k, row in enumerate(psi):
            pos = row > 0
            neg = row < 0
            r = int(pos.sum())
            s = int(neg.sum())
            coef = np.sqrt(r * s / (r + s))
            Z[:, k] = coef * (
                log_P[:, pos].mean(axis=1) - log_P[:, neg].mean(axis=1)
            )
        return Z

    return np.log(P) @ _pivot_psi(D).T


def ilr_inverse(Z: np.ndarray) -> np.ndarray:
    """Inverse of the default ILR: balances -> simplex proportions.

    The pivot-balance basis is orthonormal, so the CLR vector is the balances
    carried back through the basis transpose; exponentiating and closing gives
    the composition. Used to map statistics computed in ILR space (class
    centroids) back onto the simplex for display.
    """
    Z = np.asarray(Z, dtype=float)
    psi = _pivot_psi(Z.shape[1] + 1)
    return closure(np.exp(Z @ psi))
