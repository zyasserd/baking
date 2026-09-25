# Baking Ratio Analysis

Do ingredient **ratios** predict what a baked good *is*? Each recipe is a point
on the 5-part baking simplex — flour, liquid, egg, fat, sugar, normalized to
sum to 1 — the ratios Michael Ruhlman describes in *Ratio* (bread = 5 flour :
3 water, pie dough = 3 flour : 2 fat : 1 water, pound cake = 1:1:1:1).

The point of this project is to test a hypothesis, not to assume it: the
**features** are the ratios, and the **labels** are an *independent* source —
Food.com's user tags, joined from a separate corpus. The book ratios are used
only as reference archetypes, never as labels.

Every ingredient's mass is mapped to the parts through **USDA FoodData Central
(SR Legacy)**, so the weight vectors come from a real reference rather than
hand-tuned guesses (see *Composition vectors* below).

## Result (summary)

- The ratio simplex is genuinely 4-dimensional (PC1 ≈ 48% variance, PC2 21%,
  PC3 16%, PC4 15%) — baking is not a low-dimensional island structure.
- **PC1 is the "rich vs lean" axis** (`+sugar +fat +egg −liquid −flour`) and it
  orders the Food.com classes *exactly* as culinary intuition predicts:

  ```
  batter < bread < pie_pastry < quick_bread < cake < cookie < brownies
  ```

- But every class has a large spread, so the classes **overlap heavily**:
  clustering the ratios and scoring against the tags gives **ARI ≈ 0.21** and a
  near-zero silhouette. Baking is a **continuum**, not a set of discrete
  islands; the tags are fuzzy boundaries drawn on that continuum.
- **The best 3D simplex view folds egg into liquid.** Of the ten possible
  4-part sub-compositions (one merged pair), clustering the tag classes in
  `flour / liquid+egg / fat / sugar` separates them best (ARI ≈ 0.21 vs ≈ 0.17
  for every alternative) and keeps the book archetypes most distinct (min
  pairwise Aitchison distance 0.57). Egg alone is the *weakest* single part
  (class-separation F ≈ 590, vs ≈ 3100 for liquid and sugar) — its signal only
  appears when combined with liquid, which makes physical sense (an egg is ~75%
  water). Clustering in the top-3 log-ratio PCs beats 2D; PC4 is noise.
- **Add-ins are excluded (the book's convention, chosen empirically).** The
  build ships the *structural* decomposition — add-ins zeroed. The comparison
  that chose it: structural ARI 0.207 vs 0.176 for pooling add-ins into the
  ratio (3-D clustering). Pooling add-ins also inflates the cookie class's
  spread (their chocolate/fruit sugar+fat varies hugely). So Ruhlman's add-in
  exclusion holds up quantitatively.

## Data

Two corpora are joined on the numeric Food.com recipe id (found at the end of a
RecipeNLG `link`):

| Corpus | Provides | File |
|---|---|---|
| RecipeNLG | quantities + units → grams (the ratio features) | `data/raw/RecipeNLG/RecipeNLG_dataset.csv` |
| Food.com | independent tags + nutrition (the labels) | `data/raw/food/RAW_recipes.csv` |
| USDA SR Legacy | per-100 g composition (the reference) | `data/reference/fdc_srlegacy.csv` |

Only recipes that are (a) in both corpora, (b) classified into a baked-good
class, and (c) genuinely from scratch are kept. Prepared ingredients (dough,
mixes), no-bake items, and frosting/topping-only recipes are filtered out. The
USDA reference is fetched by `scripts/fetch_fdc.py`.

## Preprocessing: from ingredient line to parts

An ingredient line like `"1/2 cup firmly packed brown sugar"` is reduced to
grams of each structural part. Five stages:

**1. Parse to `<qty> <unit> <head> <props>`** (`src/parse.py`) — extract the
amount and canonical unit (`src/units.py`), then separate the canonical
ingredient *head* from preparation descriptors. `"1 cup firmly packed brown
sugar"` → `qty=1, unit=cup, head="brown sugar", props=[firmly, packed]`.
Compositional modifiers (`brown`, `powdered`, `whole wheat`, `unsweetened`,
`self-rising`, `skim`, `heavy`) stay with the head; prep verbs (chopped, minced,
grated, …) and stray unit words are stripped. Parenthetical size hints are kept
as a `note`.

**2. Convert to grams** (`src/density.py`) — the common currency:

| kind | rule |
|---|---|
| weight | `g`×1, `kg`×1000, `oz`×28.35, `lb`×453.59 |
| volume | `cup`×1, `tbsp`×1/16, `tsp`×1/48, `ml`, `l`, `pt`, `qt`, `gal`, then × *grams-per-cup* |
| count | egg = 50 g (yolk 17, white 33); butter stick = 113 g; yeast envelope = 7 g |
| container | `can`/`jar`/`pkg`/`container` → name-aware default net weight (a parameter), or a parenthetical size hint when present |

Volume needs a **density** (grams per cup), a per-part default refined *by
name* first (`brown sugar` 220, `powdered sugar` 120, `cream cheese` 232,
`honey` 340, `chocolate` 170, `raisins` 145, …).

**3. Mass significance** (`src/significance.py`) — an ingredient contributes to
the ratio only if its mass is **significant** (`share ≥ 2% AND ≥ 2 g` of the
recipe's total mass) **or** it is a functional ingredient that acts at tiny
mass (leavener, salt, yeast). Trace flavorings (vanilla, spices) fall below the
threshold and are ignored. The rule is a parameter.

**4. Decompose grams into parts** (`src/ingredients.decompose`) — each head
maps to a **weight vector** over `{flour, sugar, fat, egg, milk, water, salt,
leavener, yeast}` summing ≤ 1 (remainder is "other"); the ingredient's grams
are split by that vector.

**5. Close the simplex** (`src/composition.py`) — across the recipe, the five
part-masses (flour, liquid = milk + water, egg, fat, sugar) normalize to sum to
1 and are analyzed in log-ratio (CLR/ILR) coordinates.

### Composition vectors (the reference)

The vector in stage 4 comes from **USDA SR Legacy** (`src/reference.py`): a
recipe ingredient is matched to a USDA food description (a curated alias map for
the top ~500 heads + a fuzzy match for the tail), and its per-100 g proximate
composition is mapped to parts:

| nutrient | part |
|---|---|
| water | `water` |
| total lipid | `fat` |
| sugars | `sugar` |
| starch (carb − sugar − fiber) | `flour` — *only* for grain/legume/vegetable categories |
| sodium | `salt` (Na × 2.5 as NaCl) |
| protein, fiber, ash, other starch | ignored |

Pure parts are **pinned** to their own part at weight 1.0 (flour → flour, sugar
→ sugar, egg → egg, milk → milk, salt → salt, leavener → leavener, yeast →
yeast), and **butter → fat 1.0** per the book convention (its 16% water is
ignored so Ruhlman's ratios stay exact). Examples (USDA-derived):

```
cream cheese             -> fat 0.34 + water 0.53 + sugar 0.04
sweetened condensed milk -> sugar 0.54 + water 0.27 + fat 0.09
chocolate chips          -> sugar 0.55 + fat 0.30   (semisweet)
tomato soup              -> water 0.90 + sugar 0.03
rolled oats              -> flour 0.57 + fat 0.07   (add-in)
```

Ingredients are tagged **base** (structural) or **add-in** (chocolate, nuts,
fruit, vegetables, cheese, condiments, …). `decompose(name, mode)`:

- `mode="full"` — every significant ingredient contributes its vector;
- `mode="structural"` — add-ins are zeroed, leaving Ruhlman's clean ratio.

`scripts/build_dataset.py` ships the **structural** grams (`*_g` columns): the
add-in-excluding decomposition classifies measurably better (see *Result*), so
it is the pipeline's composition. The full vector is still used internally to
pick each ingredient's primary part for the density lookup.

The nutrient→part mapping and the curated alias map are parameters.

### Worked example — comparing units

```
"1/2 cup flour":   parse 0.5 cup → 0.5 × 125 g/cup = 62.5 g → flour: 1.0  → 62.5 g flour
"3 oz cornmeal":   parse 3 oz   → 3 × 28.35        = 85.0 g → flour: 1.0  → 85.0 g flour
```

Both land in "grams of flour", directly comparable. Cornmeal, masa, polenta and
cornstarch are all ~pure starch → the `flour` part.

### Reconstructing mangled fractions — how do we trust `1/2` vs `12`?

RecipeNLG sometimes drops the slash, turning `1/4 cup` into `14 cup`, `1/2
teaspoon` into `12 teaspoon`, `3/4 cup` into `34 cup` (hundreds of thousands of
lines). `src/units.py` reconstructs the fraction **only when all of** these hold:

1. the token is a standard cooking fraction — numerator < denominator, both
   single digits, denominator in {2,3,4,8} (plus 1/16): `12, 13, 14, 18, 23, 34,
   38, 58, 78, 116`;
2. it is followed by an imperial **volume** unit (`cup`/`tbsp`/`tsp`/`pt`/`qt`/`gal`)
   or **pound**;
3. it is **not** a weight unit — `oz`, `g`, `ml` are never reconstructed.

Why this is trustworthy:

- Whole-number *volumes* ≥ 10 essentially never appear in a home recipe — `12
  cups`, `34 cups` of anything are implausible — whereas `1/2 cup`, `3/4 cup`
  are among the most common quantities. So `12 cup` is almost always `1/2 cup`.
  (Measured over the Food.com data: correct `1/2`/`1/4` appear ~337k/208k times,
  mangled `12`/`14` ~231k/142k times, and a genuine "12 cups"-style line is
  negligible.)
- Weight units are the reverse: `12 oz`, `16 oz`, `500 g` are real, common whole
  amounts, and fractional weights are rare. So `12 oz` stays 12 oz.
- `lb` is the one weight exception: `1/2 lb` is common and `12 lb` of an
  ingredient is implausible, so `12 lb` → `1/2 lb`.

Residual risk: a genuinely huge volume (a 12-cup batch) would be misread as a
fraction — a factor-of-24 error that the robust-outlier step (`EllipticEnvelope`)
would flag and drop anyway.

The raw files are **git-ignored** (see `.gitignore`); re-download them to
reproduce.

## Taxonomy (a parameter, not a fact)

`src/tags.py` maps Food.com tags to 7 primary classes plus a weak tier, by
precedence (leaf tag beats parent) with a `strong`/`medium`/`weak` confidence.
The classes are *compositional* families: muffins and scones sit with
`quick_bread` (the same 2:2:1:1 batter as a loaf), and pie dough and laminated
pastry are one `pie_pastry` family (both fat-dominant, egg-free, water-poor
doughs — the difference is technique, not ratio):

| Class | Tags | Book (Ruhlman) | Wiki |
|---|---|---|---|
| `bread` | `breads`, `sourdough`, `rolls-biscuits` | Bread | Bread, buns, rolls |
| `quick_bread` | `quick-breads`, `muffins`, `scones`, `coffee-cakes` | Quick Bread, Muffin | Muffin, quick bread |
| `cake` | `cakes`, `cupcakes`, `cheesecake` | Pound/Sponge/Quick Cake | Cake, torte |
| `cookie` | `cookies-and-brownies`, `bar/drop/hand/rolled-cookies` | Cookie Dough | Cookie |
| `brownies` | `brownies` + title rescue (brownie/blondie) | — | Brownie, blondie |
| `pie_pastry` | `pies-and-tarts`, `pies`, `tarts`, `savory-pies`, `danish`, `crusts-pastry-dough-2` + title rescue | Pie Dough, Pâte à Choux, Viennoiserie | Pie, tart, pastry |
| `batter` | `pancakes-and-waffles` | Crepe, Pancake | — |
| `dessert_other` *(weak)* | `desserts` only, `cobblers-and-crisps`, `puddings-and-mousses` | — | — |

Two classes are under-represented in Food.com tags and use **title rescues**:

- `pie_pastry` — few laminated-dough tags exist, so titles naming croissants,
  puff/rough pastry, choux, éclairs, strudel, phyllo, palmiers, turnovers,
  empanadas, … are assigned *only when the tags are weak or absent* (n ≈ 3,200
  after merging with pies/tarts; title-agreement 0.87).
- `brownies` — Food.com files brownies under the generic `bar-cookies` leaf, so
  the explicit `brownies` leaf has only ~70 recipes. A title naming a
  brownie/blondie **overrides a generic cookie tag** (n ≈ 1,250;
  title-agreement 1.00).

The `dessert_other` weak tier is excluded from primary scoring. **The taxonomy
is a parameter** — if a class proves unreliable, edit the table and re-run.

## Pipeline

1. **Reference** — `scripts/fetch_fdc.py` → `data/reference/fdc_srlegacy.csv`.
2. **Build** — `scripts/build_dataset.py` joins RecipeNLG + Food.com, parses
   grams, filters from-scratch, decomposes (structural; add-ins zeroed) →
   `data/recipes_tagged.csv`.
3. **Validate tags** — `scripts/validate_tags.py` cross-checks each class
   against title keywords, ingredient signals, and nutrition →
   `output/tag_validation.txt`.
4. **Validate decomposition** — `scripts/validate_nutrition.py` correlates
   estimated `fat_g`/`sugar_g` against Food.com nutrition → `output/nutrition_validation.csv`.
5. **Simplex + PCA + cluster + continuum** — `main.py --cluster`.

## Setup

```sh
nix develop              # Python 3.13 + deps (pinned by flake.lock)
```

## Usage

```sh
# 0. Fetch the USDA reference (once)
nix develop -c python scripts/fetch_fdc.py

# 1. Build the labeled dataset (RecipeNLG + Food.com + USDA)
nix develop -c python scripts/build_dataset.py

# 2. Validate the labels and the decomposition
nix develop -c python scripts/validate_tags.py
nix develop -c python scripts/validate_nutrition.py

# 3. Run the analysis (clustered)
nix develop -c python main.py --input data/recipes_tagged.csv --outdir output/ --cluster

# Optional embedding
nix develop -c python main.py --input data/recipes_tagged.csv --outdir output/ --cluster --embed umap
```

Tests:

```sh
nix develop -c pytest tests/
```

## Output files

| File | Contents |
|---|---|
| `data/recipes_tagged.csv` | joined, tagged recipes (structural `*_g` grams) |
| `data/reference/fdc_srlegacy.csv` | USDA SR Legacy reference (per-100 g) |
| `output/tag_validation.txt` / `.csv` | per-class tag-correctness report |
| `output/nutrition_validation.csv` | decomposition vs nutrition correlations |
| `output/compositions.csv` | per-recipe simplex proportions + labels + archetype distance |
| `output/variance.csv` / `loadings.csv` / `scree.png` | log-ratio PCA dimensionality + part balances |
| `output/pca_biplot.png` / `ternary.png` | static views (book archetypes as stars) |
| `output/tag_confusion.csv` / `.png` | true-class × cluster heatmap |
| `output/class_pc1_summary.csv` | the continuum: class distribution along PC1 |
| `output/clusters.csv` / `cluster_report.txt` | cluster assignment + ARI vs tags |

## Reading the results

- `variance.csv` / `scree.png` — the simplex really is 4-D; PC1 (rich vs lean)
  dominates but is only half the variance.
- `loadings.csv` — PC1 = `+sugar +fat +egg vs −liquid −flour`, exactly the
  rich-vs-lean balance Ruhlman describes.
- `class_pc1_summary.csv` — the classes order correctly along PC1, confirming the
  ratio *does* encode the right gradient.
- `simplex_3d.html` — the 3D tetrahedron `flour / liquid+egg / fat / sugar`; the
  egg-into-liquid fold separates the tag classes best of all ten merges (see
  *Result*).
- Clustering runs in the **top-3 log-ratio PCs** (not 2): 3D beats 2D and PC4
  only adds noise.
- `tag_confusion.png` and `cluster_report.txt` — the classes bleed into each
  other (ARI ≈ 0.21, silhouette ≈ 0): baking is a continuum, and the
  Food.com tags are fuzzy labels on it, not crisp ratio clusters.

`tag_validation.txt` flags which classes are trustworthy: `bread` is the most
heterogeneous (only ~46% contain yeast), because Food.com's `breads` tag blurs
yeast breads, quick breads and enriched doughs — the natural first place to
refine the taxonomy.