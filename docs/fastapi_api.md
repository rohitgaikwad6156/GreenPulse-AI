# Step 23 — GreenPulse FastAPI API

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** The API serves saved real-data artifacts and documented planning assumptions. The `data/demo` CSV is never used as a fallback. OpenAPI/Swagger is generated from Pydantic schemas at `/docs`.

## Start on Windows 11

Run these in PowerShell from `GreenPulse-AI`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-shap.txt
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-optimizer.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

The first command installs the existing real-data/ML stack (including FastAPI, Parquet, XGBoost, SHAP and Optuna). The second makes SciPy's MILP dependency explicit. The third starts the server. Open `http://127.0.0.1:8000/docs`; all eleven requested paths are listed. Stop with `Ctrl+C`.

## Endpoint contract

| Endpoint | 200 response | Current state with missing real artifacts |
| --- | --- | --- |
| `GET /api/health` | `{ "status": "ok" }` | 200 |
| `GET /api/model/metrics` | saved spatial CV metrics for LST °C | 503 until trained model and metadata exist |
| `GET /api/wards` | real ward IDs, names and 30 m cell counts | 503 until ML Parquet exists |
| `GET /api/grid?limit=100&offset=0&ward_id=...` | paged real cells, observed LST, model features | 503 until ML Parquet exists; 404 for unknown ward |
| `GET /api/ward/{ward_id}` | count and observed LST mean/min/max | 503 until ML Parquet exists; 404 for unknown ward |
| `POST /api/predict` | XGBoost LST prediction for saved `grid_id` | 503 until matching trained model and grid exist |
| `POST /api/explain` | local and global TreeSHAP report | 503 until matching trained model and grid exist |
| `POST /api/simulate` | tree, roof or joint what-if result with uncertainty | 503 until matching model/grid/spatial RMSE exist |
| `POST /api/optimize` | discrete MILP plan | 503 until location-specific benefit and capacity fields exist |
| `POST /api/validation/did` | descriptive paired-cell LST DiD, optional NDVI change and prediction residuals | 200 for valid input; provenance is not verified |
| `GET /api/validation/demo` | explicitly labelled synthetic validation fixture | 200; DEMO / SYNTHETIC DATA only |
| `GET /api/methodology` | pipeline, scientific limits, artifact-presence flags | 200 |

All POST bodies and successful responses have Pydantic schemas visible in Swagger. Invalid field values return HTTP 422, missing real artifacts return HTTP 503, and unknown real IDs return HTTP 404. Server errors are not converted to invented observations or plan outputs.

### Request shapes

- `/api/predict`: `{"grid_id":"<real saved grid ID>"}`.
- `/api/explain`: `{"grid_id":"<real saved grid ID>","sample_size":2000}`. Sample size is 2–5000. SHAP values are model contributions in °C; they do not prove causation.
- `/api/simulate`: `grid_id`, `scenario_type` (`tree_canopy`, `cool_roof`, or `combined`), and fields for the selected intervention. Trees use `canopy_increase_percentage_points` (0–40) and `feasible_ground_area_m2` (0–900). Roofs use `retrofit_fraction` (0–1) and `eligible_roof_area_m2` (0–900). The present cool-roof MVP implementation additionally limits retrofit to 0.5 of eligible roof. A combined request needs all four fields, and total stated ground plus roof area must fit in one 900 m² cell.
- `/api/optimize`: `location`, `budget_inr`, `maintenance_cap_inr_per_year`, `available_ground_m2`, `available_roof_m2`. ₹10 lakh is ₹1,000,000. The generous 100,000,000 m² API area ceiling is an input guard, **not** proof that a ward has that much eligible space. The catalog must match the requested location.
- `/api/validation/did`: `intervention`, `pre_period`, `post_period`, and `observations`. Each observation has `grid_id`, `group` (`treated` or `control`), `period` (`pre` or `post`), observed `lst_c`, and optional `ndvi`. Each cell needs both periods and one group. Optional `predictions` supply one predicted ΔLST per treated cell; the response then includes control-adjusted residuals, MAE, and RMSE. `source_note` and `scenario_label` record input provenance without claiming verification.

### Basic smoke checks

With the server running in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/methodology
.\.venv\Scripts\python.exe -m unittest tests.test_api -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Expect health status `ok`, methodology with artifact flags, and passing tests. In Swagger, try `/api/wards` now: 503 and a missing real ML grid message are expected. Try a negative budget or retrofit fraction above 1: 422 is expected. Once the actual Parquet/model/catalog exist, re-run the same endpoints against them. The API tests use a temporary **ARTIFICIAL / SYNTHETIC** grid fixture; they do not create Pune temperature results.

## Difference-in-Differences and interpretation

The DID route calculates `(treated post − treated pre) − (control post − control pre)` in LST °C from user-supplied values. The endpoint cannot verify observation provenance or establish causal effects. A defensible study needs real pre/post observations, comparable season and satellite overpass conditions, a plausible parallel-trends argument, attention to confounding and spillover, and uncertainty analysis. LST remains distinct from pedestrian air temperature.

## Common errors

- `503 Required real ML grid...`: complete the real-data pipelines; the demo CSV is intentionally ignored.
- `503 ...predicted_cooling_benefit_c`: obtain/calibrate intervention benefits and verified site capacities before optimization.
- `422`: inspect the Pydantic field message; canopy change must be nonnegative, roof fraction 0–1, and budgets nonnegative.
- `404`: the requested ward or grid ID is absent from the saved real table.
- `ModuleNotFoundError`: use `.venv\Scripts\python.exe` and install both requirement files above.

Legacy Step 18–22 scenario routes remain available for compatibility. New dashboard integrations should use `/api/predict`, `/api/explain`, `/api/simulate`, and `/api/optimize`.
