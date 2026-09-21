# Step 20: approximate prediction uncertainty

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System**. The GreenPulse research PDF (especially its intervention-uncertainty discussion on page 93) is the primary design reference. This step attaches an approximate cooling range to each tree, cool-roof, or combined what-if API response. No value is generated from an absent model or invented performance metric.

## Calculation

For cooling magnitude `Ĉ` (°C) predicted by the saved XGBoost scenario:

- `σ_model = mean RMSE across the five held-out 5 km spatial CV folds`, read from `models/model_metadata.json` at `spatial_cv_metrics.rmse_c.mean`.
- `σ_param = |Ĉ| × CV_intervention`.
- `σ_total = sqrt(σ_model² + σ_param²)`.
- Approximate lower bound: `max(0, Ĉ − 1.645 × σ_total)`.
- Approximate upper bound: `Ĉ + 1.645 × σ_total`.

All cooling and uncertainty values are in °C. The range is a **nominal, normal-style approximation**, not a coverage-calibrated statistical prediction interval. The spatial CV RMSE measures LST prediction errors in held-out areas; it does **not** directly measure the error of an intervention temperature difference. The two terms may be correlated, errors may not be normal, and the 90% coverage claim has not been validated. The lower bound is clipped to zero because the display quantity is cooling magnitude, not signed ΔLST. The signed ΔLST remains available separately.

## Editable assumptions

All intervention coefficients, display thresholds, evidence status, version, horizon/survival provenance, and coverage-validation status are visible in [`backend/app/ml/uncertainty_assumptions.json`](../backend/app/ml/uncertainty_assumptions.json):

| Intervention | MVP CV assumption |
| --- | ---: |
| Cool roof | 0.08 |
| Tree canopy | 0.20 |
| Green roof | 0.15 |
| Cool pavement | 0.10 |

Green roofs and cool pavements are **configuration entries for later steps**, not implemented simulators. The entries are suggested research-prototype assumptions, **not measured Pune uncertainty coefficients**. Edit the JSON and restart the backend to change them. For a combined tree-plus-roof scenario, the MVP uses `sqrt(CV_tree² + CV_roof²)` and applies that effective CV to the jointly predicted cooling magnitude. This assumes independent parameter contributions; it is not empirically verified. The combined temperature itself still comes from one joint XGBoost re-prediction.

The JSON also declares the multiplier `1.645`, confidence thresholds, and prediction-horizon text. Display categories use `σ_total`:

- **High:** less than 0.3 °C.
- **Medium:** 0.3–0.6 °C, including both endpoints.
- **Low:** greater than 0.6 °C.

These are **MVP communication thresholds**, not probabilities or validated reliability grades. The API emits `coverage_calibrated: false`, and the UI calls the output an uncalibrated model-sensitivity range. Coverage-calibrated wording is reserved for a future configuration backed by empirical coverage validation. A tree scenario's horizon says *after the requested canopy is established*. No numeric growth year or survival rate is asserted; neither has been modeled. A roof scenario's horizon is after retrofit under comparable March–May daytime satellite overpass conditions. LST is not pedestrian air temperature.

## Files and API behavior

- [`backend/app/ml/uncertainty.py`](../backend/app/ml/uncertainty.py) validates configuration and saved spatial-CV metrics, calculates the range, and attaches it to scenario data.
- [`backend/app/main.py`](../backend/app/main.py) adds `uncertainty` to tree-only, roof-only, and combined API responses. If the real model metadata lacks spatial CV RMSE or refers to a different dataset version, it returns HTTP 503 rather than a point estimate without uncertainty.
- [`frontend/src/pages/ScenarioSimulator.jsx`](../frontend/src/pages/ScenarioSimulator.jsx) displays mean cooling, lower and upper bounds, MVP confidence category, prediction horizon, and expandable assumptions alongside the signed scenario ΔLST.

The `uncertainty` response contains `mean_cooling_c`, `lower_bound_c`, `upper_bound_c`, `confidence_category`, `prediction_horizon`, `sigma_model_c`, `sigma_param_c`, `sigma_total_c`, `interval_label`, and `assumptions`.

## Windows PowerShell verification

From the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_uncertainty -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Expected: six focused uncertainty tests pass, followed by the full project suite. Tests use **ARTIFICIAL TEST FIXTURES** for formula checks; their temperatures and RMSE values are not Pune results.

To inspect the dashboard, start FastAPI and Vite in separate PowerShell windows as described in the [tree simulator guide](tree_canopy_simulator.md), then open `http://localhost:5173/scenario-simulator`. The real processed ML grid, trained model, and spatial CV metadata are still absent in this workspace, so submitting a scenario must show an unavailable state and **no numeric cooling or range**. Once those real artifacts exist, the response and dashboard will show the calculated values and assumptions.
