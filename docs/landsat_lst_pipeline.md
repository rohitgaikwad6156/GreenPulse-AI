# Landsat-only LST pipeline (Step 9)

GreenPulse AI is an AI-powered Urban Climate Decision-Support System. This step creates its **observed continuous land surface temperature target in degrees Celsius**, not a pedestrian air-temperature map and not an ML prediction.

## Why USGS Level-2 Surface Temperature

Collection 2 Level-2 `ST_B10` is the USGS atmospheric/emissivity-corrected land surface temperature product. It avoids implementing a separate thermal retrieval from Level-1 radiance/brightness temperature for the MVP. The delivered raster has 30 m pixels, but the thermal sensor's native footprint is coarser (about 100 m); nearby output cells are not independent 30 m thermal measurements. USGS documentation: <https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature>.

The pipeline accepts only Landsat 8/9 Collection 2 **L2SP** products. L2SR (surface reflectance only) products do not provide usable `ST_B10`.

## Required real input files

1. `data/boundaries/pmc_pcmc.geojson`: verified PMC and PCMC polygon features in WGS84 longitude/latitude. Each feature must have `properties.municipality` equal to `PMC` or `PCMC`; both must be present. Use the intended official boundary version and record its source and effective date. Do not substitute the Step 6 fictional wards. A GeoJSON from another CRS must be reprojected to EPSG:4326 first.
2. Extracted original USGS Landsat 8/9 Collection 2 Level-2 **L2SP** scene directories under `data/raw/landsat/`. For every selected scene, keep the four matching files: `*_MTL.txt`, `*_ST_B10.TIF`, `*_QA_PIXEL.TIF`, and `*_QA_RADSAT.TIF`. Other original files can remain with the product. The script reads scenes recursively and selects March, April, and May acquisitions for the requested year.

To obtain scenes, use USGS EarthExplorer: <https://earthexplorer.usgs.gov/>. Search the study area, choose Landsat Collection 2 Level-2, March 1 through May 31 for the selected year, and download complete Landsat 8/9 L2SP products with visible study-area coverage. Inspect scene cloud coverage before downloading, but retain pixel-level QA masking in the pipeline. USGS access guide: <https://www.usgs.gov/faqs/how-do-i-search-and-download-landsat-collection-2-data-products>.

## PowerShell commands

Run from Windows PowerShell. These commands do not download satellite products.

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_landsat_lst.py' -v
```

If EarthExplorer products are `.tar` files already placed under `data/raw/landsat/`, extract each archive into its own folder:

```powershell
Get-ChildItem .\data\raw\landsat -Filter '*.tar' | ForEach-Object {
    $sceneDirectory = Join-Path .\data\raw\landsat $_.BaseName
    New-Item -ItemType Directory -Path $sceneDirectory -Force | Out-Null
    tar.exe -xf $_.FullName -C $sceneDirectory
}
```

After the verified boundary and scenes are present, run the first example for March-May 2025:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_landsat_lst.py --year 2025
```

The year is an explicit acquisition choice, not a claim that 2025 data are already on this computer. For another season, set `--year` to that acquisition year. The script stops with an error if boundary/scenes are missing, metadata calibration is absent, or no valid LST pixel survives.

## What the script does

1. Reads each scene's original `*_MTL.txt`. It requires `TEMPERATURE_MULT_BAND_ST_B10` and `TEMPERATURE_ADD_BAND_ST_B10` rather than assuming constants. For every valid ST DN: `T_K = M_T × DN + A_T`; `T_C = T_K − 273.15`. USGS metadata guide: <https://www.usgs.gov/media/files/landsat-8-9-collection-2-level-2-science-product-guide>.
2. Rejects ST fill (`DN=0`), QA_PIXEL fill, dilated cloud, high-confidence cirrus, cloud, cloud shadow, snow, and water (bits 0-5 and 7). It also rejects QA_RADSAT terrain occlusion (bit 11). Water is excluded because this is a land-focused urban heat analysis. USGS QA definitions: <https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands>.
3. Uses nearest-neighbour reprojection of stored DN and QA flags to a 30 m EPSG:32643 grid. It then converts valid DN to °C. This avoids blending QA bit patterns or treating resampling as new thermal information.
4. Clips to the union of the two verified municipality polygons. At borders, a cell is included when its centre is inside the polygon.
5. Computes the **pixelwise median** of accepted March-May scene temperatures. It does not fill holes; each cell's number of valid scenes is saved separately. Scene layers are held on temporary disk and median processing is chunked to limit RAM use.
6. Computes min, max, mean, and no-data percentage from finite cells **inside** the municipal boundary, plus a histogram. These are calculated from actual input rasters; the code contains no Pune temperature numbers.

## Outputs after a successful real-data run

- `data/processed/lst_pune_30m.tif`: float32 observed seasonal median LST in °C; EPSG:32643; 30 m grid; nodata = -9999.
- `data/processed/lst_pune_30m_valid_count.tif`: number of QA-accepted observations per 30 m cell.
- `data/processed/lst_pune_30m.json`: period, scene IDs, each scene's metadata calibration, QA rule, and measured summary statistics.
- `data/processed/lst_pune_30m_histogram.png`: distribution of valid in-boundary grid cells.

No output at these paths should be presented as real until the script succeeds with real source files. The small test fixture writes only to an automatically deleted temporary directory.

## Common mistakes and scientific limitations

- Using Level-1 `B10` brightness temperature instead of Level-2 `ST_B10` surface temperature.
- Applying Collection 1 or surface-reflectance scale factors to Collection 2 `ST_B10`, or subtracting 273.15 twice. The per-scene MTL file is the source of the multiplier and offset.
- Using only the QA_PIXEL `Clear` bit. It does not by itself exclude shadow, cirrus, snow, water, or all poor pixels.
- Trusting a scene-level cloud percentage as if every city pixel were clear. Pixel QA determines inclusion.
- Treating the delivered 30 m raster as 30 m independent thermal sensing. The thermal footprint is coarser.
- Filling ST no-data holes caused by clouds or missing emissivity with invented values. This pipeline leaves them as nodata and reports coverage.
- Treating a March-May median as an instantaneous heat event or aligning it later with optical features from a different season without documenting dates.
- Assuming the municipal boundary is current or official without checking its source and version.
- Reading the histogram cell count as an independent sample size. Nearby cells can share thermal information.

Earth Engine can search and export Landsat scenes, but it requires a configured account/project. This local pipeline deliberately uses original USGS files and their `MTL.txt` calibration, so it remains reproducible without Earth Engine access.
