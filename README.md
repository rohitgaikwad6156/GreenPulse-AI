# GreenPulse AI

An AI-powered Urban Climate Decision-Support System.

The repository implements the FastAPI, React, real-data intake, geospatial processing, spatial-validation, XGBoost, TreeSHAP, intervention-simulation, location-specific MILP, post-implementation validation, and optional research-layer workflows. The dashboard has eight working routes with explicit unavailable and connection-error states; it does not substitute demo values when production evidence is absent.

## Acceptance status

The final acceptance review is [documented here](docs/final_acceptance_review.md). Current status is intentionally split by evidence level:

| Readiness level | Status | Meaning |
| --- | --- | --- |
| Software-complete | **PASS** | The complete Python suite, frontend tests/build, API/OpenAPI checks, and desktop/mobile browser smoke checks pass. |
| Data-complete | **BLOCKED** | WorldCover, OSM roads, and WorldPop are verified locally, and an official PCMC municipal outline is staged. Verified PMC/PCMC ward boundaries, Landsat/Sentinel scenes, OSM green spaces, the peri-urban reference, and the assembled 30 m grid are still absent. |
| Model-validated | **BLOCKED** | No real ML grid or trained XGBoost model exists, so no Pune/PCMC spatial-CV metrics, SHAP values, calibrated Heat Hazard Score, or model-backed scenario results can be reported. |
| Field-validated | **BLOCKED** | No genuine pre/post intervention dataset or verified point-sensor dataset is locally available. |

Overall project outcome is **PARTIAL**: the software contract is executable and evidence-gated, but the required real-data, model-validation, and field-validation evidence is incomplete.

## Requirements

- Windows 11 with PowerShell
- Python 3.14 (the interpreter used for this initial setup)
- Node.js and npm
- Git

## Run the backend

From the `GreenPulse-AI` directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-shap.txt -r backend\requirements-optimizer.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/docs> for the FastAPI Swagger interface.

## Check the endpoints

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected JSON responses:

```json
{"message":"GreenPulse AI backend is running"}
{"status":"ok"}
```

Press `Ctrl+C` in the server window to stop it.

## Run the frontend

From the `GreenPulse-AI` directory in PowerShell:

```powershell
Copy-Item frontend\.env.example frontend\.env.development.local
Set-Location frontend
npm install
npm run dev -- --host localhost --port 5173 --strictPort
```

The copy command is optional: Vite also proxies `/api` to the local FastAPI server when no URL override is set. It sets `VITE_API_BASE_URL` to the local FastAPI address. Start FastAPI and Vite in separate PowerShell windows. Open <http://localhost:5173/> and expect `Backend Status: Healthy`. If FastAPI is stopped, the card shows `Backend Status: Connection Error`. Restart Vite after changing its environment file. The sidebar links to Overview, Heat Map, Root Cause Analysis, Scenario Simulator, Climate Action Optimizer, Validation, and Methodology. On a narrow screen, use the menu button in the top bar. Press `Ctrl+C` in the frontend server window to stop it.

To check the production build:

```powershell
npm run build
```

## Project layout

- `frontend/`: React, Vite, Tailwind CSS, and eight dashboard routes
- `backend/app/`: API, geospatial processing, ML, simulation, optimization, and validation modules
- `data/`: raw, processed, boundary, and clearly labeled demo data
- `models/`: trained model artifacts in later steps
- `notebooks/`, `scripts/`, `tests/`, `docs/`: future analysis and project materials

The Heat Map now displays dated NASA MODIS surface-temperature imagery by default, with an observation-date selector and approximately 1 km source resolution. This independent satellite view does not require a trained model. No locally processed 30 m temperature grid, model metric, or intervention outcome is currently available. Verified WorldCover, OSM roads, and WorldPop source files are present, plus a staged official PCMC outline that is not a ward layer and is not yet combined with PMC. The dashboard requests production artifacts and shows explicit unavailable states when they are absent.

## Real satellite pipelines

- [Real-data intake contract](docs/data_intake_contract.md): authoritative required/optional/future source inventory plus provenance, date, CRS, checksum, and local-file validation before processing.
- [Landsat LST processing](docs/landsat_lst_pipeline.md): measured March–May land surface temperature target on the PMC/PCMC 30 m grid.
- [Sentinel-2 NDVI/NDBI processing](docs/sentinel2_indices_pipeline.md): cloud-masked optical features aligned exactly to that LST grid. It requires the real LST raster, verified municipal boundary, and extracted L2A SAFE scenes.
- [WorldCover, OSM, and WorldPop morphology processing](docs/urban_morphology_pipeline.md): real tree-cover and built-up fractions, road density, nearest green-space distance, and population density on the same 30 m grid. It requires the real LST reference and source datasets.
- [Real-data acquisition status](docs/real_data_acquisition.md): reproducible official-source discovery/download commands, selected 2025 scenes, municipal-boundary importer, and exact credential/manual blockers.
- [Final ML-grid assembly](docs/ml_dataset_pipeline.md): validates all aligned rasters and official ward polygons, applies missing-data QA, computes focal optical context, and writes a real-data Parquet table with metadata and correlation diagnostics. It requires all upstream real layers.
- [Spatial block cross-validation](docs/spatial_cv_pipeline.md): assigns 5 km blocks to five held-out folds, checks block exclusivity, and creates a fold map from the real ML table. It trains no model.
- [Baseline LST regression](docs/baseline_models.md): compares Linear Regression, Decision Tree, and Random Forest using those same saved folds. Real metrics require the upstream Parquet and fold map.
- [Main XGBoost LST model](docs/xgboost_lst_pipeline.md): nested spatial Optuna tuning, held-out comparison with the three baselines, and final model persistence after real source data exist.
- [TreeSHAP LST explanations](docs/shap_explainability.md): sampled global importance, one-cell °C contributions, correlations, grouped summaries, and plot-ready JSON from a matching real saved model.
- [Root Cause Analysis UI](docs/root_cause_analysis_ui.md): grid-cell selection, local/global SHAP charts, additivity verification, functional groups, feature units, provenance, and explicit API failure states.
- [Heat Hazard Score](docs/heat_hazard_score.md): a separate 0–100 display index derived from predicted LST and documented observed summer LST references; no score-target training.
- [Tree canopy what-if simulator](docs/tree_canopy_simulator.md): a 0–40-point canopy slider that transforms model inputs, checks feasible area, and re-runs XGBoost for a clearly labelled LST scenario estimate.
- [Cool-roof and combined what-if simulator](docs/cool_roof_simulator.md): a 0–50% eligible-roof retrofit slider, area-weighted albedo change, optional calibrated NDBI surrogate, and a joint tree-plus-roof XGBoost re-prediction.
- [Approximate prediction uncertainty](docs/prediction_uncertainty.md): spatial-CV RMSE plus configurable intervention CV assumptions, an explicitly approximate cooling range, and MVP confidence/horizon labels on scenario results.
- [Discrete intervention catalog](docs/intervention_catalog.md): a legacy, explicitly labelled demo catalog kept outside the production optimizer path.
- [Location-specific MILP climate action optimizer](docs/milp_optimizer.md): versioned, checksum-verified evidence catalogs; loaded-location selection; integer blocks; financial, space, and intervention-capacity constraints; and explicit refusal to plan while real evidence is incomplete.
- [Complete FastAPI API](docs/fastapi_api.md): validated frontend-facing endpoints for real grids, wards, model metrics, prediction, TreeSHAP, what-if simulation, MILP planning, DID, and methodology.
- [Interactive Pune / PCMC heat map](docs/interactive_heat_map.md): React Leaflet ward and viewport grid layers, real-model LST colors, selection details, and explicit no-data states.
- [Scenario Simulator UI](docs/scenario_simulator_ui.md): tree and cool-roof controls connected to `POST /api/simulate`, model result and uncertainty display, and selected-cell map comparison.
- [Climate Action Optimizer UI](docs/climate_action_optimizer_ui.md): budget and resource controls, optional normalized-benefit priorities, integer portfolio details, and cost-versus-cooling visualization when location-specific evidence is available.
- [Post-implementation validation](docs/post_implementation_validation.md): provenance-checked multi-pre-period DiD, control/spillover/spatial diagnostics, uncertainty, prediction residuals, versioned calibration proposals, and explicit human approval gates.
- [Optional research layers](docs/research_layers.md): provenance-preserving air-temperature/humidity/AQI points, explicit peak-summer scope, separate exposure and vulnerability layers, and a hard gate against unsupported composite risk scores.
- [Full system testing](docs/full_system_testing.md): automated Python and frontend build checks plus a manual map-to-validation checklist, with explicit synthetic-fixture and real-data gates.
- [Deploy on Render and Vercel](docs/deployment_vercel_render.md): project-specific dashboard settings, cloud environment variables, routing, verification, and current data limitations.

No production pipeline substitutes synthetic climate values for missing source data. Automated tests use only temporary, labelled artificial fixtures; the separately labelled demo files are never a production API fallback.
