{
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
          ps.scikit-learn
          ps.matplotlib
          ps.plotly
          ps.umap-learn
          ps.hdbscan
          ps.pytest
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];
          shellHook = ''
            echo "baking-ratios dev shell — Python ${python.version}"
          '';
        };
      });
}
