# Final GreenPulse AI acceptance review

Review date: **2026-09-21**  
Research basis: `D:\green plus ai\GreenPulse_AI_Research_Symbols_Cleaned.pdf` and the repository documentation linked from `README.md`.

## Decision

| Readiness level | Status | Acceptance finding |
| --- | --- | --- |
| Software-complete | **PASS** | Processing, validation, model, explainability, simulation, optimizer, and UI contracts are implemented and covered by artificial test fixtures. The API and dashboard fail closed when real artifacts are absent. |
| Data-complete | **BLOCKED** | Only ESA WorldCover, OSM roads, and WorldPop pass the production source-manifest gate. An official PCMC outline is staged but is not a ward layer and is not a combined PMC/PCMC boundary. |
| Model-validated | **BLOCKED** | The real 30 m ML Parquet table and trained XGBoost artifact do not exist, so no real spatial-CV metrics, Heat Hazard calibration, SHAP report, OOD assessment, or model-backed intervention estimate exists. |
| Field-validated | **BLOCKED** | No genuine pre/post treated/control intervention dataset and no verified point-sensor dataset are locally available. |

**Overall outcome: PARTIAL.** Automated success demonstrates software behavior only. It is not evidence that Pune/PCMC data, model performance, intervention effects, or field outcomes have been validated.

## Evidence matrix

Status meanings: **PASS** = accepted with current evidence; **PARTIAL** = implementation exists but only part of the real evidence is present; **BLOCKED** = a required real artifact or validation dataset is absent.

| Requirement | Implementation | Real artifact | Validation evidence | Status | Remaining blocker |
| --- | --- | --- | --- | --- | --- |
| All Python tests | Backend/geospatial/ML/SHAP/simulation/MILP/validation/research modules and API tests | No real climate result is needed for software tests | `scripts/test_full_system.ps1`: **126 passed, 36 warnings, 24 subtests passed** | **PASS** | Warnings are dependency deprecations, not failed checks. Real-result acceptance remains separately blocked. |
| Frontend production build | React/Vite dashboard with eight routes | Production bundle in `frontend/dist/` | Frontend unit tests: **8 passed**; `npm run build`: **PASS**, 2,561 modules transformed | **PASS** | None for compilation; live data views remain evidence-gated. |
| API health and OpenAPI schema | FastAPI application and Pydantic request/response models | Runtime API only | `GET /api/health` = 200 `{"status":"ok"}`; `/openapi.json` = 200 with 30 paths and all required MVP endpoints | **PASS** | None for API availability. |
| Authoritative source intake | JSON schema, manifest validator, acquisition/import scripts, checksum and provenance gates | Verified: WorldCover, OSM roads, WorldPop. Staged only: official PCMC outline | `validate_data_manifest.py` identifies every missing/invalid field and reports exactly three verified required inputs | **PARTIAL** | Obtain and verify combined PMC/PCMC municipal and ward boundaries, Landsat 8/9 L2 scenes, Sentinel-2 L2A scenes, OSM green spaces, and same-season peri-urban LST. |
| Real ward and 30 m map layers | Ward/grid APIs and Leaflet map use production artifacts only | Required `pmc_pcmc_wards.geojson`, `greenpulse_ml_grid.parquet`, and model are absent | `/api/wards` and `/api/grid` return actionable 503 errors; browser map shows “Climate layers not available yet” with only the OSM basemap | **BLOCKED** | Verified ward GIS plus all aligned March–May 30 m source layers and trained model. |
| QA-masked real 30 m ML dataset | Landsat LST, Sentinel indices, morphology, ward assignment, focal features, QA/coverage/correlation/VIF checks | No `data/processed/greenpulse_ml_grid.parquet` or `metadata.json` | Builder stops at missing `lst_pune_30m.tif`; artificial integration fixtures cover CRS, alignment, ranges, duplicates, ambiguity, missingness, and diagnostics | **BLOCKED** | Complete the validated real-source manifest and run the documented pipelines in order. |
| Prediction and observed-LST labeling | API separates `observed_lst_c` from `predicted_lst_c`; UI calls predicted layer “Model-estimated surface temperature” | No real observations or predictions are served | API schema/tests and rendered Heat Map labels verified; 503 replaces absent values | **PASS** | Real values remain unavailable until grid/model creation. |
| Heat Hazard Score calibration | Post-inference LST normalization using documented same-season peri-urban median and municipal 95th percentile; score is not a target | No peri-urban reference or model metadata calibration | Calibration command stops before output because the real model/metadata are absent; UI leaves score unavailable | **BLOCKED** | Same-season, non-overlapping peri-urban observed-LST table/provenance plus matching real municipal dataset/model. |
| SHAP reconstruction and Root Cause page | Local signed °C contributions, baseline/reconstruction, global mean absolute ranking, groups, raw values/units, provenance, redundancy and causality warnings | No real model/grid/SHAP output | Additivity, correlation, stale-model, grouping and API tests pass on labelled artificial fixtures; browser query/input route renders an actionable 503 state | **BLOCKED** | Train the matching real XGBoost model, then generate and review real TreeSHAP outputs. |
| Tree, roof, and combined simulations | Joint XGBoost re-prediction, zero-intervention identity, capacity/source distinctions, evidence status and horizon panels | No matching real model/grid or verified per-cell capacity | Boundary, infeasibility, metadata mismatch, OOD, zero and combined scenario tests pass; `/api/simulate` returns 503 rather than a fabricated result | **BLOCKED** | Real model/grid, defensible intervention transformations, and verified roof/ground capacity. |
| OOD and uncertainty behavior | Training ranges in model metadata, scenario range checks, approximate uncertainty explicitly distinguished from calibrated coverage | No real training distribution or held-out spatial RMSE | Artificial fixture tests reject stale/mismatched metadata and missing RMSE; UI states “calibration required” and does not claim observed or causal cooling | **BLOCKED** | Real model metadata and empirical coverage validation if an interval is ever to be called coverage-calibrated. |
| Location-specific MILP constraints and provenance | Versioned location catalog; checksum, expiry, location/model identity gates; integer budget, maintenance, ground, roof, and capacity constraints; overlap warning | Production catalog exists with zero enabled locations; legacy demo CSV is excluded | Solver/API/frontend evidence-gate tests pass; `/api/optimizer/locations` returns an empty list with exact blockers; optimizer control is disabled | **BLOCKED** | At least one named area with verified spatial capacity, traceable capital/maintenance costs, co-benefit basis, and model-supported marginal benefit. |
| Validation provenance and statistical warnings | Checksum-verified imports, multi-pre-period DiD, season/overpass/QA/grid matching, parallel-trend/control/spillover/spatial warnings, limited CI, residuals, approval gate | No genuine intervention dataset | Workflow tests cover mismatch, incomplete pairs, duplicates, failed trends, contaminated controls and artificial fixtures; API reports `validation_status: BLOCKED` | **BLOCKED** | Genuine comparable pre/post treated/control LST observations and explicit review/approval of any calibration proposal. |
| Responsive UI, accessibility and failure states | Responsive shell, labelled controls/charts, keyboard-usable mobile navigation, loading/no-data/404/422/503/connection handling | Runtime views use current artifact availability | Desktop and 390×844 browser smoke checks passed; menu exposes accessible controls; verified 404, 422, 503 and backend connection-error states; no framework overlay or browser error | **PASS** | Data-backed chart rendering still needs a final live smoke test after real artifacts exist. |
| Point sensors, exposure and vulnerability separation | Provenance-preserving point ingestion, proximity/time-offset context, peak-summer enforcement, separate exposure/vulnerability status, no arbitrary composite risk | WorldPop source is verified; processed exposure, social vulnerability and sensors are absent | API/UI show sensor `missing`, exposure `source_verified_processing_blocked`, vulnerability `missing`, and `composite_risk_available: false` | **PARTIAL** | Real grid/boundaries for exposure processing; defensible social indicators; verified point observations for optional sensor context. |
| No demo data presented as real evidence | Production API paths never fall back to `data/demo`; catalog and validation demo are explicitly labelled | Demo files remain segregated and labelled | Source/code search plus API/browser smoke found no demo values in real map/model/scenario/optimizer responses | **PASS** | Maintain the production/demo separation when real data are imported. |
| No unsupported PDF metrics copied | Metrics are loaded only from saved real model metadata; UI renders unavailable markers without a model | No project model metrics exist | Repository search found none of the PDF’s illustrative model-performance, demo-temperature, score, or “real-world fidelity” values in production code/UI/data outside explicitly labelled demo material | **PASS** | Report only metrics generated from the future real saved fold artifacts. |

## Research-PDF guardrails confirmed

- The model target is continuous Landsat LST in °C, not an arbitrary risk score or 2 m air temperature.
- The Heat Hazard Score is a post-inference relative LST display index and is explicitly not health risk, probability, exposure, or vulnerability.
- The 30 m grid is an analysis grid; it does not claim to create native 30 m thermal detail.
- TreeSHAP is additive model attribution, not causation; correlated predictors produce redundancy warnings.
- Scenario outputs are model re-predictions under changed inputs, not observed or causal cooling.
- MILP quantities remain integer and optimal only under the supplied objective, evidence, and hard constraints; summed marginal cooling is a linear planning proxy.
- Difference-in-Differences remains descriptive without credible controls, parallel trends, spillover review, and genuine observations.
- CFD, 3D canyon physics, tree-species growth, and continuous IoT retraining remain future scope.

The PDF includes illustrative hackathon values and literature benchmarks. They were treated as examples, not as GreenPulse results.

## Commands and observed results

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_full_system.ps1
# 126 Python tests passed; 8 frontend tests passed; Vite production build passed.

.\.venv\Scripts\python.exe scripts\validate_data_manifest.py --manifest data\source_manifest.json
# FAIL as designed: three verified inputs; precise blockers for every absent required source.

.\.venv\Scripts\python.exe scripts\build_ml_dataset.py
# exit 2: required aligned lst_c raster is missing.

.\.venv\Scripts\python.exe scripts\train_xgboost_lst.py --trials 1 --jobs 1
# exit 2: real ML Parquet dataset is missing.

.\.venv\Scripts\python.exe scripts\calibrate_heat_hazard.py
# exit 2: real trained model and metadata are required.

.\.venv\Scripts\python.exe scripts\build_shap_explanations.py --grid-id acceptance-missing
# exit 2: real trained model and metadata are required.
```

The browser smoke test used the local FastAPI and Vite servers at 1280×720 and 390×844. It checked Overview, Heat Map, Root Cause Analysis, Scenario Simulator, Climate Action Optimizer, Validation, Research Layers, mobile navigation, no-data content, and the disconnected-backend state.

## Smallest actions required to advance acceptance

1. Supply or authorize access to an official, redistributable PMC ward GIS layer and a verified PCMC ward GIS layer/current ward scheme; import them with the existing boundary tooling.
2. Supply the required Landsat 8/9 Collection 2 Level-2 and Sentinel-2 L2A scene downloads/credentials identified in `docs/real_data_acquisition.md`, plus the missing OSM green-space extract.
3. Build and validate the real 30 m grid and peri-urban reference, train spatial-CV models, then regenerate calibration, SHAP, OOD, uncertainty, and scenario evidence.
4. Provide at least one audited location-specific intervention catalog and one genuine comparable pre/post treated/control dataset before optimizer or field-validation acceptance.
