"""STAGE 1 entry point — raw corpora -> the preprocessed recipe dataset.

The pipeline itself lives in ``src.preprocess.pipeline``; this script only
parses flags and prints the run report. Requires the manually-downloaded
Kaggle ``RAW_recipes.csv`` (see flake.nix / README).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

from src.preprocess import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: build the preprocessed recipe dataset.")
    parser.add_argument("--rnlg", default=config.RAW_RECIPE_NLG_CSV, help="RecipeNLG_dataset.csv path")
    parser.add_argument("--food", default=config.RAW_FOOD_RECIPES_CSV, help="Food.com RAW_recipes.csv path")
    parser.add_argument("--out", default=config.PROCESSED_RECIPES_CSV, help="Output dataset path")
    parser.add_argument("--interim", default=config.INTERIM_INGREDIENTS_CSV, help="Per-ingredient database path")
    parser.add_argument("--limit", type=int, default=None, help="Only read this many RecipeNLG rows")
    args = parser.parse_args()

    stats = pipeline.build(args.rnlg, args.food, args.out, args.interim, args.limit)
    print(f"RecipeNLG rows read:   {stats['total']}")
    print(f"food.com rows:         {stats['food_rows']}")
    print(f"joined to Food.com:    {stats['joined']}")
    print(f"excluded (not scratch):{stats['excluded']}")
    print(f"flourless dropped:     {stats['flourless']}")
    print(f"kept (labeled):        {stats['kept']}")
    print(f"non-baked sections:    {stats['nonbaked_components']} recipes had frosting/glaze dropped")
    print(f"wrote {args.out}")
    print(f"wrote {args.interim}")


if __name__ == "__main__":
    main()