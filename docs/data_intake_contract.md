# Real-data intake contract

GreenPulse does not treat a file's presence as proof that it is usable. The authoritative inventory is `data/source_manifest.json`; its machine-readable shape is `schemas/source_manifest.schema.json`; and `scripts/validate_data_manifest.py` is the processing gate. Entries remain `pending` until their actual files and evidence pass the gate. The currently acquired WorldCover tile is marked separately as verified; this does not make the overall intake complete.

The selected archived season is **2025-03-01 through 2025-05-31**. Exact scene discovery, acquisition commands, municipal-source findings, and access blockers are in [real_data_acquisition.md](real_data_acquisition.md).

## What must be obtained

Choose one peak-summer year before downloading scenes. The Landsat, Sentinel-2, measured-albedo (if used), and peri-urban records must all declare exactly `YYYY-03-01` through `YYYY-05-31`. Do not insert a date merely to make validation pass.

| Contract ID | Class | Exact local path | Acquisition and evidence requirement |
|---|---|---|---|
| `municipal_boundary` | Required MVP | `data/boundaries/pmc_pcmc.geojson` | Verified PMC and PCMC outlines in EPSG:4326, with issuing authority, release/effective date, license, and both municipality values. |
| `ward_boundaries` | Required MVP | `data/boundaries/pmc_pcmc_wards.geojson` | Verified wards for both corporations in EPSG:4326. Each feature needs `municipality`, `ward_id`, and `ward_name`; record authority and boundary version. |
| `landsat_lst_scenes` | Required MVP | `data/raw/landsat/` | USGS Landsat 8/9 Collection 2 L2SP scenes intersecting both cities. Keep matching `MTL.txt`, `ST_B10.TIF`, `QA_PIXEL.TIF`, and `QA_RADSAT.TIF`; record every product ID. |
| `sentinel2_l2a_scenes` | Required MVP | `data/raw/sentinel2/` | Original extracted Sentinel-2 L2A SAFE products for the same season. Preserve product XML plus B04 10 m, B08 10 m, B11 20 m, and SCL 20 m. |
| `esa_worldcover` | Required MVP | `data/raw/worldcover/` | Original ESA WorldCover 2021 v200 `*_Map.tif` tiles covering both cities. This fixed 2021 snapshot is not current canopy measurement. |
| `osm_roads` | Required MVP | `data/raw/osm/roads.geojson` | EPSG:4326 road lines with `highway` tags, full city coverage, extraction query/snapshot timestamp, and ODbL attribution. |
| `osm_green_spaces` | Required MVP | `data/raw/osm/green_spaces.geojson` | Tagged green-space polygons covering both cities plus a documented exterior buffer; preserve the query/snapshot timestamp. |
| `worldpop` | Required MVP | `data/raw/worldpop/india_population_counts.tif` | One exact India counts release, preferably closest to the selected season. Record year, product/version, constrained status, CRS, resolution, and people-per-pixel units. |
| `periurban_lst_reference` | Required MVP | `data/processed/periurban_lst_reference.parquet` and `data/processed/periurban_lst_reference_metadata.json` | QA-valid Landsat LST outside both municipalities, with unique non-overlapping `grid_id` and `lst_c`, using the exact municipal season and QA method. Independently source and document the reference-area boundary. |
| `osm_buildings` | Optional MVP | `data/raw/osm/buildings.geojson` | Enable only when complete tagged building-footprint coverage has been assessed. The current morphology pipeline works without it. |
| `measured_albedo` | Optional MVP | `data/raw/albedo/albedo_pune_30m.tif` | Documented, QA-masked surface albedo on the exact 30 m LST grid and season, with `source` and `period` tags. Illustrative roof-albedo assumptions are not measurements. |
| `municipal_sensor_observations` | Future scope | `data/raw/sensors/observations.csv` | Not an MVP dependency. An authorized station inventory, coordinates, timestamps, units, calibration records, license, and credentials are not available in this repository. |

The USGS identifies the accepted Landsat product and dataset DOI and states there are no use restrictions: <https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products>. Sentinel data use is governed by the free, full and open Copernicus legal notice: <https://dataspace.copernicus.eu/terms-and-conditions>. ESA WorldCover publishes its v200 DOI and CC BY 4.0 terms: <https://esa-worldcover.org/en/data-access>. WorldPop also publishes CC BY 4.0 terms: <https://www.worldpop.org/faq/>. OSM extracts require ODbL attribution: <https://www.openstreetmap.org/copyright>.

## Complete the manifest

For every acquired source, replace the pending values in `data/source_manifest.json` with evidence from that specific release:

1. `source_organization`, exact `product`, URL/DOI/catalogue or scene `dataset_identifier`, and `license`.
2. Actual `access_date` and acquisition/vintage `scene_date_range`; never use the current date as a substitute for an unknown acquisition date.
3. Actual coverage, CRS, and source resolution. `SOURCE_NATIVE_MIXED` is allowed only for original multi-scene directories whose members carry their own CRS.
4. A SHA-256 digest of the exact local content. Files use ordinary file SHA-256. Directories use the validator's deterministic digest of every relative filename and byte.
5. `verification_status: "verified"` only after the preceding evidence and local content have been checked. Keep `data_classification: "real"` for production data.

PowerShell examples from the repository root:

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'

# File digest (prefix the displayed hash with "sha256:" and lowercase it in the manifest).
(Get-FileHash -Algorithm SHA256 .\data\raw\osm\roads.geojson).Hash.ToLower()

# Deterministic directory digest used by the validator.
.\.venv\Scripts\python.exe -c "from pathlib import Path; from backend.app.data_intake.manifest import sha256_path; print(sha256_path(Path('data/raw/landsat')))"
```

Do not commit the large source data. The repository's `.gitignore` already excludes `data/raw/*` and generated `data/processed/*`; the manifest remains reviewable.

## Validate before processing

Install the existing geospatial/data requirements, then run the gate:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-data.txt
.\.venv\Scripts\python.exe .\scripts\validate_data_manifest.py
```

Exit code `0` and `PASS` mean every required MVP source is verified, present, checksum-matched, and internally consistent. Exit code `2` means processing must stop. Each error is prefixed with its manifest source ID and field, for example `worldpop.local_path` or `landsat_lst_scenes.checksum`. Optional/future omissions are warnings unless marked `verified`.

For CI or another program:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_data_manifest.py --json
```

The validator checks:

- the complete authoritative inventory and correct required/optional/future classification;
- required provenance fields, real-vs-synthetic classification, ISO dates, and one exact shared peak-summer range;
- repository-relative paths without traversal, file/directory presence, and SHA-256 checksums;
- declared CRS syntax and raster CRS/resolution where applicable;
- existing pipeline-specific structure for municipal/ward GeoJSON, Landsat L2SP scenes, Sentinel-2 SAFE products, WorldCover rasters, and OSM geometry/tag classes.

Synthetic fixtures are rejected by default. `--allow-synthetic` exists only for tests and never makes a synthetic manifest valid for production use.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_data_manifest -v
```

The tests cover a complete valid manifest, absent required content, malformed JSON, the explicit synthetic-data gate, and the checked-in authoritative inventory. All fixture bytes are labelled artificial and live only in temporary directories.
