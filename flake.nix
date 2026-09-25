{
  # Baking ratio analysis: do ingredient ratios predict the kind of baked good?
  #
  # Two stages (see README):
#   1. preprocess  scripts/preprocess.py — raw corpora -> preprocessed
#                  per-recipe dataset (simplex proportions + tag labels)
#   2. analysis    scripts/analyze.py    — dataset -> PCA, clustering,
#                  figures, validation diagnostics, results
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
        #    where a USDA value exists. nix also unpacks the archive and keeps
        #    only the three tables the pipeline reads (fdc-tables below), which
        #    the shell links at data/raw/fdc; src/preprocess/fdc.py then just
        #    compacts them into data/interim/fdc_srlegacy.csv.
        fdc-sr-legacy = pkgs.fetchurl {
          name = "sr_legacy.zip";
          url = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip";
          hash = "sha256-uAgXKUuIUFMKrt8uUVwCWTsYJPdjoP81blwggWQ+b9A=";
        };

        # The archive holds one top-level directory with 20 tables and docs;
        # only food.csv, food_category.csv and food_nutrient.csv matter for the
        # decomposition. Unpacking is a cached nix derivation, not pipeline
        # code — fdc-tables is a flat directory of those three CSVs.
        fdc-tables = pkgs.runCommand "fdc-sr-legacy-tables"
          { nativeBuildInputs = [ pkgs.unzip ]; } ''
          mkdir -p $out
          unzip -j -q ${fdc-sr-legacy} \
            'FoodData_Central_sr_legacy_food_csv_2018-04/food.csv' \
            'FoodData_Central_sr_legacy_food_csv_2018-04/food_category.csv' \
            'FoodData_Central_sr_legacy_food_csv_2018-04/food_nutrient.csv' \
            -d $out
        '';

        # 3. Food.com corpus (shuyangli94, 2019): tags (the independent class
        #    labels) and per-recipe nutrition. Kaggle requires a login, so this
        #    dataset CANNOT be fetched by nix: download RAW_recipes.csv manually
        #    from
        #
        #      https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions
        #
        #    into data/raw/food/RAW_recipes.csv. The dev shell validates the
        #    file against the pinned sha256 below on every entry (nix checks,
        #    not the pipeline), so a wrong/drifted file fails loudly instead of
        #    silently changing the labels.
        food-recipes-sha256 = "6a8136d1da9e03396a9f52d72200b3fddb8fe103f11e1496effca30ac4e0539f";
      in
      {
        # Manual fetch targets (optional): `nix build .#recipe-nlg` etc.
        packages.recipe-nlg = recipe-nlg;
        packages.fdc-sr-legacy = fdc-sr-legacy;
        packages.fdc-tables = fdc-tables;

        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];

          shellHook = ''
            echo "baking-ratios dev shell — Python ${python.version}"

            # Add a store symlink at each dataset's config.py location — but
            # only when it is missing, so existing local copies (like the
            # official RecipeNLG distribution) are left alone and nothing is
            # fetched until it is actually needed.
            if [ ! -e data/raw/RecipeNLG/RecipeNLG_dataset.csv ]; then
              mkdir -p data/raw/RecipeNLG
              nix build ".#recipe-nlg" -o data/raw/RecipeNLG/RecipeNLG_dataset.csv
            fi
            if [ ! -e data/raw/fdc/food.csv ]; then
              mkdir -p data/raw
              nix build ".#fdc-tables" -o data/raw/fdc
            fi

            # Food.com is login-gated (Kaggle), so nix cannot fetch it. The
            # pinned hash above is the file's identity; validate here.
            if [ -e data/raw/food/RAW_recipes.csv ]; then
              actual=$(sha256sum data/raw/food/RAW_recipes.csv | cut -d' ' -f1)
              if [ "$actual" != "${food-recipes-sha256}" ]; then
                echo "ERROR: data/raw/food/RAW_recipes.csv does not match the pinned sha256"
                echo "  expected: ${food-recipes-sha256}"
                echo "  actual:   $actual"
                echo "  make sure the file is the original RAW_recipes.csv from the Kaggle dataset"
                exit 1
              fi
            else
              echo "  Food.com:   data/raw/food/RAW_recipes.csv is MISSING — download it (login) from"
              echo "              https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions"
              echo "              expected sha256: ${food-recipes-sha256}"
            fi
          '';
        };
      });
}