# Baker's Aid — do the ratios predict the baked good?

Do the base ingredient ratios (flour, liquid, egg, fat, sugar) determine what
kind of baked good a recipe is, as Michael Ruhlman's *Ratio* claims? This
project tests it at scale: ~2.3 M recipes are turned into **compositional data**
(each recipe a point on the ingredient simplex) and their ratios are scored
against the **independent class labels** that Food.com attached to them. The
ratios are the features, the tags are the labels, and the two are never allowed
to peek at each other.

**Result: partially.** The tag classes are *described* in ratio space, not
predicted from it: their centroids sit in the right places (the classes order
correctly along a hand-picked richness axis, fat + sugar share), but their
separation is ≈ 0 (mean silhouette). Baking looks like a **continuum**, and the
Food.com tags are fuzzy labels painted on it. Nothing is clustered or
compressed — the geometry shown is the geometry that was computed.

The app's **About** page carries the method write-up (pipeline, data
provenance, the full-vs-structural decision, and the science). This README
covers the repository.

## Layout

```
flake.nix                  dev env + dataset fetchers (pinned sha256, commented)
config.py                  EVERY tunable parameter, in one commented file
scripts/                   thin entry points (argparse + report printing
                           only — all logic lives in src/)
  preprocess.py            STAGE 1: raw corpora -> preprocessed dataset
  analyze.py               STAGE 2: dataset -> the Aid + method diagnostics
src/
  dataset.py               the data contract: schema, validation, loader —
                           the only way either stage touches the dataset
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
  method/                  stage-2 science library
    pipeline.py            outlier gate + class description in ratio space
    coda.py                closure/CLR/ILR compositional transforms
    folds.py               book archetypes, tetrahedron fold
    outliers.py            robust Mahalanobis outlier gate
    validate.py            internal suspect-recipe diagnostics (CSV only)
    quality.py             data-quality report (density bases, unresolved heads)
  aid/                     the product builder: dataset -> data.js + packed HTML
web/                       the Aid's UI source (plain JS, no build step;
                           inlined into the packed HTML by stage 2)
tests/test_web.js          JS smoke tests, executed by qjs (QuickJS, staged
                           by flake.nix)
data/
  raw/                     raw corpora (gitignored): nix-staged store
                           symlinks + the manual Kaggle download
  interim/                 derived stage-1 artifacts (gitignored; the Aid
                           rebuilds without them): fdc_srlegacy.csv,
                           ingredients.csv (stage-2 diagnostics only)
  processed/               THE PREPROCESSED DATASET (committed)
    recipes_simplex.csv
    provenance.json
output/                    stage-2 results (gitignored)
tests/                     pytest suite
```

The two stages are deliberately separate: stage 1 knows nothing about the
method or the Aid; stage 2 only reads the preprocessed dataset through the
`src/dataset.py` contract.

## Reproducibility

- **Environment**: `nix develop -c python ...` — a pinned Python 3.13 with
  numpy/pandas/scipy/scikit-learn, plus ruff and QuickJS (`qjs`) for the
  Aid's JS smoke tests. Nothing else is installed.
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
  so the later stages are runnable without a 2.3 GB download.
- **Parameters**: everything tunable — taxonomy, decomposition rules, densities,
  thresholds, folds, seeds — lives in `config.py`, one commented file.

### Build the dataset

```bash
nix develop -c python scripts/preprocess.py     # ~4 min; writes data/processed/
```

### Build the Aid

```bash
nix develop -c python scripts/analyze.py        # writes output/ (Aid + diagnostics)
```

Open `output/bakers_aid.html` — it is self-contained and works offline over
file://. To hack on the UI, edit `web/` and reload the page directly: the
shell references `../output/aid/data.js` and the app files by relative path,
so the dev loop needs no build step and no server. Rerun stage 2 only when
the data changes.

### Build the website (Nix)

```bash
nix build .#website        # -> ./result/index.html (the self-contained Aid)
```

Runs stage 2 from the committed dataset and packs `web/` inside the Nix
sandbox — no raw corpora, no network. The output is byte-identical to the
local `scripts/analyze.py` run above. CI publishes it to GitHub Pages
(`.github/workflows/pages.yml`).

## Tests

```bash
nix develop -c python -m pytest -q
```

The suite covers the parser (fractions, RecipeNLG's mangled `1/4`→`14` ranges),
unit conversion, decomposition rules, the tag taxonomy, the dataset contract,
the Aid builder (data compilation + byte-deterministic packing), the
compositional transforms (closure/CLR/ILR geometry), the ILR isometry
(Aitchison distances preserved), and outlier-gate determinism. The Aid's
DOM-free JS (geometry, partitions, search, panel helpers) runs under qjs via
`tests/test_web.js`; the DOM code is syntax-checked there and exercised in
the browser.

Two consecutive stage-2 runs produce a byte-identical `bakers_aid.html` —
the product is as deterministic as the dataset.

## Caveats

**This is a vibe-coded project.** The code is largely AI-generated, written
with a language model over many sessions. It is carefully tested and
reproducible, but treat the interpretations as a hobbyist's, not a paper's.

**The preprocessing is approximate.** Ruhlman's five parts are a deliberate
simplification: ingredient lines are parsed heuristically, densities and USDA
decomposition are best-effort, the hardest ingredients are dropped, non-baked
sections are excluded, and the join to Food.com is imperfect. The geometry is
only as clean as that pipeline.

## Data

Three independent corpora meet at exactly one place: the numeric Food.com id
at the end of each RecipeNLG link.

- **RecipeNLG** (Bien et al. 2020) — raw ingredient text and source links.
- **Food.com** (shuyangli94 on Kaggle, 2019) — tags (the independent class
  labels) plus per-recipe nutrition.
- **USDA FoodData Central SR Legacy 2018-04** — per-100 g proximates that
  decompose each ingredient head into structural parts.

See the app's About page for the full provenance and the stage-1 flow.