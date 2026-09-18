# Step 19: Cool roof and combined what-if simulator

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System**. This step adds a cool-roof slider to the Step 18 tree-canopy simulator. Both scenarios modify a real 30 m model feature vector and re-run the saved XGBoost **LST in °C** regressor. No LLM generates a cooling number. The GreenPulse research PDF's empirical-ML surrogate and dual-slider prototype (pages 83 and 86) is the primary design reference.

## Cool-roof calculation

The slider is **0–50% of eligible roof area**, not 0–50% of the entire grid cell. A separately verified `eligible_roof_area_m2` is required; `roof_fraction_of_grid = eligible_roof_area_m2 / 900`. Then:

`retrofit_fraction = slider_percent / 100`

`retrofit_area_m2 = eligible_roof_area_m2 × retrofit_fraction`

`albedo_new = albedo_base + roof_fraction_of_grid × retrofit_fraction × (albedo_cool - albedo_existing_roof)`

Only the roof share contributes to the cell-average albedo change. The non-roof part stays fixed. The code rejects fractions/areas outside the 30 m cell, eligible area above a mapped `roof_fraction` when that feature exists, and any resulting albedo above 1. **The trained XGBoost model must include a real `albedo` feature.** If Step 12 omitted albedo, the roof simulator stops rather than inventing a replacement feature; obtaining a defensible albedo layer and retraining the LST model is required.

Separate measured roof albedos are not currently available. [`backend/app/simulation/config.py`](../backend/app/simulation/config.py) therefore declares **illustrative MVP assumptions** of `albedo_existing_roof = 0.20` and `albedo_cool = 0.65`. These are not Pune measurements or guaranteed retrofit outcomes. The [U.S. Department of Energy cool-roof guide](https://www1.eere.energy.gov/buildings/publications/pdfs/corporate/coolroofguide.pdf) discusses a 0.65 initial reflectance threshold for some low-slope products; product choice, aging, dust, and local roof conditions still require measurement or documentation. Change assumptions with the environment variables `GREENPULSE_EXISTING_ROOF_ALBEDO` and `GREENPULSE_COOL_ROOF_ALBEDO` before starting the backend.

The optional NDBI surrogate is `ndbi_new = ndbi_base - k_roof × retrofit_fraction`. `k_roof` is an **empirical calibration parameter, not a physical law**. It defaults to **0**, so NDBI and focal NDBI features remain unchanged. If a locally justified value is later available, configure `GREENPULSE_ROOF_NDBI_K`; the single-cell focal means then change by the local NDBI difference divided by their configured valid-cell counts. The default zero avoids asserting an unsupported spectral change from roof painting.

The simulator returns baseline LST, scenario LST, `ΔLST = scenario − baseline`, `cooling = max(0, baseline − scenario)`, changed albedo, optional changed NDBI, retrofit area, all changed features, and assumptions. Positive ΔLST means the model predicts warming and cooling is zero. These are **model what-if estimates**, not observed or causal cooling. LST is not pedestrian air temperature.

## Combined tree canopy + cool roof

The two slider changes are applied to the **same** feature vector. XGBoost predicts that joint vector directly; the implementation does not add the two individual temperature deltas. It checks that verified plantable ground plus eligible roof area fits within one 900 m² cell under the MVP's non-overlap assumption. Interactions are only those the fitted model learned. They are not proof of a physical interaction or a validated intervention effect.

## API and dashboard

- `GET /api/simulation/cool-roof/config`: slider maximum and labelled roof assumptions.
- `POST /api/simulation/cool-roof`: `grid_id`, `retrofit_percent_of_eligible_roof`, `eligible_roof_area_m2`.
- `POST /api/simulation/combined`: those roof fields plus `canopy_increase_percentage_points` and `feasible_ground_area_m2`.
- Existing tree endpoint remains available. The [Scenario Simulator dashboard](../frontend/src/pages/ScenarioSimulator.jsx) selects tree-only, roof-only, or combined mode based on nonzero sliders.

The real model, model metadata, and ML Parquet table must match in dataset SHA-256, feature list, row count, CRS, resolution, and date range. Missing real artifacts return HTTP 503. Invalid or infeasible inputs return HTTP 422. The UI does not display synthetic or placeholder temperature results.

## Windows PowerShell verification

From the project root, install the model dependencies and start the backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-xgboost.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

In another PowerShell window, start the frontend:

```powershell
Set-Location frontend
npm run dev -- --host localhost --port 5173 --strictPort
```

Open `http://localhost:5173/scenario-simulator` and `http://127.0.0.1:8000/docs`. Expect two sliders: canopy 0–40 points and roof retrofit 0–50% of eligible roof. If the real LST model or grid dataset is absent, submitting a scenario shows an unavailable message with **no numeric temperatures**. When real artifacts and verified area assessments exist, use an actual grid ID and eligible areas to compare outputs. Recheck assumptions and area source before presenting any scenario publicly.

Run the focused tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_cool_roof -v
```

Expected: five passing tests with **ARTIFICIAL TEST FIXTURES** only. They verify the area-weighted formula, unchanged non-roof features, optional NDBI, XGBoost re-prediction, combined joint prediction, feasibility checks, and saved-model loading. Test predictions are not Pune climate results.
