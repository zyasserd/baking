"""Build the compact USDA SR Legacy reference CSV.

The flake fetches the SR Legacy archive, unzips it and keeps the three tables
this pipeline reads; the dev shell links that directory at
``config.FDC_TABLES_DIR`` (``data/raw/fdc``). This module compacts those tables
into one flat CSV per food:

    fdc_id,description,category,water_g,protein_g,fat_g,carb_g,fiber_g,sugar_g,
    ash_g,sodium_mg

All nutrient columns are per 100 g. Nutrient IDs live in ``config.FDC_NUTRIENT_IDS``.
There is no network access and no extraction here — both are nix's job
(flake.nix).
"""

from __future__ import annotations

import csv
import os

import config


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def build(tables_dir: str = config.FDC_TABLES_DIR, out_path: str = config.FDC_REFERENCE_CSV) -> str:
    nutrient_ids = config.FDC_NUTRIENT_IDS

    foods = {r["fdc_id"]: r for r in _read_csv(os.path.join(tables_dir, "food.csv"))}
    categories = {r["id"]: r["description"] for r in _read_csv(os.path.join(tables_dir, "food_category.csv"))}

    # fdc_id -> {nutrient_col: amount}; only keep the nutrients we care about.
    comp: dict[str, dict[str, float]] = {fid: {v: 0.0 for v in nutrient_ids.values()} for fid in foods}
    for row in _read_csv(os.path.join(tables_dir, "food_nutrient.csv")):
        nid = int(row["nutrient_id"])
        col = nutrient_ids.get(nid)
        if col is None:
            continue
        fid = row["fdc_id"]
        if fid in comp:
            try:
                comp[fid][col] = float(row["amount"])
            except ValueError:
                pass

    columns = ["fdc_id", "description", "category"] + list(nutrient_ids.values())
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for fid, meta in foods.items():
            category = categories.get(meta.get("food_category_id", ""), "")
            w.writerow(
                [fid, meta.get("description", ""), category]
                + [round(comp[fid][c], 3) for c in nutrient_ids.values()]
            )

    print(f"wrote {out_path} ({len(foods)} foods)")
    return out_path