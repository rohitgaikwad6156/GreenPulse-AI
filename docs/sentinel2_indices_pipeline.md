# Sentinel-2 L2A NDVI and NDBI pipeline (Step 10)

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** This step creates optical **features**; it does not train a model or infer pedestrian air temperature.

## Real inputs required before running

1. `data/processed/lst_pune_30m.tif`: the **real** Step 9 Landsat March–May LST raster for the same `--year`. This is the exact output grid reference. Its CRS must be EPSG:32643, pixel size 30 m, and period tag March 1–May 31 of the chosen year.
2. `data/boundaries/pmc_pcmc.geojson`: the verified PMC and PCMC WGS84 municipal polygons described in [the Landsat pipeline](landsat_lst_pipeline.md). This is used to reconstruct the Step 9 grid and mask outside both municipalities.
3. Extracted **original Sentinel-2 Level-2A SAFE** directories below `data/raw/sentinel2/`. Each relevant SAFE must contain `MTD_MSIL2A.xml` and at least one granule with `IMG_DATA/R10m/*_B04_10m.jp2`, `*_B08_10m.jp2`, `IMG_DATA/R20m/*_B11_20m.jp2`, and `*_SCL_20m.jp2`. Keep SAFE names and metadata intact. Select acquisitions across March–May in the **same year** as LST, with coverage of both PMC and PCMC. Multiple neighboring tiles and dates are expected.

The workspace currently lacks these real inputs. The pipeline will stop before writing final rasters until they are supplied. Unit tests use artificial scenes in temporary directories and never write them to `data/processed/`.

Download one SAFE product at a time through [Copernicus Browser](https://browser.dataspace.copernicus.eu/) or the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/). Search the verified study boundary and March 1–May 31 of the chosen year. Choose Sentinel-2 **L2A**, review scene-level cloud cover, and download complete SAFE products, retaining all needed granules. The pixel-level mask below is still required. This script processes local SAFE files; it does not authenticate to or download from Copernicus or Earth Engine.

## Processing and equations

- SAFE XML supplies `BOA_QUANTIFICATION_VALUE` and each band's `BOA_ADD_OFFSET`. BOA reflectance is `(DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE`. Baseline 04.00+ products require the per-band offsets; a missing offset stops the run. Before that baseline, absent offsets mean zero. `DN=0`, nonfinite, and corrected reflectance outside `[0,1]` are excluded. Metadata details: [Copernicus processing baseline](https://documentation.dataspace.copernicus.eu/Data/Others/Sentinel2_L2A_baseline.html).
- SCL classes **4 vegetation** and **5 not vegetated** are accepted. No-data, defective, dark/shadow, water, unclassified, clouds, cirrus, and snow are excluded. This is a conservative land mask. SCL definitions: [Sentinel-2 processing](https://sentiwiki.copernicus.eu/web/s2-processing). Residual thin cloud and imperfect SCL labels remain possible.
- NDVI is `(B08 − B04) / (B08 + B04 + 1e-8)` on the **10 m** grid. Each final 30 m cell receives the mean of at least five of its nine clear 10 m index subpixels. Computing the index before aggregation retains within-cell variation. B04 and B08 are native 10 m bands.
- NDBI is `(B11 − B08) / (B11 + B08 + 1e-8)` on an aligned **20 m** grid. B11 and SCL are native 20 m; B08 is area-averaged from 10 m to 20 m. NDBI is then area-averaged to the **30 m** LST grid. This step uses geospatial reprojection because 20 m does not divide 30 m evenly; it requires at least 50% valid 20 m source coverage of a 30 m cell. B11 is never treated as original 10 m data. Band resolutions: [Copernicus Sentinel-2 products](https://sentiwiki.copernicus.eu/web/s2-products).
- Granules from the same acquisition date are mosaicked by first valid clear pixel so overlapping tiles do not count as independent dates. The March–May composite is the **pixelwise median across valid dates**. No optical values are invented to fill gaps.
- All processing is clipped to the municipal union. Final GeoTIFFs have the exact CRS, transform, dimensions, extent, and cell alignment of the LST reference. Sentinel-2's finer source resolution does **not** increase Landsat thermal resolution.

Both indices are unitless and should be within `[-1,1]`. A zero denominator is marked nodata. This QA range is a bound, not a claimed Pune measurement.

## Windows PowerShell

Run from the repository root. The install command uses the existing minimum geospatial dependencies.

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_sentinel2_indices.py' -v
```

After putting the real same-year LST raster, verified boundary, and complete extracted L2A SAFE directories at the paths above, use the matching acquisition year (2025 is only an example command):

```powershell
.\.venv\Scripts\python.exe .\scripts\build_sentinel2_indices.py --year 2025
```

If your input directories differ, run `--help` for `--scenes-dir`, `--boundary`, `--lst`, and `--output-dir` options. The script reports each index's measured min, max, mean, and percent nodata; it never prints assumed Pune values. To check that the output rasters have identical grids to LST:

```powershell
.\.venv\Scripts\python.exe -c "import rasterio; from pathlib import Path; p=Path('data/processed'); names=['lst_pune_30m.tif','ndvi_pune_30m.tif','ndbi_pune_30m.tif']; rasters=[rasterio.open(p/n) for n in names]; print([(r.crs.to_string(),r.res,r.shape,r.transform) for r in rasters]); print(all((r.crs,r.transform,r.shape)==(rasters[0].crs,rasters[0].transform,rasters[0].shape) for r in rasters)); [r.close() for r in rasters]"
```

The final line must be `True`. The run also fails before saving if either index has no valid pixels or values beyond its expected range.

## Outputs after a successful real-data run

- `data/processed/ndvi_pune_30m.tif` and `data/processed/ndbi_pune_30m.tif`: float32, unitless, EPSG:32643, 30 m, nodata = -9999.
- `data/processed/ndvi_pune_30m_valid_count.tif` and `data/processed/ndbi_pune_30m_valid_count.tif`: valid acquisition **dates** per grid cell.
- `data/processed/sentinel2_indices_pune_30m.json`: input metadata paths, date interval, accepted SCL classes, equations, and measured QA statistics.
- `data/processed/sentinel2_indices_pune_30m_maps.png`: masked NDVI/NDBI maps.
- `data/processed/sentinel2_indices_pune_30m_histograms.png`: in-boundary distributions.

## Interpretation and limitations

NDVI describes optical greenness, not canopy percentage. NDBI indicates SWIR/NIR contrast associated with built surfaces in some settings, but can also respond to bare soil. Neither index is a causal explanation of heat. A March–May optical median and a March–May daytime thermal median may summarize different clear days and viewing conditions; record exact seasons and valid-date counts before training. Cloud masking can leave residual errors and remove large cloudy areas. Reprojection and mixed pixels near roads, vegetation, and boundaries introduce uncertainty. More precise canopy and built-area features need separate land-cover or object extraction steps.
