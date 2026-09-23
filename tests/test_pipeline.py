"""Unit tests for the baking-ratio pipeline."""

import numpy as np
import pytest

from src import preprocess


def test_closure_pound_cake_four_equal():
    X = np.array([[100, 100, 100, 100, 0, 0]], dtype=float)
    P = preprocess.closure(X)
    np.testing.assert_allclose(P[0, :4], 0.25)
    np.testing.assert_allclose(P[0, 4:], 0.0)


def test_closure_sums_to_one():
    rng = np.random.default_rng(0)
    X = rng.uniform(1, 500, size=(50, 6))
    P = preprocess.closure(X)
    np.testing.assert_allclose(P.sum(axis=1), 1.0, atol=1e-9)


def test_multiplicative_replacement_sums_to_one_and_fills_zeros():
    P = np.array([[0.25, 0.25, 0.25, 0.25, 0.0, 0.0]])
    Q = preprocess.multiplicative_replacement(P)
    assert np.all(Q > 0)
    np.testing.assert_allclose(Q.sum(axis=1), 1.0, atol=1e-9)
    # The four original non-zero entries stay in the same ratio.
    np.testing.assert_allclose(Q[0, :4] / Q[0, 0], 1.0)


def test_multiplicative_replacement_noop_without_zeros():
    P = np.array([[0.5, 0.5, 0.0, 0.0, 0.0, 0.0]])
    Q = preprocess.multiplicative_replacement(P)
    np.testing.assert_allclose(Q.sum(), 1.0, atol=1e-9)


def test_clr_row_means_are_zero():
    rng = np.random.default_rng(1)
    X = rng.uniform(1, 500, size=(30, 6))
    P = preprocess.closure(X)
    P = preprocess.multiplicative_replacement(P)
    Y = preprocess.clr(P)
    np.testing.assert_allclose(Y.mean(axis=1), 0.0, atol=1e-9)
