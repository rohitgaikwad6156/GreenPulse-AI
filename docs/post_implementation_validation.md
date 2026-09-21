# Provenance-aware post-intervention validation

GreenPulse now separates the legacy two-period descriptive calculator from the evidence-gated validation workflow. The legacy `POST /api/validation/did` remains available for manual arithmetic and the explicitly synthetic demo, but it cannot claim verified provenance. Real validation uses imported, checksum-verified observations and versioned reports.

## Required input contract

The manifest schema is [`schemas/validation_dataset_manifest.schema.json`](../schemas/validation_dataset_manifest.schema.json). A dataset must provide:

- a stable dataset ID/version, named location and intervention, evidence label, `lst_c` target, and `EPSG:32643`;
- at least two pre periods and one post period, ordered by acquisition date;
- one scene ID, scene checksum, acquisition date, declared season, local overpass time, and QA criteria for every period;
- a season start/end (`MM-DD`) and maximum overpass-time difference, both enforced during import;
- complete treated/control observations for exactly the same grid IDs in every period;
- an observation-file SHA-256 and verified reference grid containing matching `grid_id`, `x`, and `y`;
- documented control-selection method and eligibility rule;
- declared spillover distance, spatial-autocorrelation neighborhood, and parallel-trend slope-difference threshold from the analysis plan—not a value chosen after seeing results;
- model dataset version and model SHA-256 when predicted intervention changes are supplied.

Observation CSV columns are `grid_id,group,period_id,lst_c,x,y,qa_valid,ndvi`. `ndvi` may be blank. Every imported row must pass the declared QA; rejected pixels must remain absent rather than being imputed. Duplicate cell-period rows, incomplete panels, group changes, unrecognized grid IDs, coordinate mismatches, checksum failures, mismatched seasons, or overpass differences outside the declared tolerance stop import.

## Analysis and diagnostics

The estimator compares each cell’s mean post-period LST with its mean pre-period LST and subtracts the control-group mean change. Pre-period group-mean slopes are reported separately; passing the declared tolerance is a diagnostic, not proof of the parallel-trends assumption.

The report includes treated/control sample sizes, period means, pre-period standardized mean difference, nearest treated-control distances, controls within the declared spillover distance, and Moran’s I for group-residualized cell changes within the declared spatial neighborhood. Positive spatial autocorrelation triggers a warning.

When both groups have at least two cells, uncertainty is an unadjusted Welch 95% confidence interval for the difference in cell-level mean changes. It does not adjust for spatial autocorrelation, scene-level dependence, matching uncertainty, or control selection and can be too narrow. With smaller samples the interval is unavailable rather than fabricated.

Predictions must match every treated grid ID exactly. Residuals equal control-adjusted observed ΔLST minus predicted ΔLST; the report includes mean residual, MAE, and RMSE for the imported follow-up sample. They are not spatial cross-validation metrics.

## Import, report, and approval commands

```powershell
.\.venv\Scripts\python.exe scripts\import_validation_observations.py `
  --manifest C:\path\validation_manifest.json `
  --observations C:\path\observations.csv `
  --grid data\processed\greenpulse_ml_grid.parquet

.\.venv\Scripts\python.exe scripts\build_validation_report.py DATASET_ID
```

Imports are stored under `data/validation/imported/DATASET_ID/`; reports are written to `data/validation/reports/DATASET_ID.json`. These evidence artifacts are gitignored. `GET /api/validation/datasets` lists only datasets explicitly labelled `REAL INTERVENTION OBSERVATIONS`. `POST /api/validation/analyze/{dataset_id}` generates the same report for the UI.

A calibration proposal is emitted only for real evidence that passes the pre-trend and spillover gates. It is marked `PROPOSED_NOT_ADOPTED`. Human approval is a separate, hash-bound record:

```powershell
.\.venv\Scripts\python.exe scripts\approve_validation_calibration.py DATASET_ID `
  --decision approve `
  --approver "Full name / authority" `
  --rationale "Documented review rationale"
```

The approval command rejects synthetic, blocked, tampered, or proposal-free reports. It writes `data/validation/approvals/DATASET_ID.json` and deliberately does not modify simulator settings, model metadata, or the intervention catalog. Adoption remains a separate reviewed change.

## Current evidence status

**BLOCKED.** No genuine intervention pre/post dataset exists locally. The bundled demo and automated fixtures are explicitly synthetic and cannot produce a production calibration proposal or approval. To unblock, import one genuine intervention dataset satisfying the manifest, grid, scene, QA, control, and provenance contract above.
