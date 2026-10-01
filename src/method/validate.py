"""Internal diagnostics — evidence for inspecting suspect recipes, not results.

``class_extremes``: per tag class, the recipes farthest from the class centroid
(Aitchison distance in ILR space) — recipes that sit far from the center of
their group are usually processing errors (parse failures, unresolved
ingredients, bad density guesses), so each flagged recipe carries the evidence
needed to inspect it: its composition, worst-deviating part vs the class
median, raw-line vs parsed-row counts, and unresolved-mass share. This is the
maintainer's preprocessing loop: find why a recipe is far out, fix stage 1 if
required, re-run.

``write_envelope_outliers``: the recipes the robust Mahalanobis gate drops,
written with the same inspection evidence before they are removed.

Both write CSVs only (``class_extremes.csv``, ``outliers.csv``) — deliberately
NOT in the HTML report.
"""

from __future__ import annotations

import ast
import os

import numpy as np
import pandas as pd

import config


def _literal_list(value: str) -> list:
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    return parsed if isinstance(parsed, list) else []


def _interim_quality() -> pd.DataFrame:
    """Per recipe_id: parsed-row count and unresolved-mass share from interim."""
    path = config.INTERIM_INGREDIENTS_CSV
    if not os.path.exists(path):
        return pd.DataFrame(columns=["n_interim_rows", "unresolved_mass_frac"])
    ing = pd.read_csv(path, usecols=["recipe_id", "grams", "role"],
                      dtype={"recipe_id": str})
    grouped = ing.groupby("recipe_id")
    quality = pd.DataFrame({
        "n_interim_rows": grouped.size(),
        "unresolved_mass_frac": grouped.apply(
            lambda g: float(g.loc[g["role"] == "other", "grams"].sum() / g["grams"].sum())
            if g["grams"].sum() > 0 else 0.0,
            include_groups=False,
        ),
    })
    return quality


def class_extremes(df: pd.DataFrame, ilr: np.ndarray) -> pd.DataFrame:
    """Per class: the recipes farthest from the class centroid in ILR space.

    Distance is Euclidean in the ILR coordinates, i.e. Aitchison distance in
    the simplex. For each flagged recipe, ``worst_part`` is the part whose
    proportion deviates most from the class median (|log-ratio|, with a small
    pseudocount so structural zeros do not blow up) and ``worst_ratio`` is its
    odds vs the class median (>1 above, <1 below). Recipe-quality columns come
    from the stage-1 interim file: raw ingredient-line count vs parsed rows,
    and the share of parsed mass with an unresolved (``role="other"``) head.
    """
    ilr = np.asarray(ilr, dtype=float)
    part_cols = [f"{p}_p" for p in config.ANALYSIS_PARTS]
    P = df[part_cols].to_numpy(dtype=float)
    eps = config.EXTREMES_LOG_EPS

    quality = _interim_quality()

    rows = []
    for cls in config.CLASS_PRIORITY:
        mask = (df["tag_coarse"] == cls).to_numpy()
        if mask.sum() < 2:
            continue
        sub = df[mask].reset_index(drop=True)
        X = ilr[mask]
        Pm = P[mask]

        centroid = X.mean(axis=0)
        dist = np.linalg.norm(X - centroid, axis=1)
        median = np.median(Pm, axis=0)
        dev = np.abs(np.log((Pm + eps) / (median + eps)))
        worst = dev.argmax(axis=1)

        take = np.argsort(-dist)[: config.EXTREMES_PER_CLASS]
        for k in take:
            wp = config.ANALYSIS_PARTS[worst[k]]
            r = sub.iloc[k]
            n_raw = len(_literal_list(r["ingredients_raw"]))
            q = quality.loc[quality.index == str(r["recipe_id"])]
            rows.append({
                "tag_coarse": cls,
                "recipe_id": r["recipe_id"],
                "name": r["name"],
                "url": r["url"],
                "aitchison_dist": round(float(dist[k]), 4),
                **{pc: round(float(v), 4) for pc, v in zip(part_cols, Pm[k])},
                "worst_part": wp,
                "worst_part_p": round(float(Pm[k][worst[k]]), 4),
                "class_median_p": round(float(median[worst[k]]), 4),
                "worst_ratio": round(float((Pm[k][worst[k]] + eps) / (median[worst[k]] + eps)), 2),
                "n_raw_lines": n_raw,
                "n_interim_rows": int(q["n_interim_rows"].iloc[0]) if len(q) else None,
                "unresolved_mass_frac": (round(float(q["unresolved_mass_frac"].iloc[0]), 3)
                                         if len(q) else None),
                "mass_significant_frac": r["mass_significant_frac"],
                "n_significant": r["n_significant"],
            })
    return pd.DataFrame(rows)


def write_extremes(df: pd.DataFrame, ilr: np.ndarray, outdir: str) -> None:
    """Write ``class_extremes.csv`` and print a per-class worst-offender line."""
    extremes = class_extremes(df, ilr)
    extremes.to_csv(os.path.join(outdir, "class_extremes.csv"), index=False)
    print(f"Class extremes: {len(extremes)} far-from-centroid recipes "
          f"(top {config.EXTREMES_PER_CLASS} per class) -> class_extremes.csv")
    for cls in config.CLASS_PRIORITY:
        sub = extremes[extremes["tag_coarse"] == cls]
        if sub.empty:
            continue
        r = sub.iloc[0]
        print(f"  {cls:<13} worst: {r['name'][:50]!r} dist={r['aitchison_dist']} "
              f"({r['worst_part']} {r['worst_part_p']} vs median {r['class_median_p']})")


def write_envelope_outliers(df: pd.DataFrame, ilr: np.ndarray, inlier_mask: np.ndarray,
                            outdir: str) -> None:
    """Report the recipes the robust Mahalanobis gate drops (``outliers.csv``).

    ``detect_outliers`` silently removed these before; each dropped recipe is
    written with the same inspection evidence as the class extremes.
    """
    idx = np.flatnonzero(~np.asarray(inlier_mask))
    if len(idx) == 0:
        print("Envelope outliers: none dropped")
        return
    part_cols = [f"{p}_p" for p in config.ANALYSIS_PARTS]
    P = df[part_cols].to_numpy(dtype=float)
    eps = config.EXTREMES_LOG_EPS
    center = ilr[np.asarray(inlier_mask)].mean(axis=0)
    median = np.median(P[np.asarray(inlier_mask)], axis=0)
    quality = _interim_quality()

    rows = []
    for i in idx:
        dev = np.abs(np.log((P[i] + eps) / (median + eps)))
        wp = config.ANALYSIS_PARTS[int(dev.argmax())]
        r = df.iloc[i]
        q = quality.loc[quality.index == str(r["recipe_id"])]
        rows.append({
            "recipe_id": r["recipe_id"],
            "name": r["name"],
            "tag_coarse": r["tag_coarse"],
            "url": r["url"],
            "dist_to_center": round(float(np.linalg.norm(ilr[i] - center)), 4),
            **{pc: round(float(v), 4) for pc, v in zip(part_cols, P[i])},
            "worst_part": wp,
            "worst_part_p": round(float(P[i][dev.argmax()]), 4),
            "median_part_p": round(float(median[dev.argmax()]), 4),
            "n_raw_lines": len(_literal_list(r["ingredients_raw"])),
            "n_interim_rows": int(q["n_interim_rows"].iloc[0]) if len(q) else None,
            "unresolved_mass_frac": (round(float(q["unresolved_mass_frac"].iloc[0]), 3)
                                     if len(q) else None),
            "mass_significant_frac": r["mass_significant_frac"],
            "n_significant": r["n_significant"],
        })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(outdir, "outliers.csv"), index=False)
    print(f"Envelope outliers: {len(out)} recipes dropped by the robust "
          f"Mahalanobis gate -> outliers.csv")
