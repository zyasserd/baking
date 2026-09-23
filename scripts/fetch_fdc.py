"""Fetch USDA FoodData Central SR Legacy and build a compact reference CSV.

Downloads the SR Legacy archive (the final Standard Reference release, ~7,800
foods with full proximate composition), extracts it, and writes one flat CSV
per food with the nutrients needed to decompose an ingredient into baking parts:

    fdc_id,description,category,water_g,protein_g,fat_g,carb_g,fiber_g,sugar_g,
    ash_g,sodium_mg

All nutrient columns are per 100 g. Nutrient IDs (FDC ``nutrient.csv``):

    1051 Water, 1003 Protein, 1004 Total lipid, 1005 Carbohydrate by difference,
    1079 Fiber, 2000 Total sugars, 1007 Ash, 1093 Sodium.

Run once; the archive and CSV are cached so this is idempotent.
"""

from __future__ import annotations

import argparse
import csv
import os
import urllib.request
import zipfile

URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"

NUTRIENT_IDS = {
    1051: "water_g",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carb_g",
    1079: "fiber_g",
    2000: "sugar_g",
    1007: "ash_g",
    1093: "sodium_mg",
}


def _download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        print(f"already present: {dest}")
        return
    print(f"downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)


def _extract(zip_path: str, dest_dir: str) -> None:
    marker = os.path.join(dest_dir, "food.csv")
    if os.path.exists(marker):
        return
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def build(ref_dir: str) -> str:
    zip_path = os.path.join(ref_dir, "sr_legacy.zip")
    extract_dir = os.path.join(ref_dir, "FoodData_Central_sr_legacy_food_csv_2018-04")

    _download(URL, zip_path)
    _extract(zip_path, ref_dir)

    foods = {r["fdc_id"]: r for r in _read_csv(os.path.join(extract_dir, "food.csv"))}
    categories = {r["id"]: r["description"] for r in _read_csv(os.path.join(extract_dir, "food_category.csv"))}

    # fdc_id -> {nutrient_col: amount}; only keep the nutrients we care about.
    comp: dict[str, dict[str, float]] = {fid: {v: 0.0 for v in NUTRIENT_IDS.values()} for fid in foods}
    for row in _read_csv(os.path.join(extract_dir, "food_nutrient.csv")):
        nid = int(row["nutrient_id"])
        col = NUTRIENT_IDS.get(nid)
        if col is None:
            continue
        fid = row["fdc_id"]
        if fid in comp:
            try:
                comp[fid][col] = float(row["amount"])
            except ValueError:
                pass

    out_path = os.path.join(ref_dir, "fdc_srlegacy.csv")
    columns = ["fdc_id", "description", "category"] + list(NUTRIENT_IDS.values())
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for fid, meta in foods.items():
            category = categories.get(meta.get("food_category_id", ""), "")
            w.writerow(
                [fid, meta.get("description", ""), category]
                + [round(comp[fid][c], 3) for c in NUTRIENT_IDS.values()]
            )

    print(f"wrote {out_path} ({len(foods)} foods)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the SR Legacy reference CSV.")
    parser.add_argument("--ref-dir", default="data/reference")
    args = parser.parse_args()
    build(args.ref_dir)


if __name__ == "__main__":
    main()
