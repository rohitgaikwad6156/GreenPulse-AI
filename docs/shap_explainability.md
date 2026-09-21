# Step 16: TreeSHAP explanations for LST

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System**. This step explains the saved XGBoost prediction of continuous **land surface temperature (LST in °C)**. It does not estimate pedestrian air temperature or causal effects.

The GreenPulse research PDF, especially its TreeSHAP blueprint (page 83) and correlation warning (page 89), is the primary design reference. The current [SHAP TreeExplainer documentation](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html) defines the path-dependent baseline and additivity behavior used here. The requested five display categories are used.

## Prerequisites

Real `data/processed/greenpulse_ml_grid.parquet` and `data/processed/metadata.json` must exist from Step 12. Real `models/xgboost_lst.joblib` and `models/model_metadata.json` must exist from Step 15. The model metadata and dataset SHA-256, model-artifact SHA-256, feature order, CRS, resolution, row count, target, and objective must match. The artifact hash is checked before `joblib.load`; only load a model produced by this trusted workspace because joblib uses pickle. No real artifacts are supplied in this repository.

From the project root in Windows PowerShell, install this step's dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-shap.txt
```

Select the first real grid ID in the Parquet table and run the explanation:

```powershell
$selectedGridId = .\.venv\Scripts\python.exe -c "import pyarrow.parquet as pq; print(pq.read_table('data/processed/greenpulse_ml_grid.parquet', columns=['grid_id']).column('grid_id')[0].as_py())"
.\.venv\Scripts\python.exe scripts\build_shap_explanations.py --grid-id $selectedGridId
```

`--sample-size 2000` is the default. A deterministic random sample is used for global importance and Pearson correlations; its row count and seed appear in output. A sample estimate may differ from whole-city importance, especially if land cover types are unevenly represented. The selected local cell is explained even if it was not in the sample.

Outputs in `models/`:

- `shap_global.json`: feature mean absolute SHAP (°C), grouped importance, all pairwise Pearson correlations, pairs with absolute `r >= 0.85`, and model/dataset/source hashes.
- `shap_local.json`: `baseline_lST`, `predicted_lst`, `grid_id`, per-feature `raw_value`, signed `shap_value_c`, `direction`, grouped contributions, UI waterfall/bar data, and model/dataset/source hashes.
- `shap_global_importance.png`: feature importance quality-control bar chart.
- `shap_local_waterfall.png`: signed local contribution chart.

For every sampled global row and the selected local row, `predicted_lst ≈ baseline_lST + Σ shap_value_c`; code checks this with relative tolerance `1e-5` and absolute tolerance `0.001 °C`. Positive contributions have direction `warming`, negative contributions `cooling`. `shap_value_c` is the signed, raw model-output contribution used in that additivity check. Separately, `warming_percentage_ui = 100 × positive_shap_value_c / Σ positive_shap_value_c`, with zero for cooling features. These normalized percentages are presentation-only shares of positive model contributions, **not °C, probabilities, or shares of physical heat causation**. Each category's local contribution is the signed sum of its member features. Global category importance is the sum of member mean absolute contributions, clearly labelled so it is not mistaken for a signed group effect.

Correlated NDVI/context, NDBI/built fraction, and similar features can split or exchange attribution as the fitted trees change. Grouping makes the display easier to read but does **not** mathematically fix instability. The JSON reports redundant pairs before grouping. TreeSHAP here uses `tree_path_dependent`, whose baseline comes from training counts in tree paths; a different dependence assumption or background may redistribute credit. SHAP describes a fitted model prediction and is not evidence that changing a feature will produce the attributed temperature change.

This step writes no API route or frontend view. These JSON structures are ready for a later API integration step.

## Tests and expected status

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_shap_explain -v
```

Expected: four tests pass. They use **ARTIFICIAL TEST FIXTURES** in temporary directories and cover correlated features, additivity, dataset mismatch, and a stale model artifact. With this repository's current missing real model, running the explanation command should stop with `Real trained XGBoost model and model metadata are required; run Step 15 first`, and it must not create real explanation files.
