# Real Heat Map pipeline (March–May 2025)

Run from the GreenPulse-AI repository with its existing Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\build_heat_map_pipeline.py --check-only --year 2025
.\.venv\Scripts\python.exe scripts\build_heat_map_pipeline.py --year 2025 --jobs 2 --trials 8
```

Dependencies are the existing `backend/requirements-xgboost.txt` stack. The first
command validates sources and makes no output changes. The build stops at source
validation when real inputs are missing. It never calls the demo generator or
reuses an old ML grid, fold assignment, or model as a fallback.

## Sources and processing

The existing `data/source_manifest.json` supplies local paths and provenance for
five required records: `municipal_boundary`, `landsat_lst_scenes`,
`sentinel2_l2a_scenes`, `esa_worldcover`, and `osm_roads`.
Each must be verified, classified real, and match its recorded SHA-256 checksum.
The satellite records must both declare `2025-03-01` through `2025-05-31`.
WorldPop, green-space distance, measured albedo, and peri-urban hazard calibration
are not prerequisites for this Heat Map model.

1. Landsat 8/9 Collection 2 **L2SP**: retain original MTL.txt, ST_B10, QA_PIXEL,
   and QA_RADSAT. Read per-scene calibration from MTL and compute
   `LST Celsius = ST_B10 DN * multiplier + offset - 273.15`. Mask fill, clouds,
   cirrus, shadows, snow, water, and terrain occlusion before seasonal median.
2. Sentinel-2 L2A SAFE: retain product metadata, B04/B08 10 m, B11/SCL 20 m.
   Apply BOA offsets and quantification from metadata. Compute NDVI and NDBI,
   mask SCL-invalid pixels, aggregate and composite onto the LST lattice.
3. ESA WorldCover: nearest-neighbor categorical mapping to nested 10 m cells,
   then tree class 10 and built class 50 fractions as percentages per 30 m cell.
   Retain valid-subpixel counts. The existing source is the 2021 v200 product;
   its vintage is recorded, not presented as measured 2025 canopy.
4. OSM: unique mapped road centerline length intersected with each 900 m² cell,
   expressed in km/km². Zero means no mapped motor road. The source snapshot
   date remains in provenance; it is not silently labeled a 2025 extract.
5. Use one snapped EPSG:32643 30 m grid within verified PMC/PCMC municipal polygons.
   Require exact raster transforms, CRS, shapes and masks. Retain cells with real
   LST and all five predictors regardless of ward availability. Assign verified
   ward labels by cell center only when the reporting source passes provenance
   checks; otherwise keep ward_id and ward_name null. Write coverage diagnostics.
6. Train with exactly `ndvi`, `ndbi`, `tree_canopy_pct`, `built_pct`, and
   `road_density`, targeting `lst_c`. Reuse the existing five-fold **5 km spatial
   block** validation and nested XGBoost tuning. The existing baseline comparison
   is generated as part of the trainer's contract. No random pixel split, target,
   ward identifier or coordinate is included among predictors.

USGS conversion reference: [Collection 2 surface temperature](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature).
Sentinel calibration reference: [Copernicus S2 products](https://sentiwiki.copernicus.eu/web/s2-products).
A 30 m analysis grid does not increase Landsat's native thermal resolution.

## Outputs and compatibility

Successful completion saves:

- `data/processed/greenpulse_ml_grid.parquet`
- `data/processed/metadata.json` (required backend companion)
- `models/xgboost_lst.joblib`
- `models/model_metadata.json`

It also saves source rasters, QA counts, coverage plots, spatial fold artifacts,
and baseline metrics. Existing API field names, ward IDs, feature order,
dataset/model hashes, and model metadata remain compatible with the backend.
Model metadata contains observed spatial MAE/RMSE/R² and per-fold results,
source provenance, acquisition period, feature distributions and model checksum.
No fabricated prediction interval or Heat Hazard Score is attached. Those require
separate calibration.

The complete build runs in a temporary staging folder. Sources are revalidated
before publication. Prior output files are copied to
`data/interim/heat_map_backups/previous-*`; replacements roll back on a write
failure. Publication is a sequence of file replacements, not a filesystem-wide
transaction: stop the API during publication and restart it afterwards. Explicit
`DEMO`/`SYNTHETIC` metadata is rejected by production grid access, training,
prediction and simulation loaders. Existing demo files are preserved, not relabeled.

## Acquisition and current blockers

Attempted during this implementation:

- `scripts/acquire_real_sources.py landsat`: USGS redirected the original MTL
  asset to authentication; the downloader rejected the HTML response.
- `scripts/acquire_real_sources.py sentinel`: stopped because CDSE_USERNAME and
  CDSE_PASSWORD are not configured. Configure them locally; do not paste secrets
  into chat. Then rerun the command.
- Earth Engine: no Python package, saved authentication, Google application
  credentials, or configured project were present. GEE is not an anonymous
  download fallback. [Authentication and project setup](https://developers.google.com/earth-engine/guides/auth).
- Official PCMC WFS capabilities were retrieved; no ward/prabhag feature type
  was listed. Its municipal outline and zone boundaries are not ward substitutes.
- Public community ward files were found, but their metadata describes independent
  digitization. They were not installed as verified municipal polygons.

No new real grid or trained model has been produced. The files currently at the
requested production paths predate this build and the grid metadata labels them
`DEMO / SYNTHETIC DATA`; production access now rejects that label.

Obtain the original scenes through authorized USGS/Copernicus access and verified
combined PMC/PCMC municipal polygons with their effective dates and provenance.
Update verified source checksums and rerun `--check-only`. Official ward GIS can
be imported later using `import_municipal_boundaries.py` for ward reporting.
A bounding box, zone polygon, traced PDF, or fictional ward is never substituted
for a verified municipality or ward.
