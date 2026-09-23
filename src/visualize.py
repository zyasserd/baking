"""Visualizations on the log-ratio (Aitchison) space.

``scree`` shows the variance carried by each log-ratio principal component;
``pca_biplot`` overlays part loadings and book archetypes on the recipe score
scatter; ``ternary`` draws the simplex in (flour, liquid, enrich) barycentric
coordinates; ``cluster_scatter`` colors the PCA projection by cluster;
``simplex_3d`` draws the 4-part tetrahedron (with the fat+sugar fold) and
``pca_3d`` the top-3 log-ratio components.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .composition import PARTS, TETRAHEDRON_PARTS, tetrahedron_vertices

# Click a recipe point to open its source link in a new tab. Fired from the
# ``customdata`` attached to every recipe trace below.
_CLICK_JS = """
var gd = document.getElementById('{plot_id}');
gd.on('plotly_click', function(data) {
    if (!data || !data.points || data.points.length === 0) return;
    var pt = data.points[0];
    if (pt.customdata && pt.customdata.length && pt.customdata[0]) {
        var url = String(pt.customdata[0]);
        if (url) window.open(url, '_blank');
    }
});
"""


def _recipe_urls(df: pd.DataFrame) -> np.ndarray:
    """Return a fully-formed URL per recipe (empty string if no link)."""
    if "link" not in df.columns:
        return np.array([""] * len(df), dtype=object)
    urls = []
    for v in df["link"].astype(object):
        if v is None:
            urls.append("")
            continue
        s = str(v).strip()
        if s == "" or s == "nan":
            urls.append("")
        elif s.startswith("http://") or s.startswith("https://"):
            urls.append(s)
        else:
            urls.append("https://" + s)
    return np.array(urls, dtype=object)


def _write_html(fig: go.Figure, path: str, url_cols: bool) -> None:
    """Write an HTML figure, adding the click-to-open-link handler if needed."""
    post_script = _CLICK_JS if url_cols else None
    fig.write_html(path, post_script=post_script)


def _discrete_colors(n: int) -> list:
    colors = []
    for name in ("tab20", "tab20b", "tab20c"):
        colors.extend(matplotlib.colormaps[name](np.linspace(0, 1, 20)))
    while len(colors) < n:
        colors.extend(colors)
    return [tuple(c) for c in colors[:n]]


def _family_codes(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list]:
    codes, uniques = pd.factorize(df["tag_coarse"])
    return codes, uniques, _discrete_colors(len(uniques))


def _scatter_families(ax, df, x, y, s=10, alpha=0.6):
    codes, uniques, color_list = _family_codes(df)
    ax.scatter(
        x, y, c=codes, cmap=matplotlib.colors.ListedColormap(color_list),
        s=s, alpha=alpha, linewidths=0,
    )
    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="", color=color_list[i], label=u)
        for i, u in enumerate(uniques)
    ]
    ax.legend(handles=handles, title="class", bbox_to_anchor=(1.02, 1), loc="upper left")


def scree(outdir: str, eigvals: np.ndarray) -> None:
    """Bar + cumulative-variance curve of the log-ratio components."""
    eigvals = np.asarray(eigvals, dtype=float)
    total = eigvals.sum() or 1.0
    frac = eigvals / total
    cum = np.cumsum(frac)
    x = np.arange(1, len(eigvals) + 1)

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.bar(x, frac, color="#4C72B0", alpha=0.8)
    ax1.set_xlabel("Log-ratio component")
    ax1.set_ylabel("Variance fraction", color="#4C72B0")
    ax1.set_xticks(x)
    ax1.tick_params(axis="y", labelcolor="#4C72B0")

    ax2 = ax1.twinx()
    ax2.plot(x, cum, marker="o", color="#DD8452")
    ax2.set_ylabel("Cumulative fraction", color="#DD8452")
    ax2.set_ylim(0, 1.05)
    ax2.tick_params(axis="y", labelcolor="#DD8452")

    ax1.set_title("Log-ratio PCA: variance explained")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "scree.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def pca_biplot(
    outdir: str,
    scores: np.ndarray,
    loadings: np.ndarray,
    df: pd.DataFrame,
    archetype_scores: np.ndarray | None = None,
    archetype_names: np.ndarray | None = None,
) -> None:
    """PC1 vs PC2 scatter with part loadings and (optionally) archetypes."""
    fig, ax = plt.subplots(figsize=(11, 9))
    _scatter_families(ax, df, scores[:, 0], scores[:, 1])

    # Loadings as arrows, scaled to the score spread.
    loadings = np.asarray(loadings, dtype=float)
    scale = max(np.abs(scores[:, :2]).max() / np.abs(loadings[:, :2]).max(), 1e-9)
    for i, part in enumerate(PARTS):
        ax.annotate(
            "",
            xy=(loadings[i, 0] * scale, loadings[i, 1] * scale),
            xytext=(0, 0),
            arrowprops=dict(arrowstyle="->", color="black", lw=1.2),
        )
        ax.annotate(
            part,
            xy=(loadings[i, 0] * scale * 1.12, loadings[i, 1] * scale * 1.12),
            fontsize=10, color="black", weight="bold",
        )

    if archetype_scores is not None and archetype_names is not None:
        ax.scatter(
            archetype_scores[:, 0], archetype_scores[:, 1],
            marker="*", s=320, c="black", edgecolors="white", linewidths=0.8,
            zorder=5,
        )
        for name, (px, py) in zip(archetype_names, archetype_scores[:, :2]):
            ax.annotate(name, (px, py), xytext=(6, 6), textcoords="offset points",
                        fontsize=9, weight="bold")

    ax.axhline(0, color="gray", lw=0.6, alpha=0.5)
    ax.axvline(0, color="gray", lw=0.6, alpha=0.5)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("Log-ratio PCA biplot (points = recipes, arrows = parts, stars = book archetypes)")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "pca_biplot.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def _ternary_xy(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map barycentric (a, b, c), each >= 0 summing to 1, onto 2-D."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    c = np.asarray(c, dtype=float)
    x = b + 0.5 * c
    y = (np.sqrt(3.0) / 2.0) * c
    return x, y


def ternary(outdir: str, df: pd.DataFrame) -> None:
    """Flour vs liquid vs (egg+fat+sugar) barycentric scatter.

    ``df`` must carry the ``flour_p``, ``liquid_p``, ``egg_p``, ``fat_p`` and
    ``sugar_p`` fraction columns from ``composition.compositions``.
    """
    flour = df["flour_p"].to_numpy()
    liquid = df["liquid_p"].to_numpy()
    enrich = df["egg_p"].to_numpy() + df["fat_p"].to_numpy() + df["sugar_p"].to_numpy()

    fig, ax = plt.subplots(figsize=(10, 9))
    x, y = _ternary_xy(flour, liquid, enrich)

    codes, uniques, color_list = _family_codes(df)
    ax.scatter(
        x, y, c=codes, cmap=matplotlib.colors.ListedColormap(color_list),
        s=12, alpha=0.6, linewidths=0,
    )

    # Triangle frame.
    tri_x, tri_y = _ternary_xy(
        np.array([1, 0, 0]), np.array([0, 1, 0]), np.array([0, 0, 1])
    )
    ax.fill(tri_x, tri_y, fill=False, edgecolor="black", lw=1.5)
    ax.plot([tri_x[0], tri_x[0]], [tri_y[0], tri_y[0]], "o", color="black")
    ax.annotate("flour", (tri_x[0], tri_y[0]), xytext=(0, -16), textcoords="offset points",
                ha="center", fontsize=11, weight="bold")
    ax.annotate("liquid", (tri_x[1], tri_y[1]), xytext=(0, -16), textcoords="offset points",
                ha="center", fontsize=11, weight="bold")
    ax.annotate("egg + fat + sugar", (tri_x[2], tri_y[2]), xytext=(0, 10),
                textcoords="offset points", ha="center", fontsize=11, weight="bold")

    ax.set_xlim(-0.08, 1.08)
    ax.set_ylim(-0.08, 0.95)
    ax.set_axis_off()
    ax.set_title("Recipes on the (flour, liquid, egg+fat+sugar) simplex")
    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="", color=color_list[i], label=u)
        for i, u in enumerate(uniques)
    ]
    ax.legend(handles=handles, title="class", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "ternary.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def cluster_scatter(
    outdir: str,
    coords: np.ndarray,
    df: pd.DataFrame,
    clusters: np.ndarray,
    xlabel: str = "dim 1",
    ylabel: str = "dim 2",
) -> None:
    """2-D scatter of the embedding, colored by cluster."""
    fig, ax = plt.subplots(figsize=(11, 9))
    clusters = np.asarray(clusters)
    n = int(clusters.max()) + 1 if len(clusters) else 0
    color_list = _discrete_colors(max(n, 1))
    for c in range(n):
        m = clusters == c
        ax.scatter(
            coords[m, 0], coords[m, 1], color=color_list[c % len(color_list)],
            s=12, alpha=0.6, linewidths=0, label=f"cluster {c}",
        )
    ax.axhline(0, color="gray", lw=0.6, alpha=0.5)
    ax.axvline(0, color="gray", lw=0.6, alpha=0.5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title("Embedding, colored by cluster")
    ax.legend(title="cluster", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "cluster_scatter.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def _tetrahedron_traces(vertices: np.ndarray) -> list[go.Scatter3d]:
    edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    traces = []
    for a, b in edges:
        traces.append(
            go.Scatter3d(
                x=[vertices[a, 0], vertices[b, 0]],
                y=[vertices[a, 1], vertices[b, 1]],
                z=[vertices[a, 2], vertices[b, 2]],
                mode="lines",
                line=dict(color="gray", width=2),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    return traces


def simplex_3d(
    outdir: str,
    coords: np.ndarray,
    df: pd.DataFrame,
    archetype_coords: np.ndarray,
    archetype_names: np.ndarray,
) -> None:
    """Interactive 3-D tetrahedron of the (flour, liquid, egg, fat+sugar) simplex.

    ``coords`` are the barycentric 3-D coordinates of the recipes; the four
    corners are flour, liquid, egg and fat+sugar (the "richness" fold). The ten
    book archetypes are drawn as labeled stars.
    """
    fig = go.Figure()

    urls = _recipe_urls(df)
    has_links = "link" in df.columns

    vertices = tetrahedron_vertices()
    for trace in _tetrahedron_traces(vertices):
        fig.add_trace(trace)

    for i, part in enumerate(TETRAHEDRON_PARTS):
        fig.add_trace(
            go.Scatter3d(
                x=[vertices[i, 0]],
                y=[vertices[i, 1]],
                z=[vertices[i, 2]],
                mode="text+markers",
                marker=dict(size=4, color="black"),
                text=[part],
                textposition="top center",
                textfont=dict(size=13),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    for fam in pd.unique(df["tag_coarse"]):
        m = df["tag_coarse"].to_numpy() == fam
        fig.add_trace(
            go.Scatter3d(
                x=coords[m, 0],
                y=coords[m, 1],
                z=coords[m, 2],
                mode="markers",
                name=str(fam),
                marker=dict(size=2.5, opacity=0.45),
                hovertext=df["name"].to_numpy()[m],
                customdata=urls[m, None],
                hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<extra></extra>",
            )
        )

    fig.add_trace(
        go.Scatter3d(
            x=archetype_coords[:, 0],
            y=archetype_coords[:, 1],
            z=archetype_coords[:, 2],
            mode="markers+text",
            name="archetype",
            marker=dict(size=10, symbol="diamond", color="black"),
            text=[str(n) for n in archetype_names],
            textfont=dict(size=11),
            textposition="top center",
        )
    )

    fig.update_layout(
        title="Baking simplex in 3-D: flour · liquid · egg · (fat + sugar)",
        scene=dict(
            xaxis=dict(showticklabels=False, title=""),
            yaxis=dict(showticklabels=False, title=""),
            zaxis=dict(showticklabels=False, title=""),
            aspectmode="cube",
        ),
        legend=dict(x=0.02, y=0.98),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    _write_html(fig, os.path.join(outdir, "simplex_3d.html"), has_links)


def embedding_2d(
    outdir: str,
    method: str,
    coords: np.ndarray,
    df: pd.DataFrame,
    archetype_coords: np.ndarray,
    archetype_names: np.ndarray,
    axis_labels: tuple[str, str] | None = None,
) -> None:
    """Interactive 2-D scatter of an embedding (PCA/UMAP/t-SNE), colored by class.

    ``axis_labels`` names the two axes when they are meaningful (PCA); UMAP/t-SNE
    axes are left unnamed because they are not interpretable.
    """
    fig = go.Figure()
    urls = _recipe_urls(df)
    has_links = "link" in df.columns

    for fam in pd.unique(df["tag_coarse"]):
        m = df["tag_coarse"].to_numpy() == fam
        fig.add_trace(
            go.Scatter(
                x=coords[m, 0],
                y=coords[m, 1],
                mode="markers",
                name=str(fam),
                marker=dict(size=4, opacity=0.5),
                hovertext=df["name"].to_numpy()[m],
                customdata=urls[m, None],
                hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<extra></extra>",
            )
        )

    if len(archetype_coords):
        fig.add_trace(
            go.Scatter(
                x=archetype_coords[:, 0],
                y=archetype_coords[:, 1],
                mode="markers+text",
                name="archetype",
                marker=dict(size=14, symbol="diamond", color="black"),
                text=[str(n) for n in archetype_names],
                textfont=dict(size=11),
                textposition="top center",
            )
        )

    xlabel = axis_labels[0] if axis_labels else ""
    ylabel = axis_labels[1] if axis_labels else ""
    fig.update_layout(
        title=f"{method.upper()} embedding (2-D), colored by class",
        xaxis=dict(showticklabels=False, title=xlabel),
        yaxis=dict(showticklabels=False, title=ylabel),
        legend=dict(x=0.02, y=0.98),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    _write_html(fig, os.path.join(outdir, f"{method}_2d.html"), has_links)


def embedding_3d(
    outdir: str,
    method: str,
    coords: np.ndarray,
    df: pd.DataFrame,
    archetype_coords: np.ndarray,
    archetype_names: np.ndarray,
) -> None:
    """Interactive 3-D scatter of an embedding (UMAP), colored by family."""
    fig = go.Figure()
    urls = _recipe_urls(df)
    has_links = "link" in df.columns

    for fam in pd.unique(df["tag_coarse"]):
        m = df["tag_coarse"].to_numpy() == fam
        fig.add_trace(
            go.Scatter3d(
                x=coords[m, 0],
                y=coords[m, 1],
                z=coords[m, 2],
                mode="markers",
                name=str(fam),
                marker=dict(size=2.5, opacity=0.45),
                hovertext=df["name"].to_numpy()[m],
                customdata=urls[m, None],
                hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<extra></extra>",
            )
        )

    if len(archetype_coords):
        fig.add_trace(
            go.Scatter3d(
                x=archetype_coords[:, 0],
                y=archetype_coords[:, 1],
                z=archetype_coords[:, 2],
                mode="markers+text",
                name="archetype",
                marker=dict(size=10, symbol="diamond", color="black"),
                text=[str(n) for n in archetype_names],
                textfont=dict(size=11),
                textposition="top center",
            )
        )

    fig.update_layout(
        title=f"{method.upper()} embedding (3-D), colored by class",
        scene=dict(
            xaxis=dict(showticklabels=False, title=""),
            yaxis=dict(showticklabels=False, title=""),
            zaxis=dict(showticklabels=False, title=""),
            aspectmode="cube",
        ),
        legend=dict(x=0.02, y=0.98),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    _write_html(fig, os.path.join(outdir, f"{method}_3d.html"), has_links)


def tag_confusion(outdir: str, table: pd.DataFrame) -> None:
    """Heatmap of the true-class x cluster count table."""
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(table.to_numpy(dtype=float), aspect="auto", cmap="viridis")
    ax.set_xticks(range(table.shape[1]))
    ax.set_xticklabels(table.columns, rotation=45, ha="right")
    ax.set_yticks(range(table.shape[0]))
    ax.set_yticklabels(table.index)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            ax.text(j, i, int(table.iat[i, j]), ha="center", va="center",
                    color="white" if table.iat[i, j] < table.to_numpy().max() * 0.6 else "black",
                    fontsize=8)
    ax.set_xlabel("ratio cluster")
    ax.set_ylabel("Food.com tag class")
    ax.set_title("Clusters vs Food.com tag classes")
    fig.colorbar(im, ax=ax, label="count")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "tag_confusion.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def class_pc1_strip(outdir: str, scores: np.ndarray, df: pd.DataFrame) -> None:
    """Per-class strip plot of PC1 (the rich-vs-lean axis).

    Discrete classes would separate cleanly; a baking *continuum* shows as
    heavily overlapping, ordered distributions.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    codes, uniques, color_list = _family_codes(df)
    x = scores[:, 0]
    for i, u in enumerate(uniques):
        m = codes == i
        y = np.full(m.sum(), i, dtype=float)
        jitter = (np.random.default_rng(0).uniform(-0.35, 0.35, m.sum()))
        ax.scatter(x[m], y + jitter, color=color_list[i], s=6, alpha=0.35, linewidths=0)
    ax.set_yticks(range(len(uniques)))
    ax.set_yticklabels([str(u) for u in uniques])
    ax.set_xlabel("PC1 (rich vs lean)")
    ax.set_title("Class distribution along PC1 — discrete islands vs continuum")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "tag_pc1.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
