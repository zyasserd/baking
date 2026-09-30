"""Standing data-quality report — the curation queue, computed, not hand-built.

Stage 2 writes ``output/data_quality.csv`` (how each recipe mass estimate was
derived: the ``grams_basis`` fingerprint) and ``output/unresolved_heads.csv``
(the heaviest ingredient heads the USDA reference could not resolve, ranked by
mass). The unresolved queue is the actionable part: heads at the top of it are
exactly the curated entries or parser fixes worth adding next — the same loop
that this session's extremes investigation ran by hand.
"""

from __future__ import annotations

import os

import pandas as pd

import config


def unresolved_heads(interim: pd.DataFrame, top: int = 50) -> pd.DataFrame:
    """Heaviest unresolvable heads (``role="other"``), ranked by total grams."""
    rows = interim[interim["role"] == "other"]
    grouped = rows.groupby("head")
    table = grouped.agg(
        total_g=("grams", "sum"),
        n_rows=("grams", "size"),
        n_recipes=("recipe_id", "nunique"),
        sample_raw=("raw", "first"),
    ).sort_values("total_g", ascending=False)
    return table.head(top).reset_index()


def basis_share(interim: pd.DataFrame) -> pd.DataFrame:
    """Mass share per conversion basis (``volume:fallback`` is the exposure)."""
    total = interim["grams"].sum()
    grouped = interim.groupby("grams_basis")["grams"].agg(["sum", "size"])
    grouped.columns = ["total_g", "n_rows"]
    grouped["mass_share"] = (grouped["total_g"] / total).round(4)
    return grouped.sort_values("total_g", ascending=False).reset_index()


def write_reports(outdir: str) -> None:
    """Write ``unresolved_heads.csv`` and ``data_quality.csv``, print highlights."""
    path = config.INTERIM_INGREDIENTS_CSV
    if not os.path.exists(path):
        print(f"quality report skipped: {path} not found")
        return
    interim = pd.read_csv(path, dtype={"recipe_id": str}, low_memory=False)

    heads = unresolved_heads(interim)
    heads.to_csv(os.path.join(outdir, "unresolved_heads.csv"), index=False)

    share = basis_share(interim)
    share.to_csv(os.path.join(outdir, "data_quality.csv"), index=False)

    total_g = interim["grams"].sum()
    unresolved_g = interim.loc[interim["role"] == "other", "grams"].sum()
    fallback_g = interim.loc[interim["grams_basis"] == "volume:fallback", "grams"].sum()
    n_ranges = int(interim["qty_low"].notna().sum())
    purpose = "|".join(config.NONSTRUCTURAL_PHRASES)
    n_purpose = int(interim["raw"].str.lower().str.contains(purpose, na=False).sum())

    print(f"Data quality: {len(interim)} ingredient rows, {total_g / 1e6:.1f} t parsed mass")
    print(f"  unresolved (role=other): {unresolved_g / total_g:.1%} of mass, "
          f"{int((interim['role'] == 'other').sum())} rows")
    print(f"  fallback density (200 g/cup guess): {fallback_g / total_g:.1%} of mass")
    print(f"  range-quantified lines: {n_ranges}; non-structural purpose lines: {n_purpose}")
    print(f"  top unresolved head: {heads.iloc[0]['head']!r} "
          f"({heads.iloc[0]['total_g'] / 1e3:.0f} kg)" if len(heads) else "", end="\n")
