# Step 29 — full system testing

GreenPulse AI is an AI-powered Urban Climate Decision-Support System. The
automated tests use **ARTIFICIAL / SYNTHETIC TEST DATA** in temporary folders.
They do not report Pune/PCMC observations, real model accuracy, or measured
intervention cooling.

## Run automated checks on Windows 11

From the `GreenPulse-AI` folder in PowerShell, first install the test-only
dependencies in the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-test.txt
```

Then run both the Python suite and frontend production build:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_full_system.ps1
```

Expected final message: `GreenPulse automated checks passed: Python tests and frontend build.`
The script exits with an error if either command fails. The build checks that
the React application compiles; the manual checklist below checks interaction
and presentation.

## Automated coverage

| Scientific or product behavior | Test file |
| --- | --- |
| NDVI, NDBI, canopy/built fraction, road density and invalid inputs | `tests/test_features.py` |
| Sentinel-2 alignment and optical QA | `tests/test_sentinel2_indices.py` |
| Heat Hazard Score and documented references | `tests/test_heat_hazard.py` |
| Saved XGBoost artifact and matching grid metadata | `tests/test_xgboost_lst.py`, `tests/test_system_integration.py` |
| Zero, tree, roof, and combined XGBoost scenarios | `tests/test_tree_canopy.py`, `tests/test_cool_roof.py`, `tests/test_system_integration.py` |
| Approximate uncertainty and missing spatial RMSE rejection | `tests/test_uncertainty.py`, `tests/test_system_integration.py` |
| Integer MILP portfolio, four limits, invalid actions | `tests/test_milp_optimizer.py`, `tests/test_system_integration.py` |
| Paired treated/control DiD, NDVI, residual MAE/RMSE | `tests/test_validation_did.py`, `tests/test_system_integration.py` |
| HTTP endpoints, schema validation, map selection and missing artifact errors | `tests/test_api.py`, `tests/test_heat_map_api.py`, `tests/test_system_integration.py` |

The HTTP integration fixture trains an XGBoost model on synthetic rows,
computes a **synthetic held-out five-fold spatial RMSE** for its metadata, and
keeps all files in a temporary directory. Its values are only arithmetic and
software checks. It asserts that a zero intervention leaves scenario LST equal
to baseline LST, while nonzero scenarios re-predict with changed features.
The optimizer test checks the returned totals against budget, maintenance,
ground, and roof limits, and checks nonnegative integer action quantities.

## Manual end-to-end checklist

Start FastAPI and Vite as described in the project README. Open the dashboard
at `http://localhost:5173/` and the API schema at `http://127.0.0.1:8000/docs`.
Record the date, dataset version, model version, ward boundary source, and
whether each result uses real or demo inputs. Do not treat an unavailable
state as a successful climate result.

- [ ] **Map:** Open Heat Map. Confirm a clear loading state and then verified
  PMC/PCMC ward outlines and a legend, or a clear data-unavailable message.
- [ ] **Click ward:** Select a ward. Check its name, cell count, predicted LST
  in °C, confidence status, and explanation scope. A missing reference should
  leave Heat Hazard Score unavailable.
- [ ] **Prediction:** Select a grid cell and compare the displayed prediction
  with `POST /api/predict` for the same `grid_id`. Check that observed LST and
  predicted LST are labelled separately.
- [ ] **SHAP:** Inspect the map detail's top factors. For the full local
  breakdown, call `POST /api/explain` in Swagger with the selected `grid_id`.
  Check the baseline plus local °C contributions reconstructs the prediction.
  Confirm the result describes attribution, not causation. The dedicated Root
  Cause Analysis page is still a placeholder.
- [ ] **Simulation:** Open Scenario Simulator for that cell. Set tree and roof
  sliders to zero; scenario LST should match baseline. Try each intervention
  and their combination. Inspect signed ΔLST, nonnegative cooling magnitude,
  90% approximate range, assumptions, and map comparison. Do not present
  modeled cooling as measured cooling.
- [ ] **Optimization:** Enter the verified ward location, budget, yearly
  maintenance cap, available ground, and roof area. If benefits/capacities are
  incomplete, check for an explicit unavailable state. With a completed,
  location-specific catalog, check every displayed quantity is an integer,
  all four limits hold, unused budget is nonnegative, and budget changes cause
  a new solve. Treat total cooling as a planning proxy.
- [ ] **Validation:** Open Validation. If using the bundled example, confirm
  the **DEMO VALIDATION SCENARIO** label. Enter paired treated/control pre/post
  observations only when their provenance is known. Verify DiD arithmetic,
  ΔNDVI, and prediction residuals. Check the page states the causal limits.
- [ ] **Methodology:** Confirm formulas, source links, spatial folds, and all
  limitations are visible. Check artifact status reflects the installed files.
- [ ] **Failure states:** Stop the backend, revisit a data page, and confirm a
  connection error. Restart it and try an unknown grid ID and invalid negative
  intervention; expect clear 404/422 or 503 responses, never fabricated data.
- [ ] **Responsive layout:** Repeat the navigation and one scenario on a
  narrow browser window; verify controls, charts, and map remain usable.

### Current project gate

At this step, the real ML grid, trained Pune/PCMC model, and calibrated
location-specific intervention benefits are not available. The automated
integration path passes on labelled synthetic fixtures. A live municipal
end-to-end acceptance run remains pending until verified source artifacts and
post-implementation observations exist. The Root Cause Analysis page is wired
to `POST /api/explain` and reports explicit unavailable states until the real
ML grid and matching model are present.

LST is not 2 m air temperature. TreeSHAP does not prove causation. DiD needs
parallel-trends and confounding review. MILP optimality holds only under the
entered objective, assumptions, and constraints.
