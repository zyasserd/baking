"""Assemble the single self-contained HTML report (``output/report.html``).

One page replaces the figure zoo: every panel is a Plotly figure with
plotly.js inlined once, so the file opens offline anywhere. Sections:

- header with the headline numbers (n, ARI + bootstrap CI + permutation p),
- log-ratio PCA scatter with book-archetype markers,
- the same view colored by cluster, plus the tag-vs-cluster confusion matrix,
- the simple-ratio panel: log(flour : liquid+egg) vs log(flour : fat+sugar) —
  kitchen ratios instead of PC scores, with translucent convex hulls per class,
- PC1 strip (the rich-vs-lean continuum per class),
- ternary simplex (flour : wet(liquid+egg) : rich(fat+sugar)) and the
  4-part tetrahedron,
- scree plot,
- diagnostics tables (class extremes, envelope outliers, k sweep, data
  quality, unresolved heads) — ingredient text included, so quantity ranges
  ("1 1/2 - 2 cups") read naturally in the cells.

Class colors come from one shared palette (``PALETTE``).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.spatial import ConvexHull

import config

PALETTE = {
    "cookie": "#d62728",
    "cake": "#1f77b4",
    "pie_pastry": "#ff7f0e",
    "bread": "#8c564b",
    "quick_bread": "#2ca02c",
    "brownies": "#9467bd",
    "batter": "#17becf",
    "dessert_other": "#7f7f7f",
}

_HEAD = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Baking ratios — analysis report</title>"
    "<style>body{font-family:sans-serif;margin:24px auto;max-width:1500px}"
    "h1{font-size:1.4em}h2{border-top:2px solid #ddd;padding-top:18px;"
    "margin-top:40px}.metrics{background:#f4f4f4;padding:12px 16px;"
    "border-radius:6px;font-size:1.05em}</style></head><body>"
)


def _ratio_readout(row: pd.Series) -> str:
    """The recipe's parts as simple ratios per 100 flour ("100 : 51 : 0 : 1 : 58")."""
    p = {part: float(row[f"{part}_p"]) for part in config.ANALYSIS_PARTS}
    base = p["flour"]
    if base <= 0:
        return "n/a"
    vals = [round(100.0 * p[part] / base) for part in config.ANALYSIS_PARTS]
    return " : ".join(str(v) for v in vals)


def _hover_texts(viz_df: pd.DataFrame, minimal: bool = False) -> np.ndarray:
    """Full hover on the main panels; minimal on the secondary views."""
    texts = []
    for _, r in viz_df.iterrows():
        if minimal:
            texts.append(f"<b>{r['name']}</b>")
        else:
            texts.append(
                f"<b>{r['name']}</b><br>class {r['tag_coarse']}"
                f"<br>flour:liquid:egg:fat:sugar = {_ratio_readout(r)}"
                f"<br>nearest archetype: {r['nearest_archetype']} "
                f"(d={r['aitchison_distance']:.3f})"
            )
    return np.asarray(texts, dtype=object)


def _class_groups(viz_df: pd.DataFrame) -> list[tuple[str, np.ndarray, str]]:
    return [(cls, (viz_df["tag_coarse"] == cls).to_numpy(), PALETTE[cls])
            for cls in config.CLASS_PRIORITY
            if (viz_df["tag_coarse"] == cls).any()]


def _cluster_groups(clusters: np.ndarray) -> list[tuple[str, np.ndarray, str]]:
    clusters = np.asarray(clusters)
    ids = sorted(set(int(c) for c in clusters))
    return [(f"cluster {cid}", clusters == cid, px.colors.qualitative.Plotly[i % 10])
            for i, cid in enumerate(ids)]


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _hull(x: np.ndarray, y: np.ndarray, color: str) -> go.Scatter | None:
    """Translucent convex hull of one class's points in a 2-D panel."""
    pts = np.column_stack([x, y])
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < 3:
        return None
    try:
        hull = ConvexHull(pts)
    except Exception:
        return None
    ring = list(hull.vertices) + [hull.vertices[0]]
    return go.Scatter(
        x=pts[ring, 0], y=pts[ring, 1], mode="lines", fill="toself",
        line={"width": 1.2, "color": color}, fillcolor=_hex_rgba(color, 0.15),
        opacity=0.6, hoverinfo="skip", showlegend=False,
    )


def _ratio_coords(viz_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Simple-ratio plane: log(flour : liquid+egg) vs log(flour : fat+sugar)."""
    flour = viz_df["flour_p"].to_numpy(dtype=float)
    wet = (viz_df["liquid_p"] + viz_df["egg_p"]).to_numpy(dtype=float)
    rich = (viz_df["fat_p"] + viz_df["sugar_p"]).to_numpy(dtype=float)
    eps = 0.005
    return np.log((flour + eps) / (wet + eps)), np.log((flour + eps) / (rich + eps))


def _panel2d(viz_df: pd.DataFrame, x: np.ndarray, y: np.ndarray, title: str,
             x_title: str, y_title: str, clusters: np.ndarray | None = None,
             hulls: bool = False, arch: np.ndarray | None = None,
             arch_names: list[str] | None = None,
             minimal_hover: bool = False) -> go.Figure:
    hover = _hover_texts(viz_df, minimal=minimal_hover)
    fig = go.Figure(layout=go.Layout(title=title, xaxis_title=x_title,
                                     yaxis_title=y_title, height=660))
    groups = (_cluster_groups(clusters) if clusters is not None
              else _class_groups(viz_df))
    if hulls and clusters is None:
        for _, mask, color in groups:
            h = _hull(x[mask], y[mask], color)
            if h is not None:
                fig.add_trace(h)
    for name, mask, color in groups:
        fig.add_trace(go.Scattergl(
            x=x[mask], y=y[mask], name=str(name), mode="markers",
            marker={"size": 4, "opacity": 0.45, "color": color},
            customdata=hover[mask],
            hovertemplate="%{customdata}<extra></extra>",
        ))
    if arch is not None and len(arch):
        fig.add_trace(go.Scatter(
            x=np.asarray(arch)[:, 0], y=np.asarray(arch)[:, 1], mode="markers+text",
            text=arch_names, textposition="top center", name="book archetypes",
            marker={"symbol": "star", "size": 11, "color": "black"},
            hovertemplate="%{text}<extra></extra>",
        ))
    return fig


def _fig_ternary(viz_df: pd.DataFrame) -> go.Figure:
    """Ternary simplex: flour : wet(liquid+egg) : rich(fat+sugar)."""
    a = viz_df["flour_p"].to_numpy(dtype=float)
    b = (viz_df["liquid_p"] + viz_df["egg_p"]).to_numpy(dtype=float)
    c = (viz_df["fat_p"] + viz_df["sugar_p"]).to_numpy(dtype=float)
    hover = _hover_texts(viz_df)
    hover = _hover_texts(viz_df, minimal=True)
    fig = go.Figure(layout=go.Layout(
        title="Ternary simplex — flour : wet(liquid+egg) : rich(fat+sugar)",
        ternary={
            "aaxis": {"title": "flour", "linewidth": 1},
            "baxis": {"title": "wet (liquid+egg)", "linewidth": 1},
            "caxis": {"title": "rich (fat+sugar)", "linewidth": 1},
        },
        height=660,
    ))
    for name, mask, color in _class_groups(viz_df):
        fig.add_trace(go.Scatterternary(
            a=a[mask], b=b[mask], c=c[mask], name=name, mode="markers",
            marker={"size": 4, "opacity": 0.45, "color": color},
            customdata=hover[mask],
            hovertemplate="%{customdata}<extra></extra>",
        ))
    names, pts = [], []
    for arch_name, vec in config.ARCHETYPES.items():
        flour, liquid, egg, fat, sugar = vec
        wet, rich = liquid + egg, fat + sugar
        total = flour + wet + rich
        pts.append((flour / total, wet / total, rich / total))
        names.append(arch_name)
    fig.add_trace(go.Scatterternary(
        a=[p[0] for p in pts], b=[p[1] for p in pts], c=[p[2] for p in pts],
        mode="markers+text", text=names, textposition="top center",
        name="book archetypes", marker={"symbol": "star", "size": 11, "color": "black"},
        hovertemplate="%{text}<extra></extra>",
    ))
    return fig


def _fig_tetra(tetra_coords: np.ndarray, viz_df: pd.DataFrame,
               arch_tetra: np.ndarray, arch_names: list[str]) -> go.Figure:
    """The 4-part tetrahedron (egg folded into liquid) in 3-D."""
    hover = _hover_texts(viz_df, minimal=True)
    fig = go.Figure(layout=go.Layout(
        title="4-part tetrahedron — flour / liquid+egg / fat / sugar", height=700,
        scene={"xaxis_title": "x", "yaxis_title": "y", "zaxis_title": "z",
               "aspectmode": "cube"},
    ))
    for name, mask, color in _class_groups(viz_df):
        fig.add_trace(go.Scatter3d(
            x=tetra_coords[mask, 0], y=tetra_coords[mask, 1], z=tetra_coords[mask, 2],
            name=name, mode="markers",
            marker={"size": 2.5, "opacity": 0.45, "color": color},
            customdata=hover[mask],
            hovertemplate="%{customdata}<extra></extra>",
        ))
    fig.add_trace(go.Scatter3d(
        x=arch_tetra[:, 0], y=arch_tetra[:, 1], z=arch_tetra[:, 2],
        mode="markers+text", text=arch_names, textposition="top center",
        name="book archetypes", marker={"symbol": "diamond", "size": 7, "color": "black"},
        hovertemplate="%{text}<extra></extra>",
    ))
    return fig


def _fig_pc1(viz_df: pd.DataFrame, pc1: np.ndarray) -> go.Figure:
    """Class distribution along PC1 (the rich-vs-lean continuum)."""
    df = pd.DataFrame({"tag_coarse": viz_df["tag_coarse"], "pc1": pc1})
    fig = px.violin(df, x="tag_coarse", y="pc1", color="tag_coarse",
                    color_discrete_map=PALETTE, box=True, points=False,
                    category_orders={"tag_coarse": [c for c in config.CLASS_PRIORITY
                                                    if c in set(df["tag_coarse"])]},
                    title="PC1 by tag class (rich > lean to the right)")
    fig.update_layout(showlegend=False, height=520)
    return fig


def _fig_confusion(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=table.to_numpy(), x=list(table.columns), y=list(table.index),
        colorscale="Blues", text=table.to_numpy(), texttemplate="%{text}",
        hovertemplate="true %{y} -> %{x}: %{z}<extra></extra>",
    ))
    fig.update_layout(title="Tag classes vs clusters (counts)", height=560)
    return fig


def _fig_scree(variance: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=variance["component"], y=variance["variance_fraction"],
        text=[f"{v:.1%}" for v in variance["variance_fraction"]],
        textposition="outside", marker_color="#1f77b4",
    ))
    fig.update_layout(title="Scree — variance per log-ratio component", height=420,
                      yaxis_tickformat=".0%")
    return fig


def _table_fig(df: pd.DataFrame, title: str, columns: list[str],
               max_rows: int | None = None) -> go.Figure:
    shown = df[columns]
    if max_rows is not None:
        shown = shown.head(max_rows)
    cells = []
    for col in columns:
        values = shown[col]
        if pd.api.types.is_float_dtype(values):
            values = values.map(lambda v: f"{v:.3f}" if pd.notna(v) else "")
        cells.append([str(v) for v in values])
    fig = go.Figure(go.Table(
        header=dict(values=columns, fill_color="#444",
                    font={"color": "white"}, align="left"),
        cells=dict(values=cells, align="left", height=22),
    ))
    fig.update_layout(title=title, height=min(900, 160 + 22 * max(len(shown), 4)))
    return fig


def write_html(
    outdir: str,
    viz_df: pd.DataFrame,
    viz_scores: np.ndarray,
    arch_scores: np.ndarray,
    arch_names: list[str],
    arch_tetra: np.ndarray,
    tetra_coords: np.ndarray,
    clusters: np.ndarray,
    confusion: pd.DataFrame,
    variance: pd.DataFrame,
    interpretations: list[str],
    metrics: dict,
) -> None:
    """Build every panel and write the single ``report.html``."""
    viz_scores = np.asarray(viz_scores)
    scores2 = viz_scores[:, :2]

    # Secondary density views carry fewer points: they are the same
    # distribution from another angle, and the hover payload dominates
    # the file size otherwise.
    rng = np.random.default_rng(config.RANDOM_SEED)
    n_sec = min(len(viz_df), 8000)
    sec_idx = np.sort(rng.choice(len(viz_df), size=n_sec, replace=False))
    sec_df = viz_df.iloc[sec_idx].reset_index(drop=True)

    ratio_x, ratio_y = _ratio_coords(viz_df)
    panels = [
        ("Log-ratio PCA — top 2 components",
         _panel2d(viz_df, scores2[:, 0], scores2[:, 1],
                  "Log-ratio PCA — top 2 components",
                  interpretations[0], interpretations[1],
                  arch=arch_scores[:, :2], arch_names=arch_names)),
        ("Same PCA view, colored by cluster (8k sample)",
         _panel2d(sec_df, scores2[sec_idx, 0], scores2[sec_idx, 1],
                  "PCA view colored by cluster",
                  interpretations[0], interpretations[1], clusters=clusters[sec_idx],
                  minimal_hover=True)),
        ("Simple ratios — flour : liquid vs flour : rich",
         _panel2d(viz_df, ratio_x, ratio_y,
                  "Simple ratios — log(flour:liquid) vs log(flour:rich)",
                  "log(flour : liquid+egg)", "log(flour : fat+sugar)", hulls=True)),
        ("PC1 by tag class", _fig_pc1(viz_df, viz_scores[:, 0])),
        ("Ternary simplex", _fig_ternary(sec_df)),
        ("4-part tetrahedron", _fig_tetra(tetra_coords[sec_idx], sec_df,
                                          arch_tetra, arch_names)),
        ("Variance", _fig_scree(variance)),
        ("Tag classes vs clusters", _fig_confusion(confusion)),
    ]

    def _csv(name: str) -> pd.DataFrame | None:
        path = os.path.join(outdir, name)
        return pd.read_csv(path) if os.path.exists(path) else None

    tables = []
    extremes = _csv("class_extremes.csv")
    if extremes is not None:
        tables.append((
            "Class extremes — top recipes far from their class centroid",
            _table_fig(extremes, "Class extremes", [
                "tag_coarse", "name", "aitchison_dist", "worst_part",
                "worst_part_p", "class_median_p", "worst_ratio",
                "unresolved_mass_frac", "mass_significant_frac", "url"])))
    outliers = _csv("outliers.csv")
    if outliers is not None:
        tables.append((
            "Envelope outliers — recipes dropped by the robust Mahalanobis gate",
            _table_fig(outliers, "Envelope outliers", [
                "tag_coarse", "name", "dist_to_center", "worst_part",
                "worst_part_p", "median_part_p", "n_raw_lines", "n_interim_rows",
                "unresolved_mass_frac", "url"])))
    sweep = _csv("k_sweep.csv")
    if sweep is not None:
        tables.append(("k sweep — silhouette and ARI per cluster count",
                       _table_fig(sweep, "k sweep", list(sweep.columns))))
    quality = _csv("data_quality.csv")
    if quality is not None:
        tables.append(("Data quality — mass share by conversion basis",
                       _table_fig(quality, "Data quality", list(quality.columns))))
    heads = _csv("unresolved_heads.csv")
    if heads is not None:
        tables.append((
            "Unresolved heads — heaviest ingredients the USDA reference could "
            "not resolve (the curation queue)",
            _table_fig(heads, "Unresolved heads", [
                "head", "total_g", "n_recipes", "sample_raw"], max_rows=20)))

    ari = metrics.get("ari")
    ci = metrics.get("ari_ci")
    p = metrics.get("ari_p_value")
    parts_head = [f"<h1>Baking-ratio analysis — {metrics['n']:,} scored recipes</h1>",
                  "<div class='metrics'>"]
    if ari is not None:
        parts_head.append(f"ARI vs tags: {ari:.3f}")
        if ci is not None:
            parts_head.append(f" (95% CI [{ci[0]:.3f}, {ci[1]:.3f}])")
        if p is not None:
            parts_head.append(f", permutation p = {p:.3f}")
        parts_head.append(" &middot; ")
    if metrics.get("silhouette") is not None:
        parts_head.append(f"silhouette {metrics['silhouette']:.3f} &middot; ")
    parts_head.append(f"PC1 order (lean &rarr; rich): "
                      f"{' < '.join(metrics['pc1_order'])}</div>")

    chunks = [_HEAD, "\n".join(parts_head)]
    for i, (title, fig) in enumerate(panels + tables):
        chunks.append(f"<h2>{title}</h2>")
        chunks.append(fig.to_html(
            full_html=False, include_plotlyjs=True if i == 0 else False,
            config={"displaylogo": False},
        ))
    chunks.append("</body></html>")

    path = os.path.join(outdir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(chunks))
    print(f"wrote {path} "
          f"({os.path.getsize(path) / 1e6:.1f} MB, plotly.js inlined)")
