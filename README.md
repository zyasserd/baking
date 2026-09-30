# Baking ratios — do the ratios predict the baked good?

Do the base ingredient ratios (flour, liquid, egg, fat, sugar) determine what
kind of baked good a recipe is, as Michael Ruhlman's *Ratio* claims? We test it
at scale: ~2.3 M recipes are turned into **compositional data** (each recipe a
point on the ingredient simplex) and their ratios are scored against the
**independent class labels** that Food.com attached to them.

- The *features* are the ratios (from USDA FoodData Central decomposition).
- The *labels* are Food.com tags (bread, cookie, cake, ...) — never the ratios.
- The book's ratios are used only as reference archetypes, never as labels.

**Result: yes, partially.** The tag classes are *described* in ratio space,
not predicted from it: their centroids sit in the right places (the classes
order correctly along the hand-picked richness axis, fat + sugar share), but
their class separation is ≈ 0 (mean silhouette): baking is a continuum, and
the Food.com tags are fuzzy labels on it. No clustering, no statistical
components — the geometry shown is the geometry used.

## Layout

```
flake.nix                  dev env + dataset fetchers (pinned sha256, commented)
config.py                  EVERY tunable parameter, in one commented file
scripts/                   thin entry points (argparse + report printing
                           only — all logic lives in src/)
  preprocess.py            STAGE 1: raw corpora -> preprocessed dataset
  analyze.py               STAGE 2: dataset -> all results (analysis +
                           validation diagnostics under output/)
src/
  preprocess/              stage-1 library
    pipeline.py            the stage-1 pipeline (join -> parts -> dataset)
    parse.py units.py      ingredient line -> qty/unit/head
    density.py             (qty, unit, ingredient) -> grams
    ingredients.py         head -> structural part weights (USDA)
    reference.py           USDA SR Legacy lookup + fuzzy matching
    fdc.py                 builds the compact USDA reference CSV
    filters.py             from-scratch / baked-goods exclusion
    tags.py                Food.com tags -> class taxonomy
    significance.py        which ingredients count toward the ratio
    parts.py               grams -> 5-part simplex proportions
  analysis/                stage-2 library
    pipeline.py            the stage-2 analysis (class description in ratio space)
    coda.py                load dataset, closure/CLR/ILR transforms
    folds.py               book archetypes, tetrahedron fold
    outliers.py            robust Mahalanobis outlier gate
    validate.py            internal suspect-recipe diagnostics (CSV only)
    quality.py             data-quality report (density bases, unresolved heads)
    report.py              the single self-contained HTML report
data/
  raw/                     raw corpora (gitignored): nix-staged store
                           symlinks + the manual Kaggle download
  interim/                 derived stage-1 artifacts (gitignored):
                           fdc_srlegacy.csv, ingredients.csv
  processed/               THE PREPROCESSED DATASET (committed)
    recipes_simplex.csv
output/                    stage-2 results (gitignored)
tests/                     pytest suite
```

The two stages are deliberately separate: stage 1 knows nothing about
analysis; stage 2 only reads the preprocessed dataset.

## Reproducibility

- **Environment**: `nix develop -c python ...` — a pinned Python 3.13 with
  numpy/pandas/scipy/scikit-learn/plotly. Nothing else is installed.
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
  One documented exception: water-dominant add-ins (moist produce —
  applesauce, pumpkin, banana, zucchini, berries — acting as the recipe's
  hydration) contribute their USDA water fraction to the liquid part; their
  remaining parts stay zeroed.

Describing the classes with each gives class separation −0.007 (structural,
the shipped pipeline) vs −0.018 (full, reproducible via `DECOMPOSITION_MODE`)
— the add-in-excluding decomposition describes the classes better, so
**structural is what
the pipeline ships**. The full vector still exists internally (it picks each
ingredient's primary part for the density lookup); it never reaches the dataset.

## Reading the results

**`output/report.html` is the one artifact to open** — a single self-contained
page (plotly.js inlined, opens offline) with four panels and nothing else: the
simple-ratio plane (log wetness vs log richness — (liquid+egg):flour vs
(fat+sugar):flour, trimmed class hulls + centroids), the richness violin per class (fat + sugar share, a hand-picked
manual axis, sorted by the distribution's mode — where the class bulges), and
the ternary and tetrahedron simplexes in
tag-class colors — small, strongly translucent markers so overplotted points
alpha-blend instead of hiding each other; the tetrahedron is a plain
wireframe, no cartesian axes. Every geometry panel marks each class centroid
(closed geometric mean) and the book-archetype stars; hovering the ternary
shows a recipe's name, class and simple ratios
(`flour:liquid:egg:fat:sugar` per 100 flour).

Remaining outputs, for programmatic use:

- `compositions.csv` — one row per recipe: the 5-part proportions plus its
  nearest book archetype and Aitchison distance to it (and the recipe `url`).
- `class_richness_summary.csv` — per-class mean/std/mode of the richness
  axis (fat + sugar share); the classes order correctly along it (lean →
  rich), confirming the ratio *does* encode the right gradient.
- Internal diagnostics (CSV only, deliberately not in the report):
  `class_extremes.csv` — per-class far-from-centroid recipes with inspection
  evidence, the maintainer's loop for finding stage-1 bugs; `outliers.csv` —
  the robust-Mahalanobis-dropped tail; `data_quality.csv` — mass share per
  density conversion basis; `unresolved_heads.csv` — the standing curation
  queue (see `src/analysis/quality.py`).

## Tests

```bash
nix develop -c python -m pytest -q
```

The suite covers the parser (fractions, RecipeNLG's mangled `1/4`→`14` ranges),
unit conversion, decomposition rules, the tag taxonomy, the compositional
transforms (closure/CLR/ILR geometry), the ILR isometry (Aitchison distances
preserved), and outlier-gate determinism.