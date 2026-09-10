# Baking Ratio Analysis

Dimensionality reduction on the baking-ingredient simplex. Each recipe is
treated as a composition of 6 core ingredients (flour, sugar, fat, egg, milk,
water) that sum to 1, transformed through closure → zero replacement → CLR, then
reduced with PCA into 3 interpretable ratio axes.

## Input schema

`data/recipes.csv`, one row per recipe:

```csv
recipe_id,name,family,flour_g,sugar_g,fat_g,egg_g,milk_g,water_g,salt_g,leavener_g,yeast_g
```

- `recipe_id`: string, unique.
- `name`: string.
- `family`: one of `lean_bread, enriched_bread, laminated, choux, pound_cake,
  butter_cake, oil_cake, genoise, chiffon, angel_food, muffin, drop_cookie,
  shortbread, sugar_cookie, pie_dough, other`.
- `flour_g, sugar_g, fat_g, egg_g, milk_g, water_g`: core simplex ingredients.
- `salt_g, leavener_g, yeast_g`: side columns (labels/analysis only, excluded
  from the simplex).
- All numeric columns: grams, `>= 0`, no missing values.

Recipes with `flour_g == 0` are excluded from the pipeline and written to
`output/excluded_flourless.csv`.

## Pipeline

Let `X` be the n×6 matrix of core ingredient grams.

1. **Closure** — `P[i,j] = X[i,j] / Σ_j X[i,j]`.
2. **Zero replacement** (multiplicative) — per row, `δ = 0.5 · min(positive
   values)`; each 0 becomes `δ`; row re-normalized to sum 1.
3. **CLR** — `Y[i,j] = ln(P[i,j]) − (1/D) Σ_k ln(P[i,k])`.
4. **PCA** — `PCA(n_components=3)` on `Y` (default centering).
5. **Axis naming** — for each PC, top-2 positive vs top-2 negative loadings:
   `PC{k} ≈ log[(pos1 · pos2) / (neg1 · neg2)]`.
6. **Clustering** (optional) — HDBSCAN on full CLR coordinates
   (Euclidean = Aitchison distance), ARI reported vs `family`.

## Setup (Nix flakes)

```sh
nix develop              # enter the dev shell (Python 3.12 + all deps)
```

The environment is pinned by `flake.lock` for reproducibility. `requirements.txt`
is a reference manifest only.

## Usage

```sh
nix develop -c python main.py --input data/recipes.csv --outdir output/
nix develop -c python main.py --input data/recipes.csv --outdir output/ --cluster
```

To regenerate the synthetic dataset:

```sh
nix develop -c python scripts/make_dataset.py --out data/recipes.csv
```

To run the tests:

```sh
nix develop -c pytest tests/
```

## Output files

| File | Contents |
|---|---|
| `output/excluded_flourless.csv` | recipes dropped for `flour_g == 0` |
| `output/coordinates.csv` | `recipe_id, name, family, PC1, PC2, PC3` |
| `output/loadings.csv` | ingredient × PC loading matrix |
| `output/variance.json` | explained-variance ratio per PC |
| `output/axis_names.txt` | 3 auto-generated ratio interpretations |
| `output/biplot.png` | PC1 vs PC2, colored by family, with loading arrows |
| `output/scatter_3d.html` | Plotly 3D scatter (hover: name + raw grams) |
| `output/umap_2d.html` | UMAP on CLR (layout only, axes unlabeled) |
| `output/clusters.csv` | `recipe_id, cluster_id` (if `--cluster`) |
| `output/cluster_report.txt` | ARI, cluster sizes, noise count |

## Reading the results

- `axis_names.txt` interprets each PC as a log-ratio between ingredient groups.
- `variance.json` ranks the axes by importance (values sum to total explained
  variance, printed to stdout on every run).
- The biplot loading arrows correspond to `loadings.csv`; families that separate
  along a given axis differ in that axis's ratio.
