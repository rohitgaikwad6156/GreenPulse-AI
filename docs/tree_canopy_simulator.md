# Step 18: Tree canopy what-if simulator

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System**. This simulator changes a real grid cell's model feature vector and runs the saved XGBoost LST regressor again. It does **not** ask an LLM for a cooling estimate. The GreenPulse research PDF's empirical-ML surrogate section (page 83) is the primary design reference.

## Calculation

- `T_base = f_XGB(x_base)`
- `T_scenario = f_XGB(x_modified)`
- `delta_lst_c = T_scenario - T_base`
- `cooling_magnitude_c = max(0, T_base - T_scenario)`

Both temperatures and the difference are **land surface temperature in °C**. A positive `delta_lst_c` is modelled warming; its cooling magnitude is zero. A negative difference is modelled cooling. Neither is an observed or proven causal intervention effect.

The slider covers **0 to +40 absolute percentage points** of canopy cover in one 30 m × 30 m cell. For a 900 m² cell, a +10-point request means 90 m² of additional canopy. The request is rejected if new canopy exceeds 100% or additional canopy area exceeds supplied **verified available planting ground**, which must exclude existing canopy. Built fraction alone cannot establish this available area.

The initial configurable empirical MVP assumption is `ΔNDVI = 0.01 × ΔCanopyPercentPoints`. This coefficient is for software prototyping and **requires local calibration**. It lives in [`backend/app/simulation/config.py`](../backend/app/simulation/config.py), along with cell area, slider bound, NDVI limits, and focal-window valid-cell assumptions. To try a different coefficient, set `GREENPULSE_CANOPY_NDVI_PER_PP` before starting the backend; the same value is returned to the UI and scenario response. No single numeric coefficient is asserted as a measured Pune relationship.

The modified features are `tree_canopy_pct`, `ndvi`, and, when present in the trained model, `ndvi_mean_3x3` and `ndvi_mean_5x5`. NDVI is clipped to [-1, 1]; focal values use the **actual** local NDVI change divided by 9 or 25 assumed valid cells. Other model features, including NDBI and built fraction, stay fixed because their canopy coupling is not calibrated. This is a one-cell what-if; it does not update neighboring cells, model canopy maturity or survival, or validate physical feasibility of shade geometry. Correlated features and out-of-distribution input combinations may make the model response unreliable. LST is not pedestrian air temperature.

## Files and API

- [`backend/app/simulation/config.py`](../backend/app/simulation/config.py): all MVP numeric assumptions and optional environment override.
- [`backend/app/simulation/tree_canopy.py`](../backend/app/simulation/tree_canopy.py): feature constraints, transformations, XGBoost re-prediction, and saved-artifact validation.
- [`backend/app/main.py`](../backend/app/main.py): `GET /api/simulation/tree-canopy/config` and `POST /api/simulation/tree-canopy`.
- [`frontend/src/pages/ScenarioSimulator.jsx`](../frontend/src/pages/ScenarioSimulator.jsx): slider, grid ID, verified area input, results, assumptions, and empty/error state.

The POST body contains `grid_id`, `canopy_increase_percentage_points`, and `feasible_ground_area_m2`. The response contains baseline LST, scenario LST, signed delta, cooling magnitude, modified and full scenario features, area demand, and assumptions. The endpoint checks that the real Parquet table and saved model metadata share the same dataset hash, features, CRS, resolution, date range, and row count. It returns HTTP 503 when those real artifacts are missing and HTTP 422 for an invalid or infeasible request. No demo dataset is used by this endpoint.

## Windows PowerShell test

Install the model dependency if needed, then run backend and frontend in separate PowerShell windows from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-xgboost.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

```powershell
Set-Location frontend
npm run dev -- --host localhost --port 5173 --strictPort
```

Open `http://localhost:5173/scenario-simulator` and `http://127.0.0.1:8000/docs`. The slider range and assumption label should load from the backend. Without the real Step 12 table and Step 15 model, submitting a scenario shows that a matching real dataset and model are required; it must show **no temperature value**. Once real artifacts and a verified planting-area assessment exist, select a real `grid_id`, enter available area, move the slider, and compare the returned baseline and scenario LST.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_tree_canopy -v
```

Expected: five passing tests using **ARTIFICIAL TEST FIXTURES** only. They check model re-prediction, exact transformed inputs, configurable coefficient, NDVI clipping, area constraints, and saved-model matching. Test predictions are not Pune climate results.
