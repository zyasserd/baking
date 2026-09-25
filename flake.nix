{
  # Baking ratio analysis: do ingredient ratios predict the kind of baked good?
  #
  # Two stages (see README):
  #   1. preprocess  scripts/1_preprocess.py — raw corpora -> preprocessed
  #                  per-recipe dataset (simplex proportions + tag labels)
  #   2. analysis    scripts/2_analyze.py    — PCA, clustering, figures, results
  #
  # Every tunable parameter lives in config.py.

  description = "Baking ratio analysis: dimensionality reduction on the ingredient simplex";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python313;
        pythonEnv = python.withPackages (ps: [
          ps.numpy
          ps.pandas
          ps.scipy
          ps.scikit-learn
          ps.matplotlib
          ps.plotly
          ps.pytest
        ]);

        # ══════════════════════════════════════════════════════════════════════
        # DATASETS — fetched with pinned sha256 so every run is reproducible.
        # ══════════════════════════════════════════════════════════════════════
        #
        # 1. RecipeNLG (Bien et al. 2020, ~2.3 GB): 2.3 M recipes with raw
        #    ingredient text ("1 1/2 c. flour"), source links and source site.
        #    Official distribution is behind a registration form
        #    (https://recipenlg.cs.put.poznan.pl/dataset); the fetch below is a
        #    byte-identical public mirror on Hugging Face — the sha256 was
        #    verified against the official download.
        recipe-nlg = pkgs.fetchurl {
          name = "RecipeNLG_dataset.csv";
          url = "https://huggingface.co/datasets/innovate-data/RecipeNLG/resolve/main/RecipeNLG_dataset.csv";
          hash = "sha256-83buC7n5nzI3Yav2Jw1FP07/IALDYl0Eyrz4tX3KCAM=";
        };

        # 2. USDA FoodData Central, SR Legacy (2018-04, the final Standard
        #    Reference release; ~7,800 foods with full proximate composition).
        #    This is the *reference* behind the ingredient decomposition
        #    (src/preprocess/reference.py) — hand-tuned numbers are never used
        #    where a USDA value exists. The zip is unpacked and compacted into
        #    data/reference/fdc_srlegacy.csv by src/preprocess/fdc.py.
        fdc-sr-legacy = pkgs.fetchurl {
          name = "sr_legacy.zip";
          url = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip";
          hash = "sha256-uAgXKUuIUFMKrt8uUVwCWTsYJPdjoP81blwggWQ+b9A=";
        };

        # 3. Food.com corpus (shuyangli94, 2019): tags (the independent class
        #    labels) and per-recipe nutrition. Kaggle requires a login, so this
        #    dataset CANNOT be auto-fetched: download RAW_recipes.csv manually
        #    from
        #
        #      https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions
        #
        #    into data/raw/food/RAW_recipes.csv. The file's sha256 is pinned in
        #    config.py (RAW_FOOD_RECIPES_SHA256) and verified by
        #    scripts/1_preprocess.py on every run, so a wrong/drifted file fails
        #    loudly instead of silently changing the labels.
        food-recipes-sha256 = "sha256-aoE20dqeAzlqn1LXIgCz/duP4QPxHhSW7/yjCsTgU58=";
      in
      {
        # Manual fetch targets (optional): `nix build .#recipe-nlg` etc.
        packages.recipe-nlg = recipe-nlg;
        packages.fdc-sr-legacy = fdc-sr-legacy;

        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];
          shellHook = ''
            echo "baking-ratios dev shell — Python ${python.version}"

            # Stage the nix-fetched datasets into their config.py locations.
            # Skipped when the files already exist (manual copies stay put;
            # building here is what downloads, on demand and once).
            if [ ! -e data/raw/RecipeNLG/RecipeNLG_dataset.csv ]; then
              mkdir -p data/raw/RecipeNLG
              nix build ".#recipe-nlg" -o data/raw/RecipeNLG/RecipeNLG_dataset.csv
            fi
            if [ ! -e data/reference/sr_legacy.zip ]; then
              mkdir -p data/reference
              nix build ".#fdc-sr-legacy" -o data/reference/sr_legacy.zip
            fi
            if [ ! -e data/raw/food/RAW_recipes.csv ]; then
              echo "NOTE: data/raw/food/RAW_recipes.csv is missing."
              echo "  Download RAW_recipes.csv (login required) from"
              echo "  https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions"
              echo "  expected sha256: 6a8136d1da9e03396a9f52d72200b3fddb8fe103f11e1496effca30ac4e0539f"
            fi
          '';
        };
      });
}