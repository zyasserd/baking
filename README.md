# Baking ratios — do the ratios predict the baked good?

Do the base ingredient ratios (flour, liquid, egg, fat, sugar) determine what
kind of baked good a recipe is, as Michael Ruhlman's *Ratio* claims? We test it
at scale: ~2.3 M recipes are turned into **compositional data** (each recipe a
point on the ingredient simplex) and their ratios are scored against the
**independent class labels** that Food.com attached to them.

- The *features* are the ratios (from USDA FoodData Central decomposition).
- The *labels* are Food.com tags (bread, cookie, cake, ...) — never the ratios.
- The book's ratios are used only as reference archetypes, never as labels.

**Result: yes, partially.** The classes order correctly along the rich-vs-lean
axis (PC1), and unsupervised clustering of the ratios beats chance against the
tags (ARI ≈ 0.18), but the classes bleed into each other (silhouette ≈ 0):
baking is a continuum, and the tags are fuzzy labels on it.

## Layout

```
flake.nix                  dev env + dataset fetchers (pinned sha256, commented)
config.py                  EVERY tunable parameter, in one commented file
scripts/                    thin entry points (argparse + report printing
                            only — all logic lives in src/)
  preprocess.py             STAGE 1: raw corpora -> preprocessed dataset
  analyze.py                STAGE 2: dataset -> all results (analysis +
                            validation diagnostics under output/)
src/
  preprocess/               stage-1 library
    pipeline.py             the stage-1 pipeline (join -> parts -> dataset)
    parse.py units.py       ingredient line -> qty/unit/head
    density.py             (qty, unit, ingredient) -> grams
    ingredients.py         head -> structural part weights (USDA)
    reference.py           USDA SR Legacy lookup + fuzzy matching
    fdc.py                 builds the compact USDA reference CSV
    filters.py             from-scratch / baked-goods exclusion
    tags.py                Food.com tags -> class taxonomy
    significance.py        which ingredients count toward the ratio
    parts.py               grams -> 5-part simplex proportions
  analysis/                 stage-2 library
    pipeline.py             the stage-2 analysis (CLR -> PCA -> clustering)
    coda.py                load dataset, closure/CLR/ILR transforms
    pca.py                 log-ratio PCA
    folds.py               book archetypes, tetrahedron fold
    cluster.py             outliers, k-means/GMM, ARI
    validate.py            diagnostics: labels vs titles, mass vs nutrition
    visualize.py           static + interactive figures
data/
  raw/                     raw corpora (gitignored): nix-staged store
                           symlinks + the manual Kaggle download
  interim/                 derived stage-1 artifacts (gitignored):
                           fdc_srlegacy.csv, ingredients.csv
  processed/recipes_simplex.csv   THE PREPROCESSED DATASET (committed)
output/                    stage-2 results (gitignored)
tests/                     pytest suite
```

The two stages are deliberately separate: stage 1 knows nothing about PCA or
clustering; stage 2 only reads the preprocessed dataset.

## Reproducibility

- **Environment**: `nix develop -c python ...` — a pinned Python 3.13 with
  numpy/pandas/scipy/scikit-learn/matplotlib/plotly. Nothing else is installed.
- **Raw data**: fetched — and, for the USDA archive, unpacked — by `flake.nix`
  with pinned sha256 hashes (the hash *is* the artifact's identity; see the
  commented DATASETS section in the flake). The dev shell stages each dataset
  as a store symlink at its `config.py` location:
  - *RecipeNLG* (Bien et al. 2020; ingredient text + source links) — fetched
    automatically on first shell entry from a byte-identical public mirror
    (the official distribution sits behind a registration form); linked at
    `data/raw/RecipeNLG/RecipeNLG_dataset.csv`.
  - *USDA FoodData Central SR Legacy (2018-04)* — fetched automatically; nix
    also unzips the archive and keeps only the three tables the pipeline
    reads (`.#fdc-tables`, linked at `data/raw/fdc`). The compact per-food
    CSV is derived from those by `src/preprocess/fdc.py`.
  - *Food.com* (shuyangli94 on Kaggle; tags + nutrition) — Kaggle requires
    login, so download `RAW_recipes.csv` manually from
    https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions
    into `data/raw/food/`. Its sha256 is pinned in `flake.nix` and validated
    by the dev shell on every entry (not by the pipeline), so a drifted file
    fails loudly.
- **Determinism**: stage 1 is verified byte-identical across runs. (Getting
  there required removing two set-iteration dependencies in the USDA fuzzy
  matcher, whose results had silently depended on Python's per-process hash
  seed.) The stage-1 output is committed (`data/processed/recipes_simplex.csv`)
  so the analysis stage is runnable without a 2.3 GB download.
- **Parameters**: everything tunable — taxonomy, decomposition rules, densities,
  thresholds, folds, seeds — lives in `config.py`, one commented file.

### Build the dataset

```bash
nix develop -c python scripts/preprocess.py     # ~4 min; writes data/processed/
```

### Run the analysis

```bash
nix develop -c python scripts/analyze.py        # writes output/ (results + diagnostics)
```

## What the pipeline computes

1. **Join**: RecipeNLG (text) is joined to Food.com (labels) on the numeric
   Food.com id at the end of the `link`. The two corpora are independent
   datasets; the join is the only point of contact.
2. **Labels**: Food.com tags resolve to a baked-good class (see `config.py`,
   TAG TAXONOMY). Title rescues exist for the under-tagged pastry and brownies
   classes; a `dessert_other` weak tier is kept but excluded from scoring.
3. **Exclusion**: recipes that are not from-scratch baked goods are dropped —
   mixes, prepared dough, purchased bread/crumbs, finished cookies/cakes used as
   ingredients, no-bake and topping-only titles (tables in `config.py`).
4. **Parsing**: each ingredient line becomes quantity + unit + head; quantities
   are converted to grams with name-aware densities (USDA container weights for
   cans/jars/packages; one large egg = 50 g; ...).
5. **Decomposition**: each ingredient head is mapped to a USDA SR Legacy food
   (curated table + fuzzy matcher) and its per-100 g proximates become part
   weights: water→water, lipid→fat, sugars→sugar, starch→flour (starchy
   categories only), sodium→salt. Pure parts are pinned to themselves (butter
   *is* fat, per the book). The per-ingredient database is written to
   `data/interim/ingredients.csv` — proportions sum to 1 per ingredient.
6. **Fold**: per recipe, the structural grams fold into five parts
   (flour / liquid / egg / fat / sugar; liquid = water + milk) and are closed
   to simplex coordinates that sum to 1. Non-baked sections (frosting, glaze,
   icing, ganache, coating) never pool into the ratio.

### Full vs structural

Two decomposition conventions were tested, and the choice is documented here
because it is the project's main methodological decision:

- **Full** — every ingredient's USDA composition is pooled into the parts,
  including add-ins (chocolate, nuts, fruit, cheese, ...). A chocolate-chip
  cookie's chocolate enters as sugar/fat.
- **Structural** — add-ins are *zeroed*: only structure-forming ingredients
  count (flours, sugars, fats, eggs, dairy, water, leaveners, salt, yeast),
  reproducing Ruhlman's clean ratio; the chocolate is flavor, not structure.

Clustering the tag classes with each gives ARI 0.176 (structural) vs ≈ 0.16
(full, at the last comparison) and better-separated archetypes — the
add-in-excluding decomposition wins, so **structural is what the pipeline
ships**. The full vector still exists internally (it picks each ingredient's
primary part for the density lookup); it never reaches the dataset.

## Reading the results

- `variance.csv` / `scree.png` — the simplex really is 4-D; PC1 (rich vs lean)
  dominates but is only half the variance.
- `loadings.csv` — PC1 = `+sugar +fat +egg vs −liquid −flour`, exactly the
  rich-vs-lean balance Ruhlman describes.
- `class_pc1_summary.csv` — the classes order correctly along PC1
  (`batter < bread < pie_pastry < quick_bread < cake < cookie < brownies`),
  confirming the ratio *does* encode the right gradient.
- `simplex_3d.html` — the 3D tetrahedron `flour / liquid+egg / fat / sugar`; the
  egg-into-liquid fold separates the tag classes best of all ten merges (see
  `config.TETRAHEDRON_PARTS` for the empirical comparison).
- Clustering runs in the **top-3 log-ratio PCs** (not 2): 3D beats 2D and PC4
  only adds noise.
- `tag_confusion.png` and `cluster_report.txt` — the classes bleed into each
  other (ARI ≈ 0.18, silhouette ≈ 0): baking is a continuum, and the Food.com
  tags are fuzzy labels on it, not crisp ratio clusters.
- `tag_validation.txt` — title-agreement spot check per class.
- `nutrition_validation.csv` — estimated structural grams vs Food.com nutrition
  (independent per-serving data) correlations, per class.

## Tests

```bash
nix develop -c python -m pytest -q
```

The suite covers the parser (fractions, RecipeNLG's mangled `1/4`→`14` ranges),
unit conversion, decomposition rules, the tag taxonomy, the compositional
transforms (closure/CLR/ILR geometry), and the deterministic-sign PCA.