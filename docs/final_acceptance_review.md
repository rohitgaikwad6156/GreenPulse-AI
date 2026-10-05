# Final GreenPulse AI acceptance review

Status reviewed: **2026-10-05**

Status basis: current `main` at `c6f5756`, source manifest, local files, audit JSON, and current source-gating code. Earlier research-PDF guardrails are retained; old documentation is not evidence of current data readiness.

## Decision

| Readiness level | Status | Acceptance finding |
| --- | --- | --- |
| Software-complete | **PASS** | Processing, validation, model, explainability, simulation, optimizer, and UI contracts are implemented and covered by artificial test fixtures. The API and dashboard fail closed when real artifacts are absent. |
| Data-complete | **BLOCKED** | Landsat, ESA WorldCover, OSM roads and WorldPop pass local manifest validation. Sentinel is absent; PCMC outline is staged but official PMC outline and verified combined boundary remain pending. Broader acceptance also lacks OSM green-space and peri-urban evidence; ward GIS remains a reporting dependency. |
| Model-validated | **BLOCKED** | No accepted real 30 m ML table or real trained XGBoost model exists; legacy demo artifacts on disk are not real evidence, so no real spatial-CV metrics, Heat Hazard calibration, SHAP report, OOD assessment, or model-backed intervention estimate exists. |
| Field-validated | **BLOCKED** | No genuine pre/post treated/control intervention dataset and no verified point-sensor dataset are locally available. |

**Overall outcome: PARTIAL.** Automated success demonstrates software behavior only. It is not evidence that Pune/PCMC data, model performance, intervention effects, or field outcomes have been validated.

## Evidence matrix

Current verification reran focused source/preflight tests and frontend tests/build. The full Python suite and historical endpoint checks were not rerun for this documentation task; unchanged software findings below retain their earlier evidence. Recent browser verification is recorded in [the UI review](ui_design_review.md).

Status meanings: **PASS** = accepted with current evidence; **PARTIAL** = implementation exists but only part of the real evidence is present; **BLOCKED** = a required real artifact or validation dataset is absent.

| Requirement | Implementation | Real artifact | Validation evidence | Status | Remaining blocker |
| --- | --- | --- | --- | --- | --- |
| Python test evidence | Backend/geospatial/ML/SHAP/simulation/MILP/validation/research modules and API tests | No production climate result required | Current focused source/preflight suite: **47 passed** (102 Rasterio dependency warnings); full suite not rerun | **PARTIAL** | Full-suite PASS belongs to the earlier software review, not this focused rerun. |
| Frontend production build | React/Vite dashboard with eight routes | Production bundle in `frontend/dist/` | Current frontend tests: **17 passed**; `npm --prefix frontend run build`: **PASS** | **PASS** | Compilation is verified; real data views remain evidence-gated. |
| API health and OpenAPI schema | FastAPI application and request/response models | Runtime API only | Prior acceptance recorded healthy endpoints and schema checks; current direct `methodology()` reports real grid/model unavailable | **PASS** | Historical endpoint acceptance retained; endpoint/schema counts not reasserted as a fresh run. |
| Authoritative source intake | Manifest validator, acquisition/import scripts and source audits | Verified: Landsat, WorldCover, OSM roads, WorldPop. Staged: official PCMC outline | Full manifest confirms four verified sources; Landsat source/processing/extreme audits each pass 9/9; Sentinel audit finds 0/6 SAFE products | **PARTIAL** | First heat map: combined municipal boundary and Sentinel. Broader intake: OSM green spaces and peri-urban reference. Ward GIS separately supports reporting. |
| Real ward and 30 m map layers | Ward/grid APIs and Leaflet map use production evidence; optional dated NASA imagery is separate | Combined boundary and real grid/model unavailable; ward GIS also pending | Current heat-map preflight accepts Landsat, WorldCover and roads, but rejects combined boundary and Sentinel; backend reports real grid/model unavailable | **BLOCKED** | Official PMC outline plus verified combined boundary and Sentinel for cells; verified ward GIS only for ward reporting/UI. |
| QA-masked real 30 m ML dataset | Landsat QA/calibration, Sentinel indices, morphology, optional ward assignment, alignment/coverage checks | Existing grid metadata says `DEMO / SYNTHETIC DATA`; no accepted real grid | Nine real Landsat scenes decode and calibrate in the non-production audit; check-only build stops at boundary/Sentinel source gate | **BLOCKED** | Resolve the two first-profile source blockers and run the real pipeline. OSM green spaces, WorldPop, peri-urban calibration and ward GIS are not first-profile prerequisites. |
| Prediction and observed-LST labeling | API separates `observed_lst_c` from `predicted_lst_c`; UI labels model predictions separately from observed satellite imagery | No real observations or predictions are served | API schema/tests and rendered Heat Map labels verified; 503 replaces absent values | **PASS** | Real values remain unavailable until grid/model creation. |
| Heat Hazard Score calibration | Post-inference LST normalization using documented same-season peri-urban median and municipal 95th percentile; score is not a target | No peri-urban reference or model metadata calibration | Real grid/model evidence is unavailable; no calibration command was rerun in this documentation review | **BLOCKED** | Same-season, non-overlapping peri-urban observed-LST table/provenance plus matching real municipal dataset/model. |
| SHAP reconstruction and Root Cause page | Local signed °C contributions, baseline/reconstruction, global mean absolute ranking, groups, raw values/units, provenance, redundancy and causality warnings | No accepted real model/grid/SHAP output; legacy outputs are not evidence | Additivity, correlation, stale-model, grouping and API tests pass on labelled artificial fixtures; browser query/input route renders an actionable 503 state | **BLOCKED** | Train the matching real XGBoost model, then generate and review real TreeSHAP outputs. |
| Tree, roof, and combined simulations | Joint XGBoost re-prediction, zero-intervention identity, capacity/source distinctions, evidence status and horizon panels | No matching real model/grid or verified per-cell capacity | Boundary, infeasibility, metadata mismatch, OOD, zero and combined scenario tests pass; `/api/simulate` returns 503 rather than a fabricated result | **BLOCKED** | Real model/grid, defensible intervention transformations, and verified roof/ground capacity. |
| OOD and uncertainty behavior | Training ranges in model metadata, scenario range checks, approximate uncertainty explicitly distinguished from calibrated coverage | No real training distribution or held-out spatial RMSE | Artificial fixture tests reject stale/mismatched metadata and missing RMSE; UI states “calibration required” and does not claim observed or causal cooling | **BLOCKED** | Real model metadata and empirical coverage validation if an interval is ever to be called coverage-calibrated. |
| Location-specific MILP constraints and provenance | Versioned location catalog; checksum, expiry, location/model identity gates; integer budget, maintenance, ground, roof, and capacity constraints; overlap warning | Production catalog exists with zero enabled locations; legacy demo CSV is excluded | Solver/API/frontend evidence-gate tests pass; `/api/optimizer/locations` returns an empty list with exact blockers; optimizer control is disabled | **BLOCKED** | At least one named area with verified spatial capacity, traceable capital/maintenance costs, co-benefit basis, and model-supported marginal benefit. |
| Validation provenance and statistical warnings | Checksum-verified imports, multi-pre-period DiD, season/overpass/QA/grid matching, parallel-trend/control/spillover/spatial warnings, limited CI, residuals, approval gate | No genuine intervention dataset | Workflow tests cover mismatch, incomplete pairs, duplicates, failed trends, contaminated controls and artificial fixtures; API reports `validation_status: BLOCKED` | **BLOCKED** | Genuine comparable pre/post treated/control LST observations and explicit review/approval of any calibration proposal. |
| Responsive UI, accessibility and failure states | Grouped navigation, readiness panel, shared loading state, responsive map controls, modal keyboard navigation, reduced-motion support | Runtime views preserve actual artifact availability | [UI review](ui_design_review.md) at `c6f5756`: eight routes at desktop and 320 px, 390 px screenshots, focus/Escape/route navigation and connection recovery checks | **PASS** | No new browser audit in this documentation pass; data-backed charts still need real-artifact verification. |
| Point sensors, exposure and vulnerability separation | Provenance-preserving point ingestion, proximity/time-offset context, peak-summer enforcement, separate exposure/vulnerability status, no arbitrary composite risk | WorldPop source is verified; processed exposure, social vulnerability and sensors are absent | API/UI show sensor `missing`, exposure `source_verified_processing_blocked`, vulnerability `missing`, and `composite_risk_available: false` | **PARTIAL** | Real grid/boundaries for exposure processing; defensible social indicators; verified point observations for optional sensor context. |
| No demo data presented as real evidence | Production API paths never fall back to `data/demo`; catalog and validation demo are explicitly labelled | Demo files remain segregated and labelled | Source/code search plus API/browser smoke found no demo values in real map/model/scenario/optimizer responses | **PASS** | Maintain the production/demo separation when real data are imported. |
| No unsupported PDF metrics copied | Metrics are loaded only from saved real model metadata; UI renders unavailable markers without a model | No project model metrics exist | Repository search found none of the PDF’s illustrative model-performance, demo-temperature, score, or “real-world fidelity” values in production code/UI/data outside explicitly labelled demo material | **PASS** | Report only metrics generated from the future real saved fold artifacts. |

## Scientific guardrails retained

- Landsat full-scene audits are not Pune, PMC or PCMC temperature results. Extreme-audit PASS confirms diagnostic execution, not the physical validity or resolved cause of extreme pixels.
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

The following checks were run for this status review (no production build or training):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_data_manifest.py tests/test_heat_map_pipeline.py tests/test_landsat_source_audit.py tests/test_landsat_processing_audit.py tests/test_landsat_extreme_audit.py tests/test_sentinel_source_audit.py -q
# 47 passed; 102 Rasterio PendingDeprecationWarnings. Synthetic temporary fixtures only.
npm --prefix frontend test
# 17 passed.
npm --prefix frontend run build
# PASS.
.\.venv\Scripts\python.exe .\scripts\build_heat_map_pipeline.py --check-only --year 2025
# Exit 2, expected: verified esa_worldcover, landsat_lst_scenes, osm_roads.
# Only municipal_boundary and sentinel2_l2a_scenes have source errors.
.\.venv\Scripts\python.exe .\scripts\validate_data_manifest.py --json
# Exit 2, expected: four verified sources, also including worldpop.
# Broader required-source errors additionally include osm_green_spaces and periurban_lst_reference.
git diff --check
# PASS. Changed Markdown repository links also checked locally.
```

Current `methodology()` status reports real grid/model unavailable, an intervention
catalog present but no enabled optimizer location, and no real validation dataset.
The PCMC staged file matches its recorded size and checksum. Audit scene IDs match
all nine discovery selections. Source-quality/processing/extreme audit outputs were
inspected, not regenerated. No source verification state was changed.

## Smallest actions required to advance acceptance

### First real cell-level heat map

The code requires exactly `municipal_boundary`, `landsat_lst_scenes`,
`sentinel2_l2a_scenes`, `esa_worldcover`, and `osm_roads`.

1. Obtain the official PMC municipal outline and authority/version/license evidence.
   Confirm reuse terms for the staged official PCMC outline, import the combined
   outline, and verify its manifest provenance/checksum. Ward GIS is not needed here.
2. Manually place the six exact selected Sentinel-2 SAFE products and their required
   XML/B04/B08/B11/SCL files; follow [the audit checklist](sentinel_quality_audit.md).
   Audit and verify actual content before changing its pending status.
3. Rerun check-only preflight; then build the real grid and run the documented spatial
   validation/training workflow. The Landsat acquisitions are already complete.
   Investigate the [extreme-audit findings](landsat_extreme_audit.md) before accepting
   downstream scientific results; do not change QA or source pixels based only on
   this diagnostic. No real accuracy can be claimed before real spatial validation.

### Broader and later-stage acceptance

- Verified ward GIS for aggregation/reporting and ward UI.
- OSM green-space coverage for the broader morphology profile; same-season,
  independently sourced peri-urban reference for Heat Hazard calibration.
- Matching real model/grid, real SHAP, uncertainty validation, and defensible
  intervention transformations/capacity before model-backed scenarios.
- Audited location-specific capacity, costs, co-benefit basis and model-supported
  benefits before optimizer acceptance; genuine comparable pre/post treated/control
  observations before field validation and any reviewed calibration proposal.
- WorldPop is already verified but still requires aligned exposure processing.
  Sensors/social vulnerability are separate research evidence; measured albedo
  and building footprints remain optional. None is a first-profile source blocker.

## Known evidence limitations and historical records

- `data/processed/greenpulse_ml_grid.parquet`, model and SHAP files may exist locally.
  The grid metadata explicitly marks demo/synthetic data; model metadata references
  that dataset digest. These files cannot support real metrics, attribution or cooling.
- The earlier processing report's unresolved-location wording is superseded by the
  extreme audit: positions and clusters are known, but causes remain unconfirmed.
- The pre-existing, untracked `data/provenance/heat_map_pipeline_attempt_2025.json`
  is a 2026-09-29 historical attempt. Its missing-Landsat and required-ward statements
  are superseded by current source/code checks; it was preserved, not overwritten.
- The sensor manifest reserves `data/raw/sensors/observations.csv` as future scope;
  the optional import workflow writes registered datasets under `data/research/sensors/`.
  These distinct paths are not evidence of a verified sensor dataset.
