"""Build a gram-level, tag-labeled baking dataset from RecipeNLG + Food.com.

RecipeNLG provides quantities; Food.com provides the *independent* tags that
label each recipe. The two are joined on the numeric Food.com recipe id at the
end of the RecipeNLG ``link`` (``www.food.com/recipe/<slug>-<id>``).

Preprocessing (see README):

1. parse each ingredient line to ``<qty> <unit> <head> <props>`` (``src.parse``),
2. convert to grams (``src.density``, name-aware densities + container defaults),
3. keep ingredients whose mass is *significant* (``src.significance``) or that
   are functional (leavener/salt/yeast),
4. decompose each head into structural part weights from USDA SR Legacy
   (``src.ingredients``): add-ins are zeroed (Ruhlman's convention — validated
   empirically, the add-in-excluding decomposition classifies better),
   keeping only flour/liquid/egg/fat/sugar + functional parts.

Only Food.com recipes that are (a) present in RecipeNLG, (b) classified into a
baked-good class by ``src.tags``, and (c) have ``flour_g > 0`` are kept. The
``dessert_other`` weak tier is kept but marked ``tag_confidence == weak``.

Output schema (one row per Food.com recipe, structural grams)::

    recipe_id,name,tag_coarse,tag_fine,tag_confidence,link,source,
    flour_g,sugar_g,fat_g,egg_g,milk_g,water_g,salt_g,leavener_g,yeast_g,
    n_significant,mass_significant_frac,
    has_yeast,has_chemical_leavener,has_egg,has_fat,has_sugar,
    calories,nutrition_fat,nutrition_sugar,nutrition_sodium,nutrition_protein,
    nutrition_satfat,nutrition_carbs,tags_raw,ingredients_raw
"""

from __future__ import annotations

import argparse
import ast
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import density, filters, ingredients, parse, significance, tags, units

CATEGORY_COLUMNS = {
    "flour": "flour_g",
    "sugar": "sugar_g",
    "fat": "fat_g",
    "egg": "egg_g",
    "milk": "milk_g",
    "water": "water_g",
    "salt": "salt_g",
    "leavener": "leavener_g",
    "yeast": "yeast_g",
}

_STRUCT_COLUMNS = {part: f"{part}_g" for part in CATEGORY_COLUMNS}
_STRUCT_COLUMN_ORDER = [_STRUCT_COLUMNS[part] for part in CATEGORY_COLUMNS]

OUTPUT_COLUMNS = (
    ["recipe_id", "name", "tag_coarse", "tag_fine", "tag_confidence", "link", "source"]
    + _STRUCT_COLUMN_ORDER
    + ["n_significant", "mass_significant_frac"]
    + ["has_yeast", "has_chemical_leavener", "has_egg", "has_fat", "has_sugar"]
    + [
        "calories",
        "nutrition_fat",
        "nutrition_sugar",
        "nutrition_sodium",
        "nutrition_protein",
        "nutrition_satfat",
        "nutrition_carbs",
        "tags_raw",
        "ingredients_raw",
    ]
)

_FOOD_ID_RE = re.compile(r"food\.com/recipe/.*?(\d+)\s*$")


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


def analyze_ingredients(ing_list: list[str]) -> tuple[dict, dict, int, float, bool]:
    """Return (structural grams, n_significant, significant_mass_frac, dropped_nonbaked).

    Each ingredient is parsed, converted to grams, and — if significant or
    functional — decomposed into its structural part vector (add-ins zeroed).
    The *full* USDA vector is still used internally to pick each ingredient's
    primary part (for the density lookup) and to decide significance, but only
    the structural grams are accumulated. Component headers ("Cream Cheese
    Filling", "for the glaze:") split multi-component recipes; lines under a
    *non-baked* header (frosting, glaze, icing, …) are skipped so decorations
    never pool into the batter's ratio.
    """
    items: list[tuple[str, float, dict, str, bool]] = []
    in_nonbaked = False
    dropped_nonbaked = False
    for ing_str in ing_list:
        header = parse.component_header(ing_str)
        if header == "drop":
            in_nonbaked = True
            dropped_nonbaked = True
            continue
        if header == "keep":
            in_nonbaked = False
            continue
        if in_nonbaked:
            continue
        p = parse.parse_ingredient(ing_str)
        if not p.head:
            continue
        vec_full = ingredients.decompose(p.head, "full")
        primary = max(vec_full, key=vec_full.get) if vec_full else "other"
        grams = density.to_grams(primary, p.qty, p.unit, p.head, p.note)
        if grams is None or grams <= 0:
            continue
        functional = primary in significance.FUNCTIONAL_PARTS
        items.append((p.head, grams, vec_full, primary, functional))

    total = sum(g for _, g, *_ in items)
    struct = {col: 0.0 for col in _STRUCT_COLUMN_ORDER}
    n_sig = 0
    sig_mass = 0.0

    for head, grams, vec_full, _, functional in items:
        if not vec_full or not significance.qualifies(grams, total, functional):
            continue
        n_sig += 1
        sig_mass += grams
        vec_struct = ingredients.decompose(head, "structural")
        for part, frac in vec_struct.items():
            col = _STRUCT_COLUMNS.get(part)
            if col:
                struct[col] += grams * frac

    mass_frac = sig_mass / total if total > 0 else 0.0
    return struct, n_sig, mass_frac, dropped_nonbaked


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
            tags_raw = _literal_list(row[tags_col]) or []
            ingredients_raw = _literal_list(row[ing_col]) or []
            nutrition = _literal_list(row[nut_col]) or []
            meta[rid] = {
                "tags": tags_raw,
                "ingredients": ingredients_raw,
                "nutrition": nutrition,
            }
    return meta


def build(
    rnlg_path: str,
    food_path: str,
    out_path: str,
    limit: int | None = None,
) -> dict:
    food_meta = load_food_meta(food_path)

    rows: list[dict] = []
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
            link = record[4]
            source = record[5]

            if "food.com/recipe/" not in link:
                continue
            stats["food_rows"] += 1

            m = _FOOD_ID_RE.search(link)
            if not m:
                continue
            food_id = int(m.group(1))
            if food_id in seen_ids or food_id not in food_meta:
                continue
            seen_ids.add(food_id)
            stats["joined"] += 1

            meta = food_meta[food_id]
            classified = tags.classify(meta["tags"])

            # Brownie title-rescue: Food.com files brownies under the generic
            # "bar-cookies" leaf, so the explicit brownies leaf is tiny. A title
            # naming a brownie/blondie overrides a generic cookie tag.
            if (
                classified is not None
                and classified[0] == "cookie"
                and tags.is_brownie_title(title)
            ):
                classified = ("brownies", "title_rescue", "medium")

            # Name-rescue the under-tagged pie/pastry class only when tags are
            # weak or absent; never override a strong/medium tag assignment.
            if (
                classified is None or classified[2] == "weak"
            ) and tags.is_pastry_title(title):
                classified = ("pie_pastry", "title_rescue", "medium")
            elif (
                classified is None or classified[2] == "weak"
            ) and tags.is_brownie_title(title):
                classified = ("brownies", "title_rescue", "medium")

            if classified is None:
                continue

            ing_list = _literal_list(ingredients_raw)
            if ing_list is None:
                continue

            if filters.is_excluded(title, ing_list):
                stats["excluded"] += 1
                continue

            struct, n_sig, sig_frac, dropped_nonbaked = analyze_ingredients(ing_list)
            if dropped_nonbaked:
                stats["nonbaked_components"] += 1
            if struct["flour_g"] <= 0:
                stats["flourless"] += 1
                continue

            tag_coarse, tag_fine, tag_confidence = classified
            nutrition = meta["nutrition"][:7]
            nutrition = nutrition + ["0"] * (7 - len(nutrition))
            try:
                nut = [float(x) for x in nutrition]
            except ValueError:
                nut = [0.0] * 7

            row = {
                "recipe_id": str(food_id),
                "name": title,
                "tag_coarse": tag_coarse,
                "tag_fine": tag_fine,
                "tag_confidence": tag_confidence,
                "link": link,
                "source": source,
            }
            row.update({col: round(struct[col], 1) for col in _STRUCT_COLUMN_ORDER})
            row["n_significant"] = n_sig
            row["mass_significant_frac"] = round(sig_frac, 4)
            row["has_yeast"] = 1 if struct["yeast_g"] > 0 else 0
            row["has_chemical_leavener"] = 1 if struct["leavener_g"] > 0 else 0
            row["has_egg"] = 1 if struct["egg_g"] > 0 else 0
            row["has_fat"] = 1 if struct["fat_g"] > 0 else 0
            row["has_sugar"] = 1 if struct["sugar_g"] > 0 else 0
            row["calories"] = nut[0]
            row["nutrition_fat"] = nut[1]
            row["nutrition_sugar"] = nut[2]
            row["nutrition_sodium"] = nut[3]
            row["nutrition_protein"] = nut[4]
            row["nutrition_satfat"] = nut[5]
            row["nutrition_carbs"] = nut[6]
            row["tags_raw"] = str(meta["tags"])
            row["ingredients_raw"] = str(meta["ingredients"])
            rows.append(row)
            stats["kept"] += 1

    import pandas as pd

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    df.to_csv(out_path, index=False)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the tag-labeled baking dataset.")
    parser.add_argument(
        "--rnlg",
        default="data/raw/RecipeNLG/RecipeNLG_dataset.csv",
        help="Path to RecipeNLG_dataset.csv",
    )
    parser.add_argument(
        "--food",
        default="data/raw/food/RAW_recipes.csv",
        help="Path to Food.com RAW_recipes.csv",
    )
    parser.add_argument("--out", default="data/recipes_tagged.csv")
    parser.add_argument("--limit", type=int, default=None, help="Only read this many RecipeNLG rows")
    args = parser.parse_args()

    stats = build(args.rnlg, args.food, args.out, args.limit)
    print(f"RecipeNLG rows read:   {stats['total']}")
    print(f"food.com rows:         {stats['food_rows']}")
    print(f"joined to Food.com:    {stats['joined']}")
    print(f"excluded (not scratch):{stats['excluded']}")
    print(f"flourless dropped:     {stats['flourless']}")
    print(f"kept (labeled):        {stats['kept']}")
    print(f"non-baked sections:    {stats['nonbaked_components']} recipes had frosting/glaze dropped")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
