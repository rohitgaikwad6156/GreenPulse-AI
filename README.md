# GreenPulse AI

An AI-powered Urban Climate Decision-Support System.

The project contains a basic FastAPI backend, a React dashboard shell, a clearly labelled synthetic demo dataset, feature-engineering utilities, local real-data Landsat/Sentinel-2/urban-morphology pipelines, and a validated ML-table assembler. The dashboard has seven working routes and placeholder states. No real satellite layers, ML results, simulation outputs, or environmental measurements are currently present in this workspace.

## Requirements

- Windows 11 with PowerShell
- Python 3.14 (the interpreter used for this initial setup)
- Node.js and npm
- Git

## Run the backend

From the `GreenPulse-AI` directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
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

The copy command is needed only for first-time setup. It sets `VITE_API_BASE_URL` to the local FastAPI address. Start FastAPI and Vite in separate PowerShell windows. Open <http://localhost:5173/> and expect `Backend Status: Healthy`. If FastAPI is stopped, the card shows `Backend Status: Connection Error`. Restart Vite after changing its environment file. The sidebar links to Overview, Heat Map, Root Cause Analysis, Scenario Simulator, Climate Action Optimizer, Validation, and Methodology. On a narrow screen, use the menu button in the top bar. Press `Ctrl+C` in the frontend server window to stop it.

To check the production build:

```powershell
npm run build
```

## Project layout

- `frontend/`: React, Vite, Tailwind CSS, and seven dashboard routes
- `backend/app/`: API, geospatial processing, ML, simulation, optimization, and validation modules
- `data/`: raw, processed, boundary, and clearly labeled demo data
- `models/`: trained model artifacts in later steps
- `notebooks/`, `scripts/`, `tests/`, `docs/`: future analysis and project materials

No measured temperature, model metric, or intervention outcome is included in this shell. The dashboard requests backend data and shows explicit unavailable states when real artifacts are absent.

## Real satellite pipelines

- [Landsat LST processing](docs/landsat_lst_pipeline.md): measured March–May land surface temperature target on the PMC/PCMC 30 m grid.
- [Sentinel-2 NDVI/NDBI processing](docs/sentinel2_indices_pipeline.md): cloud-masked optical features aligned exactly to that LST grid. It requires the real LST raster, verified municipal boundary, and extracted L2A SAFE scenes.
- [WorldCover, OSM, and WorldPop morphology processing](docs/urban_morphology_pipeline.md): real tree-cover and built-up fractions, road density, nearest green-space distance, and population density on the same 30 m grid. It requires the real LST reference and source datasets.
- [Final ML-grid assembly](docs/ml_dataset_pipeline.md): validates all aligned rasters and official ward polygons, applies missing-data QA, computes focal optical context, and writes a real-data Parquet table with metadata and correlation diagnostics. It requires all upstream real layers.
- [Spatial block cross-validation](docs/spatial_cv_pipeline.md): assigns 5 km blocks to five held-out folds, checks block exclusivity, and creates a fold map from the real ML table. It trains no model.
- [Baseline LST regression](docs/baseline_models.md): compares Linear Regression, Decision Tree, and Random Forest using those same saved folds. Real metrics require the upstream Parquet and fold map.
- [Main XGBoost LST model](docs/xgboost_lst_pipeline.md): nested spatial Optuna tuning, held-out comparison with the three baselines, and final model persistence after real source data exist.
- [TreeSHAP LST explanations](docs/shap_explainability.md): sampled global importance, one-cell °C contributions, correlations, grouped summaries, and plot-ready JSON from a matching real saved model.
- [Heat Hazard Score](docs/heat_hazard_score.md): a separate 0–100 display index derived from predicted LST and documented observed summer LST references; no score-target training.
- [Tree canopy what-if simulator](docs/tree_canopy_simulator.md): a 0–40-point canopy slider that transforms model inputs, checks feasible area, and re-runs XGBoost for a clearly labelled LST scenario estimate.
- [Cool-roof and combined what-if simulator](docs/cool_roof_simulator.md): a 0–50% eligible-roof retrofit slider, area-weighted albedo change, optional calibrated NDBI surrogate, and a joint tree-plus-roof XGBoost re-prediction.
- [Approximate prediction uncertainty](docs/prediction_uncertainty.md): spatial-CV RMSE plus configurable intervention CV assumptions, an explicitly approximate cooling range, and MVP confidence/horizon labels on scenario results.
- [Discrete intervention catalog](docs/intervention_catalog.md): six integer-sized actions with openly labelled demo costs and unknown cooling/feasibility fields, ready for later evidence and MILP work.
- [MILP climate action optimizer](docs/milp_optimizer.md): integer intervention blocks with normalized benefits, configurable objective weights, four resource limits, and explicit refusal to plan while cooling or capacity evidence is missing.
- [Complete FastAPI API](docs/fastapi_api.md): validated frontend-facing endpoints for real grids, wards, model metrics, prediction, TreeSHAP, what-if simulation, MILP planning, DID, and methodology.
- [Interactive Pune / PCMC heat map](docs/interactive_heat_map.md): React Leaflet ward and viewport grid layers, real-model LST colors, selection details, and explicit no-data states.
- [Scenario Simulator UI](docs/scenario_simulator_ui.md): tree and cool-roof controls connected to `POST /api/simulate`, model result and uncertainty display, and selected-cell map comparison.
- [Climate Action Optimizer UI](docs/climate_action_optimizer_ui.md): budget and resource controls, optional normalized-benefit priorities, integer portfolio details, and cost-versus-cooling visualization when location-specific evidence is available.
- [Post-implementation validation](docs/post_implementation_validation.md): paired treated/control LST DiD, optional NDVI change, treated-cell prediction residuals, and an explicitly synthetic demo workflow.
- [Full system testing](docs/full_system_testing.md): automated Python and frontend build checks plus a manual map-to-validation checklist, with explicit synthetic-fixture and real-data gates.
- [Deploy on Render and Vercel](docs/deployment_vercel_render.md): project-specific dashboard settings, cloud environment variables, routing, verification, and current data limitations.

Neither pipeline substitutes synthetic climate values for missing source data. Their tests use only temporary, labelled artificial fixtures.
