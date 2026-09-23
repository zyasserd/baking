"""Validate the tag-derived labels against independent signals.

This is the correctness gate for the classification: instead of trusting Food.com
tags, each class is cross-checked against three independent signals —

1. **Title keywords** — crude keyword match against the recipe title.
2. **Ingredient signal** — the presence of yeast / chemical leavener / egg /
   fat / sugar parsed from the actual ingredient list.
3. **Nutrition** — Food.com's per-serving nutrition (sugar/fat PDV) as an
   independent "richness" signature.

A class is only trustworthy when its tags agree with these signals. The report
prints, per class, the confidence mix, the title-keyword agreement rate, the
yeast/leavener/egg/fat/sugar presence rates, and mean nutrition. It also writes
random samples per class to ``output/tag_samples.csv`` for manual spot-checking.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from src import tags as tags_mod

# Crude title keywords per class, used only to sanity-check tag agreement.
TITLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bread": ("bread", "loaf", "roll", "bun", "sourdough", "bagel", "baguette",
              "focaccia", "ciabatta", "pretzel", "brioche", "challah", "dough",
              "yeast", "pizza", "toast", "kolach"),
    "quick_bread": ("bread", "muffin", "scone", "loaf", "banana", "zucchini",
                    "pumpkin", "cornbread", "biscuit", "quick"),
    "cake": ("cake", "cupcake", "cheesecake", "torte", "gateau", "frosting",
             "layer", "sponge", "bundt"),
    "cookie": ("cookie", "bar", "biscotti", "macaron", "macaroon",
               "shortbread", "snickerdoodle", "square"),
    "brownies": ("brownie", "blondie"),
    "pie_pastry": ("pie", "tart", "galette", "quiche", "cobbler", "crumble",
                   "crisp", "crust", "empanada", "croissant", "danish", "puff",
                   "choux", "eclair", "pastry", "turnover", "strudel"),
    "batter": ("pancake", "waffle", "crepe", "flapjack", "hotcake", "blintz"),
}


def _title_hits(names: pd.Series, keywords: tuple[str, ...]) -> np.ndarray:
    low = names.astype(str).str.lower()
    return low.str.contains("|".join(keywords), regex=True).to_numpy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tag-derived labels.")
    parser.add_argument("--input", default="data/recipes_tagged.csv")
    parser.add_argument("--outdir", default="output")
    parser.add_argument("--samples", type=int, default=8, help="Samples per class")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    df = pd.read_csv(args.input)

    lines: list[str] = []
    lines.append("Tag validation report")
    lines.append("=====================")
    lines.append(f"recipes: {len(df)}")
    lines.append("")

    summary_rows = []
    sample_rows = []

    for cls in tags_mod.CLASS_PRIORITY:
        sub = df[df["tag_coarse"] == cls]
        if sub.empty:
            continue
        conf = sub["tag_confidence"].value_counts().to_dict()
        names = sub["name"]

        kw = TITLE_KEYWORDS.get(cls, ())
        if kw:
            title_rate = _title_hits(names, kw).mean() if len(names) else 0.0
        else:
            title_rate = float("nan")

        yeast_rate = sub["has_yeast"].mean()
        lev_rate = sub["has_chemical_leavener"].mean()
        egg_rate = sub["has_egg"].mean()
        fat_rate = sub["has_fat"].mean()
        sugar_rate = sub["has_sugar"].mean()
        mean_sugar_pdv = sub["nutrition_sugar"].mean()
        mean_fat_pdv = sub["nutrition_fat"].mean()

        lines.append(
            f"{cls} (n={len(sub)}): "
            f"strong={conf.get('strong', 0)} medium={conf.get('medium', 0)} "
            f"weak={conf.get('weak', 0)}"
        )
        lines.append(
            f"    title-agreement={title_rate:.2f}  yeast={yeast_rate:.2f} "
            f"leavener={lev_rate:.2f} egg={egg_rate:.2f} fat={fat_rate:.2f} "
            f"sugar={sugar_rate:.2f}"
        )
        lines.append(
            f"    mean sugar-PDV={mean_sugar_pdv:.1f}  fat-PDV={mean_fat_pdv:.1f}"
        )

        summary_rows.append(
            {
                "class": cls,
                "n": len(sub),
                "title_agreement": round(title_rate, 3) if title_rate == title_rate else None,
                "has_yeast": round(yeast_rate, 3),
                "has_leavener": round(lev_rate, 3),
                "has_egg": round(egg_rate, 3),
                "has_fat": round(fat_rate, 3),
                "has_sugar": round(sugar_rate, 3),
                "mean_sugar_pdv": round(mean_sugar_pdv, 1),
                "mean_fat_pdv": round(mean_fat_pdv, 1),
            }
        )

        for _, row in sub.sample(min(args.samples, len(sub)), random_state=0).iterrows():
            sample_rows.append(
                {
                    "class": cls,
                    "fine": row["tag_fine"],
                    "confidence": row["tag_confidence"],
                    "name": row["name"],
                    "tags": row["tags_raw"],
                }
            )

    lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("- title-agreement is the share of recipes whose *title* still mentions")
    lines.append("  the class keyword; low values flag tags that disagree with names.")
    lines.append("- yeast should be high for 'bread', leavener high for 'quick_bread'")
    lines.append("  and (to a lesser degree) 'cake'/'cookie' (eggs leaven many cakes).")
    lines.append("- mean sugar-PDV orders the classes rich->lean; it should track the")
    lines.append("  ratio simplex (cake/cookie rich, bread lean).")

    report = "\n".join(lines) + "\n"
    with open(os.path.join(args.outdir, "tag_validation.txt"), "w") as fh:
        fh.write(report)

    pd.DataFrame(summary_rows).to_csv(
        os.path.join(args.outdir, "tag_validation.csv"), index=False
    )
    pd.DataFrame(sample_rows).to_csv(
        os.path.join(args.outdir, "tag_samples.csv"), index=False
    )

    print(report)
    print(f"wrote {args.outdir}/tag_validation.txt, tag_validation.csv, tag_samples.csv")


if __name__ == "__main__":
    main()
