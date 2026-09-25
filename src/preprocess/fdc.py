"""Build the compact USDA SR Legacy reference CSV from the flake-fetched zip.

The SR Legacy archive is fetched by the flake (pinned sha256) into
``config.FDC_ZIP``. This module extracts it (cached, idempotent) and writes one
flat CSV per food with the nutrients needed to decompose an ingredient into
baking parts:

    fdc_id,description,category,water_g,protein_g,fat_g,carb_g,fiber_g,sugar_g,
    ash_g,sodium_mg

All nutrient columns are per 100 g. Nutrient IDs live in ``config.FDC_NUTRIENT_IDS``.
There is no network access here — downloading is nix's job (flake.nix).
"""

from __future__ import annotations

import csv
import os
import zipfile

import config


def _extract(zip_path: str, dest_dir: str) -> str:
    """Extract the archive; return the directory holding food.csv."""
    marker = os.path.join(dest_dir, "food.csv")
    if not os.path.exists(marker):
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
    # The zip contains a single top-level directory.
    for name in os.listdir(dest_dir):
        if name.startswith("FoodData_Central"):
            return os.path.join(dest_dir, name)
    return dest_dir


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def build(zip_path: str = config.FDC_ZIP, out_path: str = config.FDC_REFERENCE_CSV) -> str:
    nutrient_ids = config.FDC_NUTRIENT_IDS
    ref_dir = os.path.dirname(zip_path)
    extract_dir = _extract(zip_path, ref_dir)

    foods = {r["fdc_id"]: r for r in _read_csv(os.path.join(extract_dir, "food.csv"))}
    categories = {r["id"]: r["description"] for r in _read_csv(os.path.join(extract_dir, "food_category.csv"))}

    # fdc_id -> {nutrient_col: amount}; only keep the nutrients we care about.
    comp: dict[str, dict[str, float]] = {fid: {v: 0.0 for v in nutrient_ids.values()} for fid in foods}
    for row in _read_csv(os.path.join(extract_dir, "food_nutrient.csv")):
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