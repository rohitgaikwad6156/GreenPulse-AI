# Real source acquisition status (2025 peak-summer season)

This is the operational hand-off for the real-data phase. The search envelope `73.65,18.35,74.15,18.85` is only a catalogue/extract envelope; it is **not** a PMC/PCMC boundary. No demo geometry or measurement is accepted by these commands.

## Reproducible commands

Run from `D:\green plus ai\GreenPulse-AI`:

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

Downloads are atomic and reused when already valid. HTML authentication responses and malformed GeoTIFFs are rejected. Provenance records, including URLs, selection rules, scene IDs, timestamps, byte sizes, and SHA-256 values, are written under `data/provenance/`. Source rasters remain under the existing ignored `data/raw/` tree.

## Municipal boundaries: smallest required user action

The official PMC open-data catalogue currently exposes ward maps as PDFs and a coordinate list, not GIS polygons. The PCMC election site likewise exposes final ward maps as PDFs. PCMC Smart GIS exposes the official `citylayers4:boundary` municipal outline through WFS, but its published capabilities do not include a ward/prabhag polygon layer. A map PDF or screenshot must not be digitized and relabelled as authoritative GIS data.

Request/export two **EPSG:4326 GeoJSON ward polygon files** from the responsible municipal election/GIS offices, with release/effective date, dataset identifier or written response URL, and reuse license/permission. Contact points published by the portals are `opendata@punecorporation.org` for PMC open data and `egov@pcmcindia.gov.in` for PCMC. Save the files outside the output paths, create a provenance JSON, and import them:

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

`data/provenance/discovery_2025.json` records nine USGS Landsat Collection 2 L2SP Tier-1 scenes (WRS path/row 147/047) acquired from 2 March through 5 May 2025 with catalogue scene cloud at or below 10%. Required files per product are original `MTL.txt`, `ST_B10.TIF`, `QA_PIXEL.TIF`, and `QA_RADSAT.TIF`. Processing additionally rejects QA_PIXEL bits 0–5 and 7 and QA_RADSAT terrain-occlusion bit 11. Anonymous asset URLs redirect to USGS authentication on this host. The smallest action is to download those exact product IDs with a USGS EarthExplorer/M2M account into `data/raw/landsat/<LANDSAT_PRODUCT_ID>/`, or provide AWS requester-pays credentials, then rerun manifest validation.

The same discovery record lists six Copernicus Sentinel-2 L2A products: both Pune-intersecting tiles `43QCA` and `43QDA` on 14 March, 13 April, and 10 May 2025, all with catalogue cloud at or below 10%. The downloader retains product metadata, B04/B08 at 10 m, B11/SCL at 20 m. Processing accepts SCL classes 4 and 5 only. The smallest action is setting credentials for a free Copernicus Data Space account and running `sentinel` as shown above.

The selected full Landsat scene footprint also covers land outside PMC/PCMC in the same acquisitions. It may supply the temperature observations for the peri-urban comparison, but the reference cannot be produced until the verified municipal polygons and an independently sourced peri-urban selection boundary are available. No exterior box is treated as evidence of municipal exclusion.

## Other sources and albedo

- ESA WorldCover tile `ESA_WorldCover_10m_2021_v200_N18E072_Map.tif` was obtained from ESA's primary object store. Its CRS, 10 m-equivalent angular resolution, Pune coverage, and SHA-256 are recorded and validated. It is a 2021 categorical land-cover snapshot, not a current canopy measurement.
- WorldPop acquisition targets the official 2025 India R2024B v1 unconstrained population-count raster (people per pixel). Its approximately 1.7 GB country file must complete and pass raster/checksum validation before the manifest is updated.
- OSM queries preserve object IDs, versions, timestamps, tags, extraction queries, and ODbL attribution for roads, green spaces, and buildings. Zero mapped objects do not prove physical absence.
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
