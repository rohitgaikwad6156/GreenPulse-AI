# Step 15: main XGBoost LST regressor

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** This step trains its main model for **continuous land surface temperature (`lst_c`) in °C**. It creates no risk categories, SHAP causal claims, air-temperature estimates, or intervention effects.

The boosted-tree prediction has the requested mathematical form:

`ŷᵢ = Σ(k=1..K) fₖ(xᵢ)`

Each `fₖ` is one learned regression tree; the sum predicts LST in °C. The XGBoost objective is explicitly `reg:squarederror`. The [XGBoost Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html) and [parameter guide](https://xgboost.readthedocs.io/en/stable/parameter.html) describe the estimator and tuning parameters.

## Real inputs and why none are fabricated

The script requires:

1. `data/processed/greenpulse_ml_grid.parquet` and `data/processed/metadata.json` from Step 12.
2. `data/processed/spatial_cv_blocks.parquet` and `data/processed/spatial_cv_metadata.json` from Step 13.
3. `models/baseline_metrics.json` from Step 14, evaluated on the **same dataset, feature list, and saved spatial folds**.

These real artifacts are still absent in this workspace. Consequently, **no real Pune XGBoost model, MAE, RMSE, R², or comparison plot has been produced**. The tests fit only explicitly artificial temporary fixtures. Research-paper performance numbers are never copied into project results.

## Spatially safe tuning and evaluation

A plain random cross-validation split would let nearby 30 m cells leak across folds. The pipeline therefore uses **nested spatial validation**:

1. **Outer evaluation:** use the exact saved five Step 13 folds of whole 5 km blocks. An outer validation block is unseen during its fold's tuning and training.
2. **Inner Optuna tuning:** within each outer training set, divide its remaining 5 km blocks into three `GroupKFold` inner folds. Optuna minimizes mean **inner-fold RMSE**. It never sees that outer fold's held-out LST values. The [Optuna study API](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.create_study.html) supports the fixed trial budget used here.
3. **Outer scoring:** fit an XGBoost regressor with that outer fold's selected parameters on the entire outer training set, then predict its held-out blocks. Calculate MAE, RMSE, and R² using the same formulas and target units as Step 14.
4. **Final deployment fit:** after all outer scores are recorded, run a separate spatial Optuna search on the full dataset using the saved five block groups. Fit one final model on **all** retained rows with those final parameters and save it. The outer scores estimate the tuning workflow's geographic performance; they are **not** scores from predicting the rows on which this final model was fitted.

The default budget is **eight Optuna trials per outer fold**, plus eight final full-dataset trials. For large real tables this means many XGBoost fits and can take substantial CPU time. `--trials` controls the budget; the chosen value is recorded. A tiny budget is useful only to test wiring and is not a thorough hyperparameter search. The search is deterministic for a fixed dataset, software version, and seed but exact floating-point results can still vary across platforms.

| Tuned parameter | Search range |
|---|---|
| `max_depth` | integer 2–8 |
| `learning_rate` | 0.01–0.2, log scale |
| `n_estimators` | 100–500, step 50 |
| `subsample` | 0.6–1.0 |
| `colsample_bytree` | 0.6–1.0 |
| `gamma` | 0–5 |
| `reg_alpha` | 1e-6–10, log scale |
| `reg_lambda` | 1e-3–20, log scale |

Other fixed settings are `tree_method=hist`, `random_state=42`, and two CPU jobs by default. Only fields listed in the Step 12 metadata feature list enter the model; grid IDs, coordinates, ward names, and target values are excluded as predictors.

## Metrics and baseline comparison

For every untouched outer validation fold:

`MAE = (1/n) × Σ |yᵢ − ŷᵢ|` in °C.

`RMSE = sqrt[(1/n) × Σ(yᵢ − ŷᵢ)²]` in °C.

`R² = 1 − [Σ(yᵢ − ŷᵢ)² / Σ(yᵢ − ȳ)²]`, where `ȳ` is the held-out fold's mean observed LST. R² is unitless and can be negative.

The report stores all five outer-fold metrics and their **arithmetic mean ± sample standard deviation** (`ddof=1`). It compares those values against the Step 14 Linear Regression, Decision Tree, and Random Forest metrics **only after verifying the baseline JSON refers to the same dataset, features, 5 km mapping, and held-out fold sizes**. A negative R² or XGBoost score worse than a baseline is a valid measured outcome, not a reason to change the reported values.

## Windows PowerShell commands

From the repository root:

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-xgboost.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_xgboost_lst.py' -v
```

After the real Step 12–14 artifacts exist:

```powershell
.\.venv\Scripts\python.exe .\scripts\train_xgboost_lst.py
```

The command prints measured outer-fold MAE, RMSE, and R² means ± standard deviations, then prints output paths. For a limited wiring run on a real dataset, `--trials 2` shortens Optuna's search but must be described as a limited search when reporting results. `--jobs` controls CPU parallelism; increasing it can raise memory use. Do not run the real command until the upstream source layers, table, spatial folds, and baselines are valid.

## Outputs after a successful real-data run

- `models/xgboost_lst.joblib`: final XGBoost regressor fitted on all retained real rows after spatial tuning.
- `models/model_metadata.json`: feature list, UTC training time, SHA-256 dataset version, source date range, target and units, all five held-out scores and mean/std, final hyperparameters, each outer fold's selected hyperparameters, CRS, 30 m resolution, software versions, and nested spatial validation method.
- `models/xgboost_baseline_comparison.png`: visual comparison of XGBoost against all three saved baselines for MAE, RMSE, and R².

The pipeline reloads the newly saved `.joblib` in the same run and checks sample predictions before publishing it. **Only load joblib files produced by a trusted source** because joblib uses Python pickle serialization; see the [joblib persistence guide](https://joblib.readthedocs.io/en/stable/user_guide/persistence.html).

## Scientific limits

- Whole 5 km blocks reduce neighbour leakage but may still touch other folds at boundaries. Focal features and Landsat's coarser thermal footprint can cross those boundaries. A later buffered evaluation or larger blocks can test sensitivity.
- The Step 12 table uses a complete-case policy. Cloudy or poorly mapped cells are absent, so results may not represent every ward equally.
- The finite Optuna search explores only the stated ranges and trial budget. The best observed setting is not guaranteed globally optimal.
- LST measures land surface temperature, not pedestrian air temperature. High predictive accuracy would not prove that changing an input feature causes the predicted cooling.
