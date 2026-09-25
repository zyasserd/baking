"""STAGE 1 — Preprocess: raw corpora -> the preprocessed recipe dataset.

Joins the RecipeNLG corpus (ingredient text) with the Food.com corpus
(independent tag labels + nutrition) on the numeric Food.com recipe id at the
end of the RecipeNLG ``link`` (``www.food.com/recipe/<slug>-<id>``), then turns
every kept recipe into structural baking parts.

Per recipe:

1. tags are resolved to a class (``src.preprocess.tags``; title rescues for the
   under-tagged pastry and brownies classes),
2. non-scratch recipes are dropped (``src.preprocess.filters``),
3. each ingredient line is parsed (``src.preprocess.parse``), converted to grams
   (``src.preprocess.density``), and — if *significant* (``src.preprocess.
   significance``) — decomposed into structural part weights from USDA SR Legacy
   (``src.preprocess.ingredients``): add-ins are zeroed, keeping only
   flour/liquid/egg/fat/sugar + functional parts,
4. non-baked sections (frosting, glaze, icing, ...) are skipped so decorations
   never pool into the batter's ratio,
5. the structural grams fold into 5-part simplex proportions that sum to 1
   (``src.preprocess.parts``).

Outputs (see config DATA section):

- ``data/interim/ingredients.csv`` — the per-ingredient database: every
  significant ingredient with its grams, role, and USDA part proportions
  (summing to 1). Provenance for the recipe-level numbers.
- ``data/processed/recipes_simplex.csv`` — one row per kept recipe: identity +
  url + tags + structural part grams + simplex proportions (sum to 1) + flags +
  Food.com nutrition.

The Food.com file must be downloaded manually (Kaggle login; see flake.nix) —
its sha256 is pinned in ``config.RAW_RECIPES_SHA256`` and verified here.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import config

from src.preprocess import (
    density,
    filters,
    fdc as fdc_module,
    ingredients,
    parse,
    parts,
    significance,
    tags,
)

_FOOD_ID_RE = re.compile(r"food\.com/recipe/.*?(\d+)\s*$")

# Food.com's per-recipe `nutrition` list, in positional order.
_NUTRITION_COLUMNS = [
    "calories",
    "nutrition_fat",
    "nutrition_sugar",
    "nutrition_sodium",
    "nutrition_protein",
    "nutrition_satfat",
    "nutrition_carbs",
]

_GRAM_COLUMNS = [f"{part}_g" for part in config.INGREDIENT_PARTS]
_PROPORTION_COLUMNS = parts.proportion_columns()

INTERIM_COLUMNS = (
    ["recipe_id", "seq", "section", "raw", "head", "qty", "unit", "note", "grams",
     "role", "primary_part", "significant"]
    + [f"{p}_p" for p in config.INGREDIENT_PARTS]
    + ["structural"]
)

OUTPUT_COLUMNS = (
    ["recipe_id", "name", "tag_coarse", "tag_fine", "tag_confidence", "url", "source"]
    + _GRAM_COLUMNS
    + _PROPORTION_COLUMNS
    + ["n_significant", "mass_significant_frac"]
    + ["has_yeast", "has_chemical_leavener", "has_egg", "has_fat", "has_sugar"]
    + _NUTRITION_COLUMNS
    + ["tags_raw", "ingredients_raw"]
)


def _literal_list(value: str) -> list[str] | None:
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    if isinstance(parsed, str):
        return [parsed]
    return None


def verify_food_dataset(path: str = config.RAW_FOOD_RECIPES_CSV) -> None:
    """Verify the pinned sha256 of the manually-downloaded RAW_recipes.csv."""
    if not os.path.exists(path):
        raise SystemExit(
            f"missing {path}\n"
            "download RAW_recipes.csv (login required) from\n"
            "  https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions\n"
            "into data/raw/food/ — the expected sha256 is pinned in config.RAW_FOOD_RECIPES_SHA256"
        )
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != config.RAW_FOOD_RECIPES_SHA256:
        raise SystemExit(
            f"{path} does not match the pinned sha256 {config.RAW_FOOD_RECIPES_SHA256}\n"
            "make sure the file is the original RAW_recipes.csv from the Kaggle dataset"
        )


def analyze_ingredients(ing_list: list[str]) -> tuple[list[dict], dict, int, float, bool]:
    """Decompose one recipe's ingredient list.

    Returns ``(interim_rows, structural_grams, n_significant,
    significant_mass_frac, dropped_nonbaked)``.

    Each ingredient is parsed, converted to grams, and — if significant or
    functional — accumulated into the structural part grams. The *full* USDA
    vector is used internally to pick each ingredient's primary part (for the
    density lookup) and its role, but only structural grams accumulate into the
    recipe; the interim rows carry the full per-ingredient proportions.
    """
    interim: list[dict] = []
    items: list[tuple[float, dict, str, bool]] = []
    in_nonbaked = False
    dropped_nonbaked = False
    section = ""

    for ing_str in ing_list:
        header = parse.component_header(ing_str)
        if header == "drop":
            in_nonbaked = True
            dropped_nonbaked = True
            continue
        if header == "keep":
            in_nonbaked = False
            section = ing_str.strip()
            continue
        if in_nonbaked:
            continue
        p = parse.parse_ingredient(ing_str)
        if not p.head:
            continue
        vec_full, role = ingredients.resolve(p.head)
        primary = ingredients.primary_part(vec_full)
        grams = density.to_grams(primary, p.qty, p.unit, p.head, p.note)
        if grams is None or grams <= 0:
            continue
        functional = primary in config.FUNCTIONAL_PARTS
        items.append((grams, vec_full, role, functional))
        interim.append({
            "recipe_id": None,
            "seq": None,
            "section": section,
            "raw": p.raw,
            "head": p.head,
            "qty": p.qty,
            "unit": p.unit,
            "note": p.note,
            "grams": grams,
            "role": role,
            "primary_part": primary or "",
            "significant": None,  # fixed below
            "structural": 1 if role == "base" else 0,
            "_vec": vec_full,
            "_functional": functional,
        })

    total = sum(g for g, *_ in items)
    struct = {col: 0.0 for col in _GRAM_COLUMNS}
    n_sig = 0
    sig_mass = 0.0

    for row, (grams, vec_full, role, functional) in zip(interim, items):
        sig = significance.qualifies(grams, total, functional)
        row["significant"] = int(sig)
        # Full USDA part proportions (closed over the tracked parts).
        vec_sum = sum(vec_full.values())
        for part in config.INGREDIENT_PARTS:
            row[f"{part}_p"] = round(vec_full.get(part, 0.0) / vec_sum, 6) if vec_sum > 0 else 0.0
        if not sig or not vec_full:
            continue
        n_sig += 1
        sig_mass += grams
        if role == "base":
            for part, frac in vec_full.items():
                col = f"{part}_g"
                if col in struct:
                    struct[col] += grams * vec_full[part]

    mass_frac = sig_mass / total if total > 0 else 0.0
    return interim, struct, n_sig, mass_frac, dropped_nonbaked


def load_food_meta(path: str) -> dict[int, dict]:
    """Load Food.com id -> {tags, ingredients, nutrition} (all we need)."""
    meta: dict[int, dict] = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        idx = {name: i for i, name in enumerate(header)}
        id_col, tags_col = idx["id"], idx["tags"]
        ing_col, nut_col = idx["ingredients"], idx["nutrition"]
        for row in reader:
            try:
                rid = int(row[id_col])
            except (ValueError, IndexError):
                continue
            meta[rid] = {
                "tags": _literal_list(row[tags_col]) or [],
                "ingredients": _literal_list(row[ing_col]) or [],
                "nutrition": _literal_list(row[nut_col]) or [],
            }
    return meta


def classify_recipe(title: str, tags_raw: list[str]) -> tuple[str, str, str] | None:
    """Resolve tags (+ title rescues) to a ``(coarse, fine, confidence)`` label.

    Brownie title-rescue: Food.com files brownies under the generic
    "bar-cookies" leaf, so the explicit brownies leaf is tiny; a title naming a
    brownie/blondie overrides a generic cookie tag. The pastry name-rescue only
    applies when tags are weak or absent; it never overrides a strong/medium
    tag assignment.
    """
    classified = tags.classify(tags_raw)

    if classified is not None and classified[0] == "cookie" and tags.is_brownie_title(title):
        return "brownies", "title_rescue", "medium"

    if (classified is None or classified[2] == "weak") and tags.is_pastry_title(title):
        return "pie_pastry", "title_rescue", "medium"
    if (classified is None or classified[2] == "weak") and tags.is_brownie_title(title):
        return "brownies", "title_rescue", "medium"
    return classified


def build(
    rnlg_path: str,
    food_path: str,
    out_path: str,
    interim_path: str,
    limit: int | None = None,
) -> dict:
    verify_food_dataset(food_path)

    # The USDA reference is derived from the flake-fetched archive; build it
    # once here so stage 1 is self-sufficient.
    if not os.path.exists(config.FDC_REFERENCE_CSV):
        fdc_module.build()

    food_meta = load_food_meta(food_path)

    rows: list[dict] = []
    interim_rows: list[dict] = []
    stats = {
        "total": 0,
        "food_rows": 0,
        "joined": 0,
        "excluded": 0,
        "flourless": 0,
        "kept": 0,
        "nonbaked_components": 0,
    }
    seen_ids: set[int] = set()

    with open(rnlg_path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for record in reader:
            stats["total"] += 1
            if limit is not None and stats["total"] > limit:
                break

            if len(record) < 6:
                continue
            title = record[1]
            ingredients_raw = record[2]
            url = record[4]
            source = record[5]

            if "food.com/recipe/" not in url:
                continue
            stats["food_rows"] += 1

            m = _FOOD_ID_RE.search(url)
            if not m:
                continue
            food_id = int(m.group(1))
            if food_id in seen_ids or food_id not in food_meta:
                continue
            seen_ids.add(food_id)
            stats["joined"] += 1

            meta = food_meta[food_id]
            classified = classify_recipe(title, meta["tags"])
            if classified is None:
                continue

            ing_list = _literal_list(ingredients_raw)
            if ing_list is None:
                continue

            if filters.is_excluded(title, ing_list):
                stats["excluded"] += 1
                continue

            interim, struct, n_sig, sig_frac, dropped_nonbaked = analyze_ingredients(ing_list)
            if dropped_nonbaked:
                stats["nonbaked_components"] += 1
            if struct["flour_g"] <= 0:
                stats["flourless"] += 1
                continue

            for i, row in enumerate(interim):
                row["recipe_id"] = str(food_id)
                row["seq"] = i
            interim_rows.extend(interim)

            # Fold the structural grams into 5-part proportions (sum to 1).
            grams_df = pd.DataFrame([struct])
            props = parts.proportions(grams_df)[0]

            nutrition = meta["nutrition"][:7]
            nutrition = nutrition + ["0"] * (7 - len(nutrition))
            try:
                nut = [float(x) for x in nutrition]
            except ValueError:
                nut = [0.0] * 7

            row = {
                "recipe_id": str(food_id),
                "name": title,
                "tag_coarse": classified[0],
                "tag_fine": classified[1],
                "tag_confidence": classified[2],
                "url": url,
                "source": source,
            }
            row.update({col: round(struct[col], 1) for col in _GRAM_COLUMNS})
            row.update({pc: round(float(pr), 6) for pc, pr in zip(_PROPORTION_COLUMNS, props)})
            row["n_significant"] = n_sig
            row["mass_significant_frac"] = round(sig_frac, 4)
            row["has_yeast"] = 1 if struct["yeast_g"] > 0 else 0
            row["has_chemical_leavener"] = 1 if struct["leavener_g"] > 0 else 0
            row["has_egg"] = 1 if struct["egg_g"] > 0 else 0
            row["has_fat"] = 1 if struct["fat_g"] > 0 else 0
            row["has_sugar"] = 1 if struct["sugar_g"] > 0 else 0
            row.update(dict(zip(_NUTRITION_COLUMNS, nut)))
            row["tags_raw"] = str(meta["tags"])
            row["ingredients_raw"] = str(meta["ingredients"])
            rows.append(row)
            stats["kept"] += 1

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    df.to_csv(out_path, index=False)

    interim_df = pd.DataFrame(interim_rows, columns=[c for c in INTERIM_COLUMNS])
    os.makedirs(os.path.dirname(interim_path) or ".", exist_ok=True)
    interim_df.to_csv(interim_path, index=False)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: build the preprocessed recipe dataset.")
    parser.add_argument("--rnlg", default=config.RAW_RECIPE_NLG_CSV, help="RecipeNLG_dataset.csv path")
    parser.add_argument("--food", default=config.RAW_FOOD_RECIPES_CSV, help="Food.com RAW_recipes.csv path")
    parser.add_argument("--out", default=config.PROCESSED_RECIPES_CSV, help="Output dataset path")
    parser.add_argument("--interim", default=config.INTERIM_INGREDIENTS_CSV, help="Per-ingredient database path")
    parser.add_argument("--limit", type=int, default=None, help="Only read this many RecipeNLG rows")
    args = parser.parse_args()

    stats = build(args.rnlg, args.food, args.out, args.interim, args.limit)
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