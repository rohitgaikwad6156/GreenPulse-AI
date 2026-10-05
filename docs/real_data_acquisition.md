# Real source acquisition status (2025 peak-summer season)

Status reviewed: **2026-10-05**.

This is the operational hand-off for the real-data phase. The search envelope `73.65,18.35,74.15,18.85` is only a catalogue/extract envelope; it is **not** a PMC/PCMC boundary. No demo geometry or measurement is accepted by these commands.

## Reproducible commands

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py discover
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py worldcover
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py worldpop
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py osm-roads
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py osm-green
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py osm-buildings
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py pcmc-boundary

$env:CDSE_USERNAME = 'your Copernicus Data Space username'
$env:CDSE_PASSWORD = 'your Copernicus Data Space password'
.\.venv\Scripts\python.exe .\scripts\acquire_real_sources.py sentinel

.\.venv\Scripts\python.exe .\scripts\validate_data_manifest.py
```

Downloads are atomic and reused when already valid. HTML authentication responses and malformed GeoTIFFs are rejected. Provenance records, including URLs, selection rules, scene IDs, timestamps, byte sizes, and SHA-256 values, are written under `data/provenance/`. Source rasters remain under `data/raw/`. Selected Landsat rasters are now tracked with Git LFS and their MTL files are tracked directly; other raw-source paths remain ignored according to `.gitignore`.

## Municipal outlines required for the study grid

Acquire separate, official EPSG:4326 PMC and PCMC **municipal outline** GeoJSON files, with the issuing authority, dataset identifier, effective date, and reuse permission. The official PCMC Smart GIS outline is staged at `data/boundaries/source/pcmc_boundary_official.geojson` with [provenance](../data/provenance/acquisition_pcmc_boundary.json). It covers PCMC only; the official PMC outline is still missing and the combined `municipal_boundary` manifest entry remains `pending`. The PCMC provenance does not state redistribution permission; obtain written terms before redistribution. A search envelope or ward map PDF is not a substitute. Import the two outlines independently of ward GIS:

```powershell
.\.venv\Scripts\python.exe .\scripts\import_municipal_outlines.py `
  --pmc-outline C:\path\pmc-outline.geojson --pcmc-outline C:\path\pcmc-outline.geojson `
  --provenance C:\path\outline-provenance.json
```

The provenance JSON has `PMC` and `PCMC` objects with `source_organization`, `source_url`, `dataset_identifier`, `license`, and `effective_date` fields. Validate the resulting `data/boundaries/pmc_pcmc.geojson`, record its checksum in `data/source_manifest.json`, and run manifest validation. The importer only combines supplied official outlines; it does not create ward geometry.

## Ward boundaries required only for reporting

The official PMC open-data catalogue currently exposes ward maps as PDFs and a coordinate list, not GIS polygons. The PCMC election site likewise exposes final ward maps as PDFs. PCMC Smart GIS exposes the official `citylayers4:boundary` municipal outline through WFS, but its published capabilities do not include a ward/prabhag polygon layer. A map PDF or screenshot must not be digitized and relabelled as authoritative GIS data.

For ward aggregation and the ward UI, request/export two **EPSG:4326 GeoJSON ward polygon files** from the responsible municipal election/GIS offices, with release/effective date, dataset identifier or written response URL, and reuse license/permission. Cell-level dataset assembly and training can proceed without them. Contact points published by the portals are `opendata@punecorporation.org` for PMC open data and `egov@pcmcindia.gov.in` for PCMC. Save the files outside the output paths, create a provenance JSON, and import them:

```json
{
  "PMC": {"source_organization": "...", "source_url": "...", "dataset_identifier": "...", "license": "...", "effective_date": "YYYY-MM-DD"},
  "PCMC": {"source_organization": "...", "source_url": "...", "dataset_identifier": "...", "license": "...", "effective_date": "YYYY-MM-DD"}
}
```

```powershell
.\.venv\Scripts\python.exe .\scripts\import_municipal_boundaries.py `
  --pmc-wards C:\path\pmc.geojson --pcmc-wards C:\path\pcmc.geojson `
  --provenance C:\path\boundary-provenance.json `
  --pmc-id-field WARD_ID --pmc-name-field WARD_NAME `
  --pcmc-id-field WARD_ID --pcmc-name-field WARD_NAME
```

The importer validates polygon type, validity, Pune-region coordinates, identifiers, and provenance; normalizes only the field names; writes `data/boundaries/pmc_pcmc_wards.geojson`, dissolves source wards into `data/boundaries/pmc_pcmc.geojson`, and records input hashes. It is idempotent. Substitute the real source field names in the command—do not rename or invent ward values by hand.

## Scene selection and credentials

`data/provenance/discovery_2025.json` records nine USGS Landsat Collection 2 L2SP Tier-1 scenes (WRS path/row 147/047) acquired from 2 March through 5 May 2025 with catalogue scene cloud at or below 10%. Required files per product are original `MTL.txt`, `ST_B10.TIF`, `QA_PIXEL.TIF`, and `QA_RADSAT.TIF`. Processing additionally rejects QA_PIXEL bits 0–5 and 7 and QA_RADSAT terrain-occlusion bit 11. Acquisition and verification are now complete: all nine selected products and 36 required files are present under `data/raw/landsat/<LANDSAT_PRODUCT_ID>/`. The manifest marks Landsat `verified` and records SHA-256 `9bf2cbf4ee2d1c2763a777ed081e7aff42ef829274aa16884ef58a2b1d1982a7`. The [source audit](landsat_quality_audit.md), [processing smoke test](landsat_processing_audit.md), and [extreme diagnostic audit](landsat_extreme_audit.md) each pass all nine scenes. Earlier anonymous-download authentication failures are historical, not current Landsat blockers. These are full-scene diagnostics, not municipal temperature results; hot/cold clusters still warrant investigation.

The same discovery record lists six Copernicus Sentinel-2 L2A products: both Pune-intersecting tiles `43QCA` and `43QDA` on 14 March, 13 April, and 10 May 2025, all with catalogue cloud at or below 10%. The downloader retains product metadata, B04/B08 at 10 m, B11/SCL at 20 m. Processing accepts SCL classes 4 and 5 only. Current intake is manual and pending: 0/6 SAFE directories and 0/30 required files are present. Use the [manual source audit and exact placement checklist](sentinel_quality_audit.md), `scripts/audit_sentinel_sources.py`, and `scripts/show_missing_sentinel_files.py`. These helpers never download data or mark Sentinel verified. The credential-based acquisition command above remains an available tool, not evidence of completed acquisition.

Exact selected product IDs (unchanged from discovery):

- `S2B_MSIL2A_20250314T052649_N0511_R105_T43QCA_20250314T095315`
- `S2B_MSIL2A_20250314T052649_N0511_R105_T43QDA_20250314T095315`
- `S2B_MSIL2A_20250413T052649_N0511_R105_T43QCA_20250413T075318`
- `S2B_MSIL2A_20250413T052649_N0511_R105_T43QDA_20250413T075318`
- `S2A_MSIL2A_20250510T053241_N0511_R105_T43QCA_20250510T084438`
- `S2A_MSIL2A_20250510T053241_N0511_R105_T43QDA_20250510T084438`

The selected full Landsat scene footprint also covers land outside PMC/PCMC in the same acquisitions. It may supply the temperature observations for the peri-urban comparison, but the reference cannot be produced until the verified municipal polygons and an independently sourced peri-urban selection boundary are available. No exterior box is treated as evidence of municipal exclusion.

## Other sources and albedo

- ESA WorldCover tile `ESA_WorldCover_10m_2021_v200_N18E072_Map.tif` was obtained from ESA's primary object store. Its CRS, 10 m-equivalent angular resolution, Pune coverage, and SHA-256 are recorded and validated. It is a 2021 categorical land-cover snapshot, not a current canopy measurement.
- WorldPop acquisition is complete and the manifest is `verified`: the official 2025 India R2024B v1 unconstrained population-count raster (people per pixel) exists at `data/raw/worldpop/india_population_counts.tif` and passes local checksum validation. It is an exposure source, not a first heat-map build requirement.
- OSM roads are present and verified with a 2026-09-19 snapshot; green spaces and buildings remain pending. OSM queries preserve object IDs, versions, timestamps, tags, extraction queries, and ODbL attribution for roads, green spaces, and buildings. Zero mapped objects do not prove physical absence.
- No authoritative measured in-season Pune albedo dataset has been established. This input remains optional and pending; GreenPulse will not derive or label an assumed roof reflectance as measured albedo.

## Authoritative endpoints

- PMC Open Data: <https://opendata.pmc.gov.in/> and API <https://opendataapi.pmc.gov.in/>
- PCMC elections: <https://www.pcmcindia.gov.in/electionNew>
- PCMC Smart GIS WFS: <https://smartgisda.pcmcindia.gov.in/geoserver/citylayers4/wfs?service=WFS&request=GetCapabilities>
- USGS Landsat STAC: <https://landsatlook.usgs.gov/stac-server>
- Copernicus Data Space STAC: <https://stac.dataspace.copernicus.eu/v1>
- ESA WorldCover: <https://esa-worldcover.org/en/data-access>
- WorldPop data server: <https://data.worldpop.org/GIS/Population/Global_2015_2030/R2024B/2025/IND/v1/100m/unconstrained/>
- OpenStreetMap copyright and license: <https://www.openstreetmap.org/copyright>
