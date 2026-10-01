"""STAGE 2 entry point — the preprocessed dataset -> results.

The pipeline itself lives in ``src.method.pipeline``; this script only
parses flags. It reads only the preprocessed dataset (``--input``, default
``data/processed/recipes_simplex.csv``) plus ``config``, and writes the
results — the Aid, plus maintainer diagnostics — under ``--outdir``.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.method import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: analyze the preprocessed dataset.")
    parser.add_argument("--input", default=config.PROCESSED_RECIPES_CSV, help="Preprocessed dataset path")
    parser.add_argument("--outdir", default=config.OUTPUT_DIR, help="Directory for output files")
    args = parser.parse_args()

    pipeline.run(args.input, args.outdir)


if __name__ == "__main__":
    main()