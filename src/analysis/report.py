"""Assemble the single self-contained HTML report (``output/report.html``).

One page, plotly.js inlined once, opens offline anywhere. Sections:

- header with the headline numbers (n, tag-class separation, axis orderings),
- the richness violin per tag class — the hand-picked manual axis
  (fat + sugar share), sorted by the distribution's mode (where the class
  bulges, not the skewed mean),
- ternary simplex (flour : wet(liquid+egg) : rich(fat+sugar)) and the
  4-part tetrahedron in tag-class colors. The renderer would otherwise hide
  points behind points, so the markers are small and strongly translucent:
  overlapping recipes alpha-blend, and dense regions read as saturated mixes.
  The tetrahedron is drawn as a plain wireframe with vertex labels — no
  cartesian axes. Every geometry panel also marks each class centroid
  (the closed geometric mean of the class's compositions).

Class colors come from one shared palette (``PALETTE``). The ternary is the
2-D ratio geometry in barycentric coordinates (a dedicated log-ratio scatter
would re-draw the same triangle — it lives only as the hover readout).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import gaussian_kde

import config

from . import coda, folds

PALETTE = {
    "cookie": "#e15759",
    "cake": "#4e79a7",
    "pie_pastry": "#f28e2b",
    "bread": "#9c755f",
    "quick_bread": "#59a14f",
    "brownies": "#b07aa1",
    "batter": "#76b7b2",
    "dessert_other": "#bab0ac",
}

# Simplex panels draw one translucent trace per class: overlapping points
# alpha-blend, so density reads as saturation instead of occlusion.
_ALPHA, _ALPHA3D = 0.25, 0.3

_TETRA_LABELS = ["flour", "liquid+egg", "fat", "sugar"]

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


def _hover_texts(viz_df: pd.DataFrame, minimal: bool = False,
                 readout: bool = False) -> np.ndarray:
    """Full hover carries the nearest archetype; `readout` adds the ratios."""
    texts = []
    for _, r in viz_df.iterrows():
        if minimal:
            texts.append(f"<b>{r['name']}</b> — {r['tag_coarse']}")
        elif readout:
            texts.append(
                f"<b>{r['name']}</b> — {r['tag_coarse']}"
                f"<br>flour:liquid:egg:fat:sugar = {_ratio_readout(r)}")
        else:
            texts.append(
                f"<b>{r['name']}</b><br>class {r['tag_coarse']}"
                f"<br>flour:liquid:egg:fat:sugar = {_ratio_readout(r)}"
                f"<br>nearest archetype: {r['nearest_archetype']} "
                f"(d={r['aitchison_distance']:.3f})"
            )
    return np.asarray(texts, dtype=object)


def mode_estimate(values: np.ndarray) -> float:
    """The peak of the distribution's KDE — where the class bulges the most.

    The richness distributions are skewed, so their mean sits in the tail; the
    KDE mode is the honest "typical value" for sorting the violins.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return float("nan")
    if len(np.unique(values)) < 2:
        return float(values[0])
    grid = np.linspace(values.min(), values.max(), 512)
    return float(grid[np.argmax(gaussian_kde(values)(grid))])


def _class_groups(viz_df: pd.DataFrame) -> list[tuple[str, np.ndarray, str]]:
    return [(cls, (viz_df["tag_coarse"] == cls).to_numpy(), PALETTE[cls])
            for cls in config.CLASS_PRIORITY
            if (viz_df["tag_coarse"] == cls).any()]


def _class_centroids(viz_df: pd.DataFrame, ilr: np.ndarray) -> dict[str, np.ndarray]:
    """Per-class centroid: mean ILR balance mapped back to simplex shares.

    The mean is taken in the analysis space (ILR, where the outlier gate and
    extremes are computed); ``coda.ilr_inverse`` transforms it back exactly.
    A geometric mean of the raw shares is wrong here: with structural zeros
    the epsilon needed to take logs dominates parts that are often absent.
    """
    out = {}
    for cls in config.CLASS_PRIORITY:
        mask = (viz_df["tag_coarse"] == cls).to_numpy()
        if not mask.any():
            continue
        out[cls] = coda.ilr_inverse(ilr[mask].mean(axis=0)[None, :])[0]
    return out


def _centroid_trace(coords: dict[str, np.ndarray], to_xy, symbol: str,
                    name: str) -> go.Scatter:
    """Markers + labels for the class centroids, mapped by ``to_xy(share_vec)``."""
    xs, ys, texts, colors = [], [], [], []
    for cls, g in coords.items():
        x, y = to_xy(g)
        xs.append(x)
        ys.append(y)
        texts.append(cls)
        colors.append(PALETTE[cls])
    return go.Scatter(
        x=xs, y=ys, mode="markers+text", text=texts, textposition="top center",
        name=name, marker={"symbol": symbol, "size": 13, "color": colors},
        cliponaxis=False,
        hovertemplate="%{text} centroid<extra></extra>",
    )


def _ratio_coords_vec(g: np.ndarray) -> tuple[float, float]:
    """Simple-ratio coordinates (flour-first) of one share vector."""
    idx = {p: i for i, p in enumerate(config.ANALYSIS_PARTS)}
    flour, wet = g[idx["flour"]], g[idx["liquid"]] + g[idx["egg"]]
    rich = g[idx["fat"]] + g[idx["sugar"]]
    eps = 0.005
    return (np.log((flour + eps) / (wet + eps)), np.log((flour + eps) / (rich + eps)))


def _fig_violin(viz_df: pd.DataFrame, values: pd.Series, title: str) -> go.Figure:
    """Class distribution along one manual axis, sorted by class median."""
    df = pd.DataFrame({"tag_coarse": viz_df["tag_coarse"], "value": values})
    order = (df.groupby("tag_coarse")["value"].median()
             .sort_values().index.tolist())
    fig = px.violin(df, x="tag_coarse", y="value", color="tag_coarse",
                    color_discrete_map=PALETTE, box=True, points=False,
                    category_orders={"tag_coarse": order}, title=title)
    fig.update_layout(showlegend=False, height=520)
    return fig


def _fig_ternary(viz_df: pd.DataFrame, cents: dict[str, np.ndarray]) -> go.Figure:
    """Ternary simplex in class colors; translucent markers alpha-blend."""
    a = viz_df["flour_p"].to_numpy(dtype=float)
    b = (viz_df["liquid_p"] + viz_df["egg_p"]).to_numpy(dtype=float)
    c = (viz_df["fat_p"] + viz_df["sugar_p"]).to_numpy(dtype=float)
    hover = _hover_texts(viz_df, readout=True)
    fig = go.Figure(layout=go.Layout(
        title="Ternary simplex — flour : wet(liquid+egg) : rich(fat+sugar)<br>"
              "<sup>translucent markers alpha-blend: dense regions read as "
              "saturated color mixes, not a front layer</sup>",
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
            marker={"size": 4, "opacity": _ALPHA, "color": color},
            customdata=hover[mask],
            hovertemplate="%{customdata}<extra></extra>",
        ))

    def to_ternary(g: np.ndarray) -> tuple[float, float, float]:
        idx = {p: i for i, p in enumerate(config.ANALYSIS_PARTS)}
        wet = g[idx["liquid"]] + g[idx["egg"]]
        rich = g[idx["fat"]] + g[idx["sugar"]]
        return g[idx["flour"]], wet, rich

    fig.add_trace(go.Scatterternary(
        a=[to_ternary(g)[0] for g in cents.values()],
        b=[to_ternary(g)[1] for g in cents.values()],
        c=[to_ternary(g)[2] for g in cents.values()],
        mode="markers+text", text=list(cents.keys()), textposition="top center",
        name="class centroid", marker={"symbol": "cross", "size": 13,
                                       "color": [PALETTE[c] for c in cents]},
        hovertemplate="%{text} centroid<extra></extra>",
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
        cliponaxis=False,
        hovertemplate="%{text}<extra></extra>",
    ))
    return fig


def _fig_tetra(tetra_coords: np.ndarray, viz_df: pd.DataFrame,
               cents: dict[str, np.ndarray],
               arch_tetra: np.ndarray, arch_names: list[str]) -> go.Figure:
    """The 4-part tetrahedron as a plain wireframe — no cartesian axes."""
    hover = _hover_texts(viz_df, minimal=True)
    fig = go.Figure(layout=go.Layout(
        title="4-part tetrahedron — flour / liquid+egg / fat / sugar<br>"
              "<sup>translucent markers alpha-blend; depth splits fat from "
              "sugar</sup>",
        height=700,
        scene={
            "xaxis": {"visible": False}, "yaxis": {"visible": False},
            "zaxis": {"visible": False}, "aspectmode": "cube",
        },
    ))
    for name, mask, color in _class_groups(viz_df):
        fig.add_trace(go.Scatter3d(
            x=tetra_coords[mask, 0], y=tetra_coords[mask, 1], z=tetra_coords[mask, 2],
            name=name, mode="markers",
            marker={"size": 2.5, "opacity": _ALPHA3D, "color": color},
            customdata=hover[mask],
            hovertemplate="%{customdata}<extra></extra>",
        ))
    # Tetrahedron wireframe: the four corners joined by six edges.
    V = folds.tetrahedron_vertices()
    for i, j in [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]:
        fig.add_trace(go.Scatter3d(
            x=[V[i, 0], V[j, 0]], y=[V[i, 1], V[j, 1]], z=[V[i, 2], V[j, 2]],
            mode="lines", line={"color": "#888", "width": 3},
            hoverinfo="skip", showlegend=False,
        ))

    def to_tetra(g: np.ndarray) -> tuple[float, float, float]:
        idx = {p: i for i, p in enumerate(config.ANALYSIS_PARTS)}
        return (g[idx["flour"]], g[idx["liquid"]] + g[idx["egg"]],
                g[idx["fat"]], g[idx["sugar"]])

    cent_xyz = folds.barycentric_3d(np.array([to_tetra(g) for g in cents.values()]))
    fig.add_trace(go.Scatter3d(
        x=cent_xyz[:, 0], y=cent_xyz[:, 1], z=cent_xyz[:, 2],
        mode="markers+text", text=list(cents.keys()), textposition="top center",
        name="class centroid", marker={"symbol": "cross", "size": 9,
                                       "color": [PALETTE[c] for c in cents]},
        hovertemplate="%{text} centroid<extra></extra>",
    ))
    fig.add_trace(go.Scatter3d(
        x=V[:, 0], y=V[:, 1], z=V[:, 2],
        mode="markers+text", text=_TETRA_LABELS, textposition="top center",
        name="parts", marker={"size": 5, "color": "#444"},
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter3d(
        x=arch_tetra[:, 0], y=arch_tetra[:, 1], z=arch_tetra[:, 2],
        mode="markers+text", text=arch_names, textposition="top center",
        name="book archetypes", marker={"symbol": "diamond", "size": 7, "color": "black"},
        hovertemplate="%{text}<extra></extra>",
    ))
    return fig


def write_html(
    outdir: str,
    viz_df: pd.DataFrame,
    viz_ilr: np.ndarray,
    arch_names: list[str],
    arch_tetra: np.ndarray,
    tetra_coords: np.ndarray,
    metrics: dict,
) -> None:
    """Build every panel and write the single ``report.html``."""
    # Secondary density views carry fewer points: they are the same
    # distribution from another angle, and the hover payload dominates
    # the file size otherwise.
    rng = np.random.default_rng(config.RANDOM_SEED)
    n_sec = min(len(viz_df), 8000)
    sec_idx = np.sort(rng.choice(len(viz_df), size=n_sec, replace=False))
    sec_df = viz_df.iloc[sec_idx].reset_index(drop=True)

    cents = _class_centroids(viz_df, viz_ilr)
    panels = [
        ("Richness by tag class",
         _fig_violin(viz_df, (viz_df["fat_p"] + viz_df["sugar_p"]) * 100.0,
                     "Richness (fat + sugar share, %) by tag class — sorted by mode")),
        ("Ternary simplex", _fig_ternary(sec_df, cents)),
        ("4-part tetrahedron", _fig_tetra(tetra_coords[sec_idx], sec_df, cents,
                                          arch_tetra, arch_names)),
    ]

    sep = metrics.get("separation")
    parts_head = [f"<h1>Baking-ratio analysis — {metrics['n']:,} scored recipes</h1>",
                  "<div class='metrics'>"]
    if sep is not None:
        parts_head.append(
            f"Tag-class separation (mean silhouette): {sep:.3f} — "
            "&asymp; 0: the classes bleed into each other; baking is a continuum"
            " &middot; ")
    parts_head.append(f"Richness order by mode (lean &rarr; rich): "
                      f"{' < '.join(metrics['richness_order'])}</div>")

    chunks = [_HEAD, "\n".join(parts_head)]
    for i, (title, fig) in enumerate(panels):
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