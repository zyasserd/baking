"""Visualizations: biplot, 3D scatter, UMAP."""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import umap
from matplotlib import colors as mcolors

from .preprocess import CORE_COLUMNS
from .reduce import ingredient_label


def _family_colors(families: pd.Series):
    """Return (family -> int code) and a discrete color sequence."""
    codes, uniques = pd.factorize(families)
    return codes, uniques


def biplot(
    outdir: str,
    df: pd.DataFrame,
    Z: np.ndarray,
    W: np.ndarray,
) -> None:
    """2D scatter of PC1 vs PC2 colored by family, with loading arrows."""
    labels = [ingredient_label(c) for c in CORE_COLUMNS]
    codes, uniques = _family_colors(df["family"])

    fig, ax = plt.subplots(figsize=(11, 9))
    base_cmap = matplotlib.colormaps["tab20"]
    color_list = base_cmap(np.linspace(0, 1, len(uniques)))
    cmap = mcolors.ListedColormap(color_list)
    sc = ax.scatter(Z[:, 0], Z[:, 1], c=codes, cmap=cmap, s=32, alpha=0.85)

    # Loading arrows scaled to data extent.
    max_abs = np.max(np.abs(Z[:, :2]))
    scale = max_abs / np.max(np.abs(W[:, :2]))
    for j, label in enumerate(labels):
        ax.annotate(
            "",
            xy=(W[0, j] * scale, W[1, j] * scale),
            xytext=(0, 0),
            arrowprops=dict(arrowstyle="->", color="black", lw=1.2),
        )
        ax.text(W[0, j] * scale * 1.08, W[1, j] * scale * 1.08, label, fontsize=9)

    ax.axhline(0, color="grey", lw=0.6)
    ax.axvline(0, color="grey", lw=0.6)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_title("CLR-PCA biplot (ingredient loading arrows)")

    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="", color=color_list[i], label=u)
        for i, u in enumerate(uniques)
    ]
    ax.legend(handles=handles, title="family", bbox_to_anchor=(1.02, 1), loc="upper left")

    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "biplot.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def scatter_3d(outdir: str, df: pd.DataFrame, Z: np.ndarray) -> None:
    """Plotly 3D scatter of PC1/PC2/PC3; hover shows name + raw grams."""
    plot_df = df.copy()
    for k in range(Z.shape[1]):
        plot_df[f"PC{k + 1}"] = Z[:, k]

    hover_cols = CORE_COLUMNS
    fig = px.scatter_3d(
        plot_df,
        x="PC1",
        y="PC2",
        z="PC3",
        color="family",
        hover_name="name",
        hover_data=hover_cols,
        title="CLR-PCA 3D scatter",
    )
    fig.write_html(os.path.join(outdir, "scatter_3d.html"))


def umap_2d(outdir: str, Y: np.ndarray, df: pd.DataFrame) -> None:
    """UMAP on full CLR coordinates; axes intentionally unlabeled."""
    reducer = umap.UMAP(n_components=2, random_state=0)
    embedding = reducer.fit_transform(Y)

    plot_df = df[["name", "family"]].copy()
    plot_df["UMAP1"] = embedding[:, 0]
    plot_df["UMAP2"] = embedding[:, 1]

    fig = px.scatter(
        plot_df,
        x="UMAP1",
        y="UMAP2",
        color="family",
        hover_name="name",
        title="UMAP on CLR coordinates (layout only)",
    )
    fig.update_xaxes(showticklabels=False, title_text="")
    fig.update_yaxes(showticklabels=False, title_text="")
    fig.write_html(os.path.join(outdir, "umap_2d.html"))
