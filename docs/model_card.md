# GreenPulse AI — Model Card

**Status:** MODEL NOT TRAINED ON REAL PRODUCTION DATA YET

**Last reviewed:** 2026-10-05

This card defines the intended and implemented model contract. Performance sections remain unavailable until the accepted real production dataset is created and spatial validation completes. Files already present under production model paths are legacy/demo artifacts, not real model evidence.

## Model identity and intended data

| Item | Implemented contract |
| --- | --- |
| Model | XGBoost gradient-boosted regression trees for land-surface temperature |
| Target | `lst_c`, continuous land-surface temperature in °C |
| Objective and fixed settings | `reg:squarederror`; `tree_method=hist`; `random_state=42` |
| Initial intended season | 2025-03-01 to 2025-05-31. Actual trained period: **NOT AVAILABLE YET**; populate from `models/model_metadata.json → dataset_date_range`. |
| Analysis domain | Intended verified PMC + PCMC 30 m EPSG:32643 cells. Real accepted municipal coverage: **NOT AVAILABLE YET**. |
| Training rows | **NOT AVAILABLE YET**; populate from `models/model_metadata.json → dataset_rows`. |

The first real Heat Map profile uses exactly these five predictors, as defined in [ML dataset assembly](ml_dataset_pipeline.md) and the production feature contract:

| Predictor | Meaning |
| --- | --- |
| `ndvi` | QA-masked Sentinel optical vegetation index |
| `ndbi` | QA-masked Sentinel optical built-up index |
| `tree_canopy_pct` | ESA WorldCover tree-class fraction proxy within a cell |
| `built_pct` | ESA WorldCover built-class fraction proxy within a cell |
| `road_density` | Eligible mapped OSM motor-road centreline length per cell area |

Coordinates, grid/ward identifiers, ward names, `lst_c`, and WorldPop population density are not first-profile predictors. After real training, reconcile the final feature list in `data/processed/metadata.json → features` with `models/model_metadata.json → feature_list`; do not substitute the 13-feature demo metadata.

## Training and validation design

The implemented [spatial CV design](spatial_cv_pipeline.md) assigns whole 5 km blocks, using EPSG:32643 coordinates, to **five outer held-out folds**. Nearby 30 m cells are spatially correlated; a random row split could give optimistic estimates. Within each outer training partition, **three-fold GroupKFold** separates the remaining spatial groups while Optuna `TPESampler` selects settings by mean inner-fold RMSE. An outer validation block is unseen during that fold's tuning. After evaluation, the implementation tunes on the complete set of spatial groups and fits a final model on all retained rows. Outer metrics estimate the tuning procedure on held-out blocks; they are not in-sample scores for the final full-data fit.

The [baseline workflow](baseline_models.md) evaluates Linear Regression, Decision Tree Regressor and Random Forest Regressor on the same accepted dataset, five-feature list and saved spatial fold mapping before comparison with XGBoost. No baseline or XGBoost real-data evaluation has completed.

## Spatial validation performance

> No real production model result is available yet. Populate these values only from `models/model_metadata.json → spatial_cv_metrics` after accepted real spatial validation; each metric contains `mean` and `std` across outer folds.

| Metric | Mean | Fold SD | Status |
| --- | --- | --- | --- |
| MAE (°C) | **NOT AVAILABLE YET** | **NOT AVAILABLE YET** | `spatial_cv_metrics.mae_c.mean/std` |
| RMSE (°C) | **NOT AVAILABLE YET** | **NOT AVAILABLE YET** | `spatial_cv_metrics.rmse_c.mean/std` |
| R² | **NOT AVAILABLE YET** | **NOT AVAILABLE YET** | `spatial_cv_metrics.r2.mean/std` |

### Per-fold results

> Fold numbers describe the five-fold method, not completed evaluations. Populate every result from `models/model_metadata.json → outer_fold_results`; never use artificial test-fixture or demo metrics.

| Fold | Validation blocks | Validation rows | MAE (°C) | RMSE (°C) | R² |
| --- | --- | --- | --- | --- | --- |
| 1 | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| 2 | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| 3 | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| 4 | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| 5 | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |

### Baseline comparison

> Real baseline metrics are **NOT AVAILABLE YET**. Populate from a real `models/baseline_metrics.json` and reconcile the XGBoost values with `models/model_metadata.json → baseline_comparison` using the same dataset and fold mapping.

| Model | MAE (°C) | RMSE (°C) | R² |
| --- | --- | --- | --- |
| Linear Regression | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| Decision Tree Regressor | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| Random Forest Regressor | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| XGBoost | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |

## Training support

> Per-feature distributions are **NOT AVAILABLE YET**. The eventual `models/model_metadata.json → training_feature_distributions` records `count`, `min`, `p01`, `p05`, `median`, `p95`, `p99`, and `max`. These ranges support scenario extrapolation guards; they do not establish causal intervention validity.

| Feature | Count | Min | p01 | p05 | Median | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ndvi` | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| `ndbi` | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| `tree_canopy_pct` | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| `built_pct` | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |
| `road_density` | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET | NOT AVAILABLE YET |

## Tuning configuration and reproducibility

The ranges below are implemented *search-space definitions*, not selected trained hyperparameters. The code default is eight trials; the **actual** real-run trial budget must be read from saved metadata.

| Parameter | Implemented search range |
| --- | --- |
| `max_depth` | Integer 2–8 |
| `learning_rate` | 0.01–0.2, log scale |
| `n_estimators` | 100–500 in steps of 50 |
| `subsample` | 0.6–1.0 |
| `colsample_bytree` | 0.6–1.0 |
| `gamma` | 0–5 |
| `reg_alpha` | 1e-6–10, log scale |
| `reg_lambda` | 1e-3–20, log scale |

**Final selected hyperparameters: NOT AVAILABLE UNTIL REAL TRAINING.** See [the XGBoost workflow](xgboost_lst_pipeline.md) for implementation details.

| Real-run item | Current value | Populate from `models/model_metadata.json` |
| --- | --- | --- |
| Training timestamp | NOT AVAILABLE YET | `training_date_utc` |
| Dataset SHA-256 / version | NOT AVAILABLE YET | `dataset_version` (SHA-256-qualified version); verify accepted grid |
| Model artifact SHA-256 | NOT AVAILABLE YET | `model_artifact_sha256`; verify saved artifact |
| Dataset row count | NOT AVAILABLE YET | `dataset_rows` |
| Final feature list | NOT AVAILABLE YET | `feature_list`; reconcile with real `data/processed/metadata.json → features` |
| Software versions | NOT AVAILABLE YET | `software` |
| Final hyperparameters | NOT AVAILABLE YET | `final_hyperparameters` and `final_model_configuration` |
| Optuna trial budget | NOT AVAILABLE YET | `tuning.trials_per_outer_fold` and `tuning.final_full_dataset_trials` |
| Actual study period | NOT AVAILABLE YET | `dataset_date_range` |
| Spatial evaluation | NOT AVAILABLE YET | `outer_fold_results`, `spatial_cv_metrics`, `cv_mapping_path`, `block_size_m`, `outer_folds` |
| Git commit and repository state | NOT AVAILABLE YET | `git_commit`, `git_dirty`, `git_state`, `git_reproducibility_note` |
| Resolved pipeline command and parameters | NOT AVAILABLE YET | `pipeline_command`, `pipeline_parameters` |
| Reproducibility snapshot | NOT AVAILABLE YET | `reproducibility_snapshot` → `models/reproducibility_snapshot.json` after a real full build |
| Python and dependency identities | NOT AVAILABLE YET | Snapshot `runtime`, `dependency_identity.python_requirement_files` |
| Frontend lockfile identity | NOT AVAILABLE YET | Snapshot `dependency_identity.frontend_package_lock`; optional for model generation |

Although `models/xgboost_lst.joblib`, `models/model_metadata.json`, and `models/baseline_metrics.json` exist locally, the current upstream `data/processed/metadata.json` identifies its grid as **DEMO / SYNTHETIC DATA**. The existing model files therefore cannot populate real-run fields. Real dataset and model checksums, training date, rows, feature ranges, selected settings, and performance remain **NOT AVAILABLE YET**.

The future [reproducibility snapshot](reproducibility.md) links a successful real run's Git state, resolved command, source checksums, Python environment, requirement-file hashes, optional frontend lockfile, and dataset/CV/baseline/model hashes. None of those real-run values may be copied from current demo files.

## Intended use

After source acceptance and real spatial validation, this model is intended for research on seasonal urban land-surface heat patterns, relative identification of cells with elevated *modelled* LST, and PMC/PCMC-scale planning support. Exploratory intervention scenarios require separate capacity and calibration evidence. It is not a medical, personal safety, weather forecasting, or causal intervention tool.

## Unsupported interpretations

- Predicted LST is not pedestrian air temperature, and model outputs are not observed PMC/PCMC temperature measurements.
- Heat Hazard Score is not a health-risk probability.
- SHAP attribution is not causation; see [explainability](shap_explainability.md).
- A model response to changed features is not measured intervention cooling; high predictive accuracy would not establish the effect of changing NDVI or tree cover.
- The 30 m output grid does not imply independent native 30 m thermal sensing.
- Predictions outside supported training feature ranges must not be silently trusted; approximate uncertainty is distinct from calibrated coverage (see [uncertainty](prediction_uncertainty.md)).

## Limitations and readiness

Spatial dependence may remain across adjacent 5 km block boundaries. Landsat thermal information is coarser than the output grid. Cloud gaps and complete-case filtering may bias retained geography. A March–May composite is seasonal rather than an event measurement. WorldCover 2021 and OSM 2026 snapshots differ from the 2025 thermal season. NDVI/canopy and NDBI/built fractions can be correlated proxies. Optuna explores a finite search space. Predictive validation does not provide causal validity, field validation, or intervention calibration; those require separate evidence.

**Real production readiness checklist** — unchecked items require accepted real-run evidence, not merely implemented code:

- [ ] Verified five-source production gate
- [ ] Real 30 m ML grid built
- [ ] Real spatial block artifacts generated
- [ ] Baselines evaluated on those folds
- [ ] Nested XGBoost spatial CV completed
- [ ] Final real model saved and reload verified
- [ ] Real dataset and model SHA-256 checksums recorded
- [ ] Real MAE, RMSE and R² recorded
- [ ] Training feature distributions recorded
- [ ] Limitations and field-validation needs reviewed

The [Data Card](data_card.md) and [final acceptance review](final_acceptance_review.md) document the unfinished source gate. Replace placeholders only after source verification, real dataset build, fold assignment, real baseline/XGBoost runs, and artifact reload/checksum checks.
