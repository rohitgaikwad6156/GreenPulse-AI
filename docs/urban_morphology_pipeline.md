# Step 11: real urban morphology features

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** This step aligns measured/source-derived features to the existing **30 m × 30 m PMC/PCMC LST grid**. It performs no ML training and contains no assumed Pune feature values.

## Inputs and where to put them

| Input | Required path | Meaning and source |
|---|---|---|
| LST grid reference | `data/processed/lst_pune_30m.tif` | Real Step 9 output. Its CRS, transform, extent, and shape define every output raster. |
| Municipal boundary | `data/boundaries/pmc_pcmc.geojson` | Verified PMC/PCMC WGS84 polygons used by Step 9. |
| ESA WorldCover | `data/raw/worldcover/` | Original 2021 v200 10 m `*_Map.tif` tiles covering both municipalities. Download only the needed tiles from [ESA WorldCover data access](https://esa-worldcover.org/en/data-access). |
| OSM roads | `data/raw/osm/roads.geojson` | WGS84 GeoJSON FeatureCollection with `highway` tags and LineString/MultiLineString geometry. Export from [OpenStreetMap](https://wiki.openstreetmap.org/wiki/Download), for example through OSMnx or Overpass, with coverage of the full study boundary. |
| OSM green spaces | `data/raw/osm/green_spaces.geojson` | WGS84 GeoJSON polygons with `leisure=park/garden`, `landuse=forest/grass/recreation_ground`, or `natural=wood/grassland`. Include a buffer **outside** PMC/PCMC so edge cells can find their nearest mapped green space. |
| WorldPop | `data/raw/worldpop/india_population_counts.tif` | A documented WorldPop **population counts** GeoTIFF, with people per source pixel, preferably the year closest to LST. WorldPop's [India population-count catalogue](https://hub.worldpop.org/project/categories?id=3) lists the source year, resolution, version, and whether counts are constrained. The local filename is just a convenient alias; record the exact original dataset citation and year. |
| Optional OSM buildings | Give `--osm-buildings` a path | WGS84 polygons with a `building` tag. Use only after checking inventory completeness. |

No input above is currently present in this workspace. The command will stop before creating real feature rasters. Test data live only in temporary test directories.

## Grid, definitions, and resampling

All distances, lengths, and areas use **EPSG:32643 (UTM zone 43N), metres**, the same projected CRS as the LST grid. Every output has exactly the LST raster's 30 m transform, dimensions, CRS, and extent. Cells outside the verified municipal polygons are nodata.

| Output layer | Calculation | Unit | Resampling/aggregation |
|---|---|---|---|
| `tree_canopy_pct` | `100 × ESA WorldCover tree-cover class 10 area / valid source area` | % of valid 10 m subpixels | WorldCover categories use **nearest neighbour** to an aligned 10 m grid; count class 10 among nine 10 m subpixels per 30 m cell. At least five valid subpixels required. |
| `built_pct` | `100 × ESA WorldCover built-up class 50 area / valid source area` | % of valid 10 m subpixels | Same categorical nearest-neighbour procedure. This is **built-up land cover**, not a roof-footprint fraction. |
| `road_density` | Sum of unique mapped motor-road centreline length clipped to each 900 m² cell, divided by 900 m² | km/km² | Vector intersection in UTM; no categorical raster resampling. Footways and cycleways are excluded. |
| `distance_green_m` | Distance from the 30 m cell **centre** to nearest mapped OSM green polygon boundary/interior | m | Vector nearest-neighbour geometry query in UTM; zero for a centre inside a mapped green polygon. It is Euclidean distance, not walking distance or cooling reach. |
| `population_density` | If source is counts: source people/pixel divided by source pixel's actual area; if source is already density: use its stated people/km² values | people/km² | **Bilinear** reprojection of this continuous density field to the 30 m grid. WGS84 count-pixel areas are geodesic; EPSG:32643 count-pixel areas are planar. No new 30 m population information is created. |
| `building_fraction` (optional) | Union of OSM mapped building-footprint polygons intersected with each cell / 900 m² | fraction 0–1 | Vector area intersection in UTM. Kept optional to avoid adding a potentially incomplete and correlated near-duplicate of `built_pct`. |

ESA WorldCover [2021 v200](https://esa-worldcover.org/en/about/about) is a **2021 land-cover snapshot**, not a current canopy census or an annually refreshed 2025 map. Its class 10 is a **tree-cover proxy**, not a measured 3D crown-canopy percentage. Class 50 is a broad built-up cover category, not a complete impervious-surface measurement. The source classes and 10 m grid are described in the [WorldCover product manual](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PUM_V2.0.pdf).

WorldPop count products are commonly around 100 m and may be modelled estimates rather than census observations at each source pixel. The output 30 m cells inherit a smooth density surface, and neighbouring values should not be treated as independent observations. Check the actual WorldPop product's units: **people per pixel** and **people/km²** are different. OSM completeness varies; a zero road density means no mapped eligible road in a cell, not proof that no physical road exists.

## Windows PowerShell run

From the repository root, once the real inputs above exist:

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_urban_morphology.py' -v
.\.venv\Scripts\python.exe .\scripts\build_urban_morphology.py --worldpop .\data\raw\worldpop\india_population_counts.tif --worldpop-kind counts
```

If using a WorldPop **density** GeoTIFF with documented people/km² units, use its actual path and `--worldpop-kind density`. For optional OSM buildings, add `--osm-buildings` and its actual GeoJSON path. Run `--help` to see every path option. Do not relabel a count raster as density: it changes units by orders of magnitude.

## Outputs and checks

Separate aligned intermediate layers are saved under `data/interim/morphology/`:

- `tree_canopy_pct_pune_30m.tif`
- `built_pct_pune_30m.tif`
- `road_density_pune_30m.tif`
- `distance_green_m_pune_30m.tif`
- `population_density_pune_30m.tif`
- `building_fraction_pune_30m.tif` only if requested
- `worldcover_valid_subpixels_pune_30m.tif` as a coverage QA layer
- `morphology_qc.json` with source paths and measured min/max/mean/nodata percentage
- `morphology_qc_maps.png` and `morphology_qc_histograms.png`

All feature layers are float32 GeoTIFFs with `-9999` nodata. The script validates physical ranges and stops if any required feature has no valid cells inside PMC/PCMC. The map and histograms are generated **only after a successful real-data run**. Compare their edges with the LST/NDVI maps and review the WorldCover valid-subpixel layer; source seams and low-coverage cells need investigation.

To check exact alignment:

```powershell
.\.venv\Scripts\python.exe -c "import rasterio; from pathlib import Path; p=Path('data/interim/morphology'); a=rasterio.open('data/processed/lst_pune_30m.tif'); names=['tree_canopy_pct','built_pct','road_density','distance_green_m','population_density']; rasters=[rasterio.open(p/(n+'_pune_30m.tif')) for n in names]; print(all((r.crs,r.transform,r.shape)==(a.crs,a.transform,a.shape) for r in rasters)); [r.close() for r in rasters]; a.close()"
```

The result must be `True`. The unit tests also exercise categorical fractions, metric vector length/area/distance, WorldPop count-to-density conversion, and output georeferencing using **artificial fixtures** only.
