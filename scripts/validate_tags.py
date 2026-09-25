"""Validate the tag-derived labels against recipe titles (independent check).

For each class, reports how many of the dataset's titles contain a class-
defining keyword (the table lives in ``config.VALIDATION_TITLE_KEYWORDS``) and
prints random samples for eyeballing. This is a *diagnostic*, not a metric used
anywhere downstream.
"""

from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import config


def validate(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cls in config.CLASS_PRIORITY:
        sub = df[df["tag_coarse"] == cls]
        if len(sub) == 0:
            continue
        keywords = config.VALIDATION_TITLE_KEYWORDS.get(cls, ())
        hit = sub["name"].str.lower().apply(lambda t: any(k in t for k in keywords))
        rows.append(
            {
                "class": cls,
                "n": len(sub),
                "title_agreement": round(float(hit.mean()), 3) if len(sub) else None,
                "n_matching_title": int(hit.sum()),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spot-check tag labels against titles.")
    parser.add_argument("--input", default=config.PROCESSED_RECIPES_CSV, help="Preprocessed dataset path")
    parser.add_argument("--outdir", default=config.OUTPUT_DIR, help="Output directory")
    parser.add_argument("--samples", type=int, default=config.VALIDATION_SAMPLE_ROWS)
    args = parser.parse_args()

    df = pd.read_csv(args.input)

    report = validate(df)
    os.makedirs(args.outdir, exist_ok=True)
    report.to_csv(os.path.join(args.outdir, "tag_validation.csv"), index=False)

    lines = ["Tag validation: title agreement per class", ""]
    for _, row in report.iterrows():
        lines.append(f"  {row['class']:<13} n={row['n']:<6} title agreement={row['title_agreement']}")
    lines.append("")
    lines.append("Random samples per class for eyeballing:")
    rng = random.Random(config.RANDOM_SEED)
    for cls in config.CLASS_PRIORITY:
        sub = df[df["tag_coarse"] == cls]
        if len(sub) == 0:
            continue
        idx = rng.sample(range(len(sub)), min(args.samples, len(sub)))
        lines.append(f"\n[{cls}]")
        for i in idx:
            r = sub.iloc[i]
            lines.append(f"  - {r['name']}  (tag_fine={r['tag_fine']}, confidence={r['tag_confidence']})")

    text = "\n".join(lines) + "\n"
    with open(os.path.join(args.outdir, "tag_validation.txt"), "w") as fh:
        fh.write(text)
    print(text)

    samples = []
    for cls in config.CLASS_PRIORITY:
        sub = df[df["tag_coarse"] == cls]
        if len(sub) == 0:
            continue
        idx = rng.sample(range(len(sub)), min(args.samples, len(sub)))
        for i in idx:
            r = sub.iloc[i]
            samples.append({"class": cls, "name": r["name"], "tag_fine": r["tag_fine"],
                            "confidence": r["tag_confidence"]})
    pd.DataFrame(samples).to_csv(os.path.join(args.outdir, "tag_samples.csv"), index=False)
    print(f"wrote {args.outdir}/tag_validation.txt, tag_validation.csv, tag_samples.csv")


if __name__ == "__main__":
    main()