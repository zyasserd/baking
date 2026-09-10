"""Generate a synthetic gram-level recipe dataset across all 16 families.

Realistic base gram values per family (per ~1 loaf/cake/batch), perturbed with
multiplicative noise. This is synthetic data for the current iteration; swap in
a real parsed CSV later (schema unchanged).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CORE = ["flour_g", "sugar_g", "fat_g", "egg_g", "milk_g", "water_g"]
SIDE = ["salt_g", "leavener_g", "yeast_g"]
ALL = CORE + SIDE

# Base gram values per family: dict family -> {column: value}
BASE = {
    "lean_bread": dict(flour_g=500, sugar_g=10, fat_g=10, egg_g=0, milk_g=0, water_g=330, salt_g=10, leavener_g=0, yeast_g=7),
    "enriched_bread": dict(flour_g=500, sugar_g=60, fat_g=50, egg_g=100, milk_g=250, water_g=50, salt_g=10, leavener_g=0, yeast_g=7),
    "laminated": dict(flour_g=500, sugar_g=40, fat_g=300, egg_g=0, milk_g=120, water_g=100, salt_g=10, leavener_g=0, yeast_g=12),
    "choux": dict(flour_g=125, sugar_g=10, fat_g=100, egg_g=200, milk_g=0, water_g=240, salt_g=5, leavener_g=0, yeast_g=0),
    "pound_cake": dict(flour_g=250, sugar_g=250, fat_g=250, egg_g=250, milk_g=0, water_g=0, salt_g=5, leavener_g=0, yeast_g=0),
    "butter_cake": dict(flour_g=250, sugar_g=300, fat_g=150, egg_g=120, milk_g=120, water_g=0, salt_g=5, leavener_g=10, yeast_g=0),
    "oil_cake": dict(flour_g=250, sugar_g=280, fat_g=120, egg_g=120, milk_g=120, water_g=0, salt_g=5, leavener_g=10, yeast_g=0),
    "genoise": dict(flour_g=120, sugar_g=150, fat_g=30, egg_g=250, milk_g=0, water_g=0, salt_g=3, leavener_g=0, yeast_g=0),
    "chiffon": dict(flour_g=130, sugar_g=160, fat_g=80, egg_g=200, milk_g=0, water_g=90, salt_g=3, leavener_g=8, yeast_g=0),
    "angel_food": dict(flour_g=100, sugar_g=200, fat_g=0, egg_g=360, milk_g=0, water_g=0, salt_g=3, leavener_g=0, yeast_g=0),
    "muffin": dict(flour_g=250, sugar_g=150, fat_g=100, egg_g=100, milk_g=240, water_g=0, salt_g=5, leavener_g=12, yeast_g=0),
    "drop_cookie": dict(flour_g=250, sugar_g=200, fat_g=170, egg_g=100, milk_g=0, water_g=0, salt_g=5, leavener_g=8, yeast_g=0),
    "shortbread": dict(flour_g=250, sugar_g=100, fat_g=200, egg_g=0, milk_g=0, water_g=0, salt_g=5, leavener_g=0, yeast_g=0),
    "sugar_cookie": dict(flour_g=250, sugar_g=200, fat_g=150, egg_g=60, milk_g=0, water_g=0, salt_g=5, leavener_g=6, yeast_g=0),
    "pie_dough": dict(flour_g=300, sugar_g=20, fat_g=220, egg_g=0, milk_g=0, water_g=60, salt_g=6, leavener_g=0, yeast_g=0),
    "other": dict(flour_g=250, sugar_g=120, fat_g=100, egg_g=80, milk_g=80, water_g=80, salt_g=5, leavener_g=6, yeast_g=3),
}

FAMILIES = list(BASE.keys())
NAME_PREFIX = {
    "lean_bread": "Country Loaf",
    "enriched_bread": "Brioche",
    "laminated": "Croissant",
    "choux": "Pâte à Choux",
    "pound_cake": "Pound Cake",
    "butter_cake": "Butter Cake",
    "oil_cake": "Oil Cake",
    "genoise": "Genoise",
    "chiffon": "Chiffon",
    "angel_food": "Angel Food Cake",
    "muffin": "Muffin",
    "drop_cookie": "Chocolate Chip Cookie",
    "shortbread": "Shortbread",
    "sugar_cookie": "Sugar Cookie",
    "pie_dough": "Pie Crust",
    "other": "Assorted Bake",
}


def _sample_family(rng: np.random.Generator, family: str, n: int) -> pd.DataFrame:
    base = BASE[family]
    rows = []
    for i in range(n):
        row = {}
        for col in ALL:
            val = base[col]
            if val == 0:
                # Occasionally introduce a small amount to exercise zero handling
                # without destroying the family's character.
                row[col] = 0.0 if rng.random() < 0.85 else round(float(rng.uniform(5, 20)), 1)
            else:
                noise = rng.lognormal(0.0, 0.15)
                row[col] = round(float(val * noise), 1)
        rows.append(row)

    df = pd.DataFrame(rows)
    # Guarantee flour > 0 (family-defining ingredient).
    df["flour_g"] = df["flour_g"].clip(lower=50.0)
    return df


def generate(n_per_family: int = 15, seed: int = 0, flourless: bool = True) -> pd.DataFrame:
    """Generate the synthetic dataset (optionally including a few flourless rows)."""
    rng = np.random.default_rng(seed)
    frames = []
    for family in FAMILIES:
        f = _sample_family(rng, family, n_per_family)
        f.insert(0, "family", family)
        frames.append(f)

    df = pd.concat(frames, ignore_index=True)

    # A couple of flourless recipes to exercise the exclusion path.
    if flourless:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [
                        dict(flour_g=0, sugar_g=200, fat_g=100, egg_g=150, milk_g=120, water_g=0,
                             salt_g=3, leavener_g=8, yeast_g=0),
                        dict(flour_g=0, sugar_g=150, fat_g=80, egg_g=100, milk_g=200, water_g=0,
                             salt_g=3, leavener_g=0, yeast_g=0),
                    ]
                ),
            ],
            ignore_index=True,
        )
        flourless_rows = df["flour_g"] == 0
        df.loc[flourless_rows, "family"] = "other"

    # Assign ids and names.
    df["name"] = [f"{NAME_PREFIX[f]} #{i + 1}" for i, f in enumerate(df["family"])]
    df.insert(0, "recipe_id", [f"R{i + 1:04d}" for i in range(len(df))])
    df.insert(1, "name", df.pop("name"))
    df.insert(2, "family", df.pop("family"))

    cols = ["recipe_id", "name", "family"] + ALL
    return df[cols]


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Generate synthetic recipe dataset.")
    parser.add_argument("--out", default="data/recipes.csv")
    parser.add_argument("--per-family", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    df = generate(n_per_family=args.per_family, seed=args.seed)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
