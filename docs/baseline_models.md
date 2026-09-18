# Step 14: spatially evaluated baseline LST regressors

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** This step compares three regressors for the **continuous observed land surface temperature target `lst_c` in °C**. It creates no 0–100 risk categories, SHAP claims, intervention results, or pedestrian air-temperature predictions.

## Real inputs required

- `data/processed/greenpulse_ml_grid.parquet` and its `data/processed/metadata.json` from Step 12.
- `data/processed/spatial_cv_blocks.parquet` and `data/processed/spatial_cv_metadata.json` from Step 13.
- At least five populated 5 km blocks, with at least two held-out cells and nonconstant observed LST in every validation fold.

The real ML Parquet is **not yet present** in this workspace. This step therefore cannot honestly produce Pune MAE, RMSE, R², comparison plots, or `models/baseline_metrics.json` now. Tests fit models only to explicitly **ARTIFICIAL TEST FIXTURES** in temporary directories and do not save those values under `models/`.

## Method

All three models use the **exact saved Step 13 block-to-fold mapping**. The evaluator checks the saved 5 km origin, block coordinates, fold summary, row counts, and source table path before fitting. It never makes a new random split. Each whole block appears in validation in exactly one of five folds and never appears in training for that same fold.

For every fold and every model, a fresh estimator is fitted on training blocks only. Validation blocks are untouched until prediction. The feature names come from Step 12 metadata, which excludes `lst_c`, coordinates, grid IDs, and ward labels from predictors.

| Baseline | Fixed configuration |
|---|---|
| Linear Regression | `StandardScaler` fitted **inside the training fold**, followed by ordinary least squares `LinearRegression`. Scaling from all rows would leak validation information. |
| Decision Tree Regressor | `max_depth=16`, `min_samples_leaf=5`, `random_state=42`. |
| Random Forest Regressor | 100 trees, `max_depth=16`, `min_samples_leaf=5`, `random_state=42`, two worker jobs by default. |

These are fixed, untuned baseline settings; they are not claimed as optimal. Scikit-learn documents the [linear model](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html), [decision tree](https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeRegressor.html), and [random forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html). The model fitting code records software versions and settings in the JSON result.

## Metrics

All metrics are computed **only on each held-out fold**:

`MAE = (1/n) × Σ |yᵢ − ŷᵢ|` in °C.

`RMSE = sqrt[(1/n) × Σ(yᵢ − ŷᵢ)²]` in °C.

`R² = 1 − [Σ(yᵢ − ŷᵢ)² / Σ(yᵢ − ȳ)²]`, where `ȳ` is the **validation fold's observed mean**. R² is unitless and can be negative. If a validation fold has constant observed LST, R² is undefined and the run stops rather than inventing a value.

For each metric, the output reports the arithmetic mean **± sample standard deviation** of the five fold metrics (`ddof=1`). This describes variation among the five spatial holdouts; it is not a confidence interval. The plot displays individual fold values as points and mean ± standard deviation as bars.

## Windows PowerShell commands

Run from the repository root. The ML requirements include scikit-learn, PyArrow, and the existing geospatial dependencies.

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-ml.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_baselines.py' -v
```

Once **real** Step 12 and Step 13 files exist:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_baselines.py
```

The command prints one MAE, RMSE, and R² mean ± standard deviation line per model, using values calculated from that real dataset. No numeric performance is supplied in this document because none has been measured. The fixed forest size can be changed with `--rf-trees`, and CPU parallelism with `--rf-jobs`; both choices are saved in the result JSON. Keep the same settings when comparing repeated runs.

## Expected outputs after a successful real-data run

- `models/baseline_metrics.json`: input table and fold-map paths, continuous target and units, feature list, fixed model settings, software versions, five held-out metric triplets per model, and mean ± sample standard deviation for each metric.
- `models/baseline_comparison.png`: side-by-side MAE, RMSE, and R² comparison panels with individual fold values.

The evaluator saves **metrics only**. It does not save or deploy fitted baseline models; a later training/deployment step should explicitly choose how to fit a final model after spatial evaluation.

## Checks and limitations

The tests verify the metric equations with hand-checkable artificial numbers, five shared held-out folds across all three regressors, rejection of a changed fold map, and rejection of target/coordinate leakage into feature metadata. The full project test suite is also run after this step.

Spatial blocks reduce the strongest neighbour leakage, but cells across adjacent block borders can still share optical context or Landsat thermal information. The 30 m LST product has coarser native thermal sensing, so grid rows are not independent thermometers. These baseline comparisons use the available complete-case table; missingness from clouds or source coverage may create spatial selection bias. R² can be unstable when a held-out block has little LST variation. Any later tuning or preprocessing must stay inside training folds, with validation blocks untouched.
