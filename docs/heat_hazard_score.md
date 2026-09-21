# Step 17: Heat Hazard Score

GreenPulse AI remains **An AI-powered Urban Climate Decision-Support System**. The XGBoost model's target remains continuous **land surface temperature (LST in °C)**. This step adds a separate, transparent dashboard **Heat Hazard Score**. The GreenPulse research PDF motivates a readable map indicator; this step keeps the physical temperature prediction primary and requires documented reference temperatures before showing a number.

## Formula and meaning

`H = 100 × clip((T_pred - T_background) / (T_hot_ref - T_background), 0, 1)`

- `T_pred`: the model's predicted LST for a 30 m grid cell, in °C.
- `T_background`: median of **observed, QA-valid** March–May LST in a documented Pune rural/peri-urban reference area **outside PMC/PCMC**, in °C.
- `T_hot_ref`: 95th percentile of **observed, QA-valid** March–May LST in the real PMC/PCMC ML table, in °C.

The score is dimensionless from 0 to 100. `0` means predicted LST is at or below the background reference. `100` means it reaches or exceeds the municipal hot reference. Values in between linearly locate predicted LST between the two. They are **not** probabilities, health thresholds, or percentage changes in temperature. Clipping conceals how far a cell lies beyond either anchor. The score is relative to the documented reference season and should be recalibrated when the data period changes.

The existing municipal ML table contains only PMC/PCMC wards, so it cannot establish a rural/peri-urban background. No Pune reference temperature is supplied or guessed here. The separate background sample must come from the same March–May season and the same observed surface-temperature product/QA approach. The existing Step 9 LST raster is clipped to PMC/PCMC, so its extent must be expanded or a separately processed same-season peri-urban LST layer must be prepared first.

## Required real input files

1. `data/processed/greenpulse_ml_grid.parquet` and `data/processed/metadata.json` from Step 12, containing observed `lst_c`, grid IDs, and the March–May period.
2. `models/xgboost_lst.joblib` and `models/model_metadata.json` from Step 15, matching the model-artifact hash, table hash, target, features, CRS, resolution, and date range. Calibration rejects a stale or substituted model.
3. `data/processed/periurban_lst_reference.parquet`, containing `grid_id` and `lst_c` columns of observed, QA-valid LST cells outside the municipal grid. IDs must be unique and must not overlap municipal IDs.
4. `data/processed/periurban_lst_reference_metadata.json`, documenting `source_organization`, `source_product`, `source_scene_or_composite`, `periurban_area_definition`, `area_boundary_source`, `qa_mask_method`, `temperature_variable` (`land_surface_temperature`), `units` (`degC`), `date_range` (identical to the municipal March–May period), and `region` (`Pune rural/peri-urban outside PMC/PCMC`). This provenance is supplied by the data preparer; the code checks its presence and ID separation but cannot independently prove the selected geography is truly rural. Inspect the polygon/source before using the score publicly.

Do not substitute IMD air-temperature records for either LST anchor: [USGS describes Landsat Collection 2 surface temperature as surface temperature](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature). A single-season 95th percentile is a **seasonal** reference; call it historical only after an appropriate multi-year data series has been assembled. The score is a hazard indicator, not a full Climate Risk Score, because it does not model exposure, vulnerability, or capacity. [WHO describes heat vulnerability as depending on exposure and individual and social factors](https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health).

## Calibrate and test in Windows PowerShell

From the `GreenPulse-AI` root, after all required real files exist:

```powershell
.\.venv\Scripts\python.exe scripts\calibrate_heat_hazard.py
```

The script prints the **calculated** background median, municipal 95th percentile, period, and metadata path. It writes a `heat_hazard_score` object into `models/model_metadata.json`, preserving the XGBoost target and training metrics. That object stores both temperatures, methods, row counts, model/dataset/peri-urban/provenance hashes, the source model-metadata hash, date range, formula, interpretation, and limitations. If real references are absent, overlap the municipal grid, have a mismatched season, or belong to a stale model, calibration stops and does not create a numeric score.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_heat_hazard -v
```

Expected: five passing tests, all based on **ARTIFICIAL TEST FIXTURES** in temporary directories. They cover formula behavior, mismatched seasons, overlapping peri-urban IDs, and stale model artifacts. Their numbers are formula checks, not Pune measurements.

The Overview dashboard currently shows an empty Heat Hazard Score card. A numeric cell score can be displayed only after the real model predicts that cell's LST and the metadata contains calibrated references. No XGBoost retraining or score-target training occurs in this step.
