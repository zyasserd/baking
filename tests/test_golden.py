"""Golden-file test: the committed dataset is deterministic, pin it.

The pipeline is fully deterministic (seeded, sorted iteration), so stage-1
re-runs must reproduce ``data/processed/recipes_simplex.csv`` byte-for-byte.
This test pins its hash so ANY unintended change — a parse tweak, a dependency
upgrade, a config drift — fails loudly here instead of silently altering the
dataset that every result is built on.

If a pipeline change SHOULD change the dataset: verify the diff is exactly
what you intended, then update ``GOLDEN_SHA256`` in this file as a deliberate,
reviewable act.
"""

import hashlib

DATASET = "data/processed/recipes_simplex.csv"

# 2026-09: after soymilk/plant-milk base fix, nuts curation, phrase-check
# reorder, non-structural purpose lines, pinch/dash masses, produce-water rule.
GOLDEN_SHA256 = "e8fafbdc7e06e2d0a8a4a3da459ad57f7b65261d8d3ea02c47e549aa2b56d7af"


def test_golden_dataset_unchanged():
    with open(DATASET, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    assert digest == GOLDEN_SHA256, (
        f"{DATASET} changed (sha256 {digest}). The dataset is committed and "
        "every result is built on it — verify the diff is intended, then "
        "update GOLDEN_SHA256 in tests/test_golden.py deliberately."
    )
