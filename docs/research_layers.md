# Optional research layers

These features extend the research workflow without changing the land-surface-temperature MVP. The XGBoost target remains wall-to-wall seasonal Landsat LST. Point measurements, exposure, and vulnerability are separate evidence products and are never silently added to model features, Heat Hazard Score, or intervention claims.

## Verified point observations

The manifest contract is [`schemas/point_sensor_manifest.schema.json`](../schemas/point_sensor_manifest.schema.json). It supports verified observations of:

- `air_temperature_c`;
- `relative_humidity_pct`;
- `aqi` using the source provider’s documented AQI method.

Each dataset records organization, product, URL/identifier, license, access date, file checksum, variables, freshness and temporal-match thresholds, and a station inventory. Every station records provider ID, coordinates, measurement height, instrument, and calibration reference. Every CSV observation records a unique observation ID, station ID, timezone-aware UTC timestamp, coordinates, QA status, and declared variables.

Only `qa_status=valid` rows are imported. Duplicate IDs, unknown stations, coordinate mismatches, invalid values, missing provenance, and checksum failures stop import. The importer is idempotent for the same dataset version and evidence hash:

```powershell
.\.venv\Scripts\python.exe scripts\import_point_sensors.py `
  --manifest C:\path\sensor_manifest.json `
  --observations C:\path\sensor_observations.csv
```

Imported files live under `data/research/sensors/DATASET_ID/` and are gitignored. They remain points. GreenPulse does not krige, inverse-distance weight, rasterize, or otherwise interpolate them citywide because no validated Pune method is supplied.

`GET /api/research/sensors/nearby` reports the nearest observation’s physical distance and temporal offset. Its confidence label is `point_proximity_only_not_calibrated_for_lst`; proximity is not an LST confidence interval or evidence that the station represents a whole 30 m cell.

The status API distinguishes:

- `missing`: no verified dataset;
- `sparse`: fewer stations than the manifest’s predeclared context threshold;
- `stale`: latest observation exceeds the predeclared freshness threshold;
- `temporally_mismatched`: observations do not overlap the LST MVP period;
- `available`: verified point context is present, still without interpolation.

## Temporal scope

The MVP remains explicitly limited to the source manifest’s `peak_summer` period, **2025-03-01 through 2025-05-31**. Multi-season composites are not implemented. Sensor observations outside this period can be preserved as point records but are labelled temporally mismatched for comparison with the current LST composite.

## Exposure, vulnerability, and risk

[`data/research/research_layers.json`](../data/research/research_layers.json) keeps exposure and vulnerability separate:

- population exposure is intended to use the verified WorldPop counts product and derived density layer;
- social vulnerability requires authoritative, licensed, current small-area indicators with compatible boundaries and documented denominators.

The WorldPop country raster is locally checksum-verified, but the 30 m population-exposure layer is `source_verified_processing_blocked` until the real municipal reference grid and boundaries exist. Social vulnerability remains `missing`. Population is not treated as vulnerability. Heat Hazard Score remains only a normalized predicted-LST hazard indicator.

No composite climate-risk score is calculated. A future composite would require an established documented risk framework, complete hazard/exposure/vulnerability/capacity inputs, normalization justification, missing-data treatment, uncertainty propagation, and sensitivity analysis. GreenPulse will not create an arbitrary weighted sum.

## Future scope

The following remain future work unless real implementations and evidence are added:

- CFD and 3D urban-canyon physics;
- tree-species growth, survival, irrigation, and canopy maturation;
- continuous IoT ingestion and automatic model retraining.

The `/research-layers` UI exposes these limitations and the missing, sparse, stale, and temporal-mismatch states directly.
