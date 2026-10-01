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
  interim/                 derived stage-1 artifacts (gitignored):
                           fdc_srlegacy.csv, ingredients.csv
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

Describing the classes with each favors the add-in-excluding convention
(structural separation −0.005 vs −0.018 full at the time of the comparison,
reproducible via `DECOMPOSITION_MODE`), so **structural is what the pipeline
ships**. The full vector still exists internally (it picks each ingredient's
primary part for the density lookup); it never reaches the dataset.

## The Aid

`output/bakers_aid.html` is the project's product: one self-contained page
(no server, no build step, works offline) that lets you *interrogate* the
ratio space instead of looking at it.

- **One geometry, every partition.** Every recipe is five structural parts;
  a view is a partition of those parts into groups — two groups a 1D axis,
  three a triangle (flour at the top), four a tetrahedron. A **divider bar**
  above the plot shows the partition as `[rest] | flour | wet | rich`: drag a
  pill to another compartment (or click it, then the compartment), drag it onto
  the `+` box to give it its own compartment, click a divider `|` to merge two
  compartments, or a compartment's `+|` to peel one part off. Compartments carry numbered badges matching
  the plot corners. In 3D, two corners that line up on screen show their badges
  fused (the 4th vertex hidden behind its parent) and clicking that fused pair
  merges them. A split (2D→3D) turns the *regular* tetrahedron rigidly about the
  edge joining the two untouched corners: those two stay exactly on the 2D
  triangle, the split corner swings out, and the new apex lands on the same pixel
  as it (hidden) until you orbit to reveal it; 3D→2D reverses that turn back to
  the equilateral. A part pulled out of the `rest` box has no parent corner, so
  the view opens face-on instead.
  Within 3D, editing preserves the angle you orbited to; points tween between
  views.
  Book archetypes (★, Ruhlman's *Ratio*) are defined on the same five parts, so
  they project identically in every partition — reference stars everywhere.
- **Search drives the geometry.** The search bar takes typed chips:
  ingredients (resolved to the same USDA heads stage 1 uses, plural-
  insensitive), classes (in their palette color), name keywords, and ratio
  ranges (`sugar 40-60%`, or merged targets like `rich`). Matches stay
  full-color; everything else whispers to 4% opacity — you see *where in the
  space* your search lives.
- **Families filter.** The class legend above the plot is a row of family
  chips (cookie, cake, ...). Click one to isolate it, click several to combine
  (OR); the selection is ANDed with the search query. The weak-tier
  `dessert_other` family is not shown at all.
- **The ratio card.** Click any point: the panel shows what the recipe page
  does not — the five parts per 100 flour in display order flour : fat :
  sugar : liquid : egg (`100 : 50 : 50 : 100 : 100`), the composition bar, the
  nearest book archetype with its Aitchison distance, and where the recipe
  sits inside its class (per-part percentiles). All of it is computed in the
  browser from raw shares; Python compiles data, the client owns geometry.
- **Provenance and science stay honest.** Stage-1 row accounting ships in
  the data (for a future About view); the separation finding (≈ 0, the
  continuum) remains the method's result, printed by stage 2 and documented
  below.

Internal diagnostics (CSV only, deliberately not in any user-facing page):
`class_extremes.csv` — per-class far-from-centroid recipes with inspection
evidence, the maintainer's loop for finding stage-1 bugs; `outliers.csv` —
the robust-Mahalanobis-dropped tail; `data_quality.csv` — mass share per
density conversion basis; `unresolved_heads.csv` — the standing curation
queue (see `src/method/quality.py`).

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