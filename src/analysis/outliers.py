"""Outlier elimination in Aitchison (ILR) space.

The simplex is not Euclidean, so outliers are found using the isometric
log-ratio coordinates, where Euclidean distance equals the Aitchison distance.
A robust Mahalanobis distance (Minimum Covariance Determinant) flags
parse-error outliers before anything else looks at the data. The contamination
fraction and seed live in the ANALYSIS section of ``config``.
"""

from __future__ import annotations

import numpy as np
from sklearn.covariance import EllipticEnvelope

import config


def detect_outliers(ilr: np.ndarray, contamination: float | None = None,
                    seed: int | None = None) -> np.ndarray:
    """Boolean inlier mask from robust Mahalanobis distance in ILR space.

    ``EllipticEnvelope`` fits a robust (Minimum Covariance Determinant)
    Gaussian; points beyond the ``contamination`` tail are flagged as outliers.
    Defaults come from ``config``.
    """
    ilr = np.asarray(ilr, dtype=float)
    if len(ilr) < 10:
        return np.ones(len(ilr), dtype=bool)
    if contamination is None:
        contamination = config.OUTLIER_CONTAMINATION
    if seed is None:
        seed = config.RANDOM_SEED
    detector = EllipticEnvelope(contamination=contamination, random_state=seed)
    labels = detector.fit_predict(ilr)  # +1 inlier, -1 outlier
    return labels == 1