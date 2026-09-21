# Step 12: assemble the real GreenPulse ML grid

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System.** This step creates a table with **one row per 30 m × 30 m cell** and a continuous observed **land surface temperature target, `lst_c` in °C**. It performs no ML training. LST is land skin temperature, not pedestrian air temperature.

The project currently has **no real LST, NDVI/NDBI, morphology rasters, or verified ward boundaries**, so the real Parquet and metadata cannot yet be generated. WorldCover, WorldPop, and OSM roads are locally verified inputs but cannot produce the dependent grid alone. Tests use temporary **ARTIFICIAL TEST FIXTURES** and never save synthetic rows to the real processed-data paths.

## Required inputs

All rasters must be single-band float32 GeoTIFFs with a declared nodata value and exactly the **same EPSG:32643 CRS, 30 m resolution, affine transform, width, height, and extent** as the real Step 9 LST raster. This step does **not** silently reproject or resample misaligned sources. [Rasterio georeferencing documentation](https://rasterio.readthedocs.io/en/stable/topics/georeferencing.html) explains why CRS and transform jointly define the grid.

| Field | Required file |
|---|---|
| `lst_c` | `data/processed/lst_pune_30m.tif` |
| `ndvi`, `ndbi` | `data/processed/ndvi_pune_30m.tif`, `data/processed/ndbi_pune_30m.tif` |
| Valid-observation QA | Corresponding `lst_pune_30m_valid_count.tif`, `ndvi_pune_30m_valid_count.tif`, `ndbi_pune_30m_valid_count.tif` |
| `tree_canopy_pct`, `built_pct`, `road_density`, `distance_green_m`, `population_density` | Separate `data/interim/morphology/<field>_pune_30m.tif` files from Step 11 |
| Source provenance | `data/interim/morphology/morphology_qc.json` from Step 11 |
| Municipality outline | `data/boundaries/pmc_pcmc.geojson`, the same verified outline used for the LST grid |
| Wards | `data/boundaries/pmc_pcmc_wards.geojson`, a **verified** WGS84 GeoJSON FeatureCollection with polygon features for both municipalities. Every feature requires `properties.municipality` (`PMC` or `PCMC`), `properties.ward_id`, and `properties.ward_name`. Record its issuing authority and boundary version outside the table. |
| Optional `albedo` | Explicit `--albedo` GeoTIFF, only after a documented, QA-masked derivation. It must have a `source` tag and the **same March–May period tag** as LST. No guessed albedo values are inserted. |

The LST, NDVI, and NDBI raster `period` tags must all be identical and exactly `YYYY-03-01/YYYY-05-31`. The current pipeline is a **single seasonal composite table**, not a per-observation-date time series. Temporal changes or a future-year prediction dataset require a separate design with explicit dates; do not use later imagery for prospective claims.

## Assembly rules

1. Validate all raster grid definitions and declared nodata before reading values. Build the municipal cell mask from the verified outline.
2. Read each raster in row chunks. Treat its nodata as missing. For LST, NDVI, and NDBI, a zero valid-count pixel is also missing: this removes QA-rejected thermal/optical pixels, including upstream cloud-masked pixels. The source QA processing remains in Steps 9–10.
3. Reject **impossible finite values** rather than clipping them: LST must be above absolute zero; NDVI/NDBI and their focal means must lie in `[-1,1]`; cover percentages in `[0,100]`; albedo in `[0,1]`; distances, road density, and population density must be nonnegative. No arbitrary Pune temperature cutoff is imposed.
4. Calculate `ndvi_mean_3x3`, `ndbi_mean_3x3` with at least **5/9** valid grid cells, and `ndvi_mean_5x5`, `ndbi_mean_5x5` with at least **13/25**. Focal windows include the central cell and use neighbouring predictor values only. Outside-municipality optical cells were already masked by Step 10, so border windows can have more missing context.
5. Assign a ward where exactly one verified ward polygon contains the grid-cell centre. Use a qualified ID such as `PMC:12` or `PCMC:12`; both can have a raw ward `12`. Unassigned or overlapping ward centres are excluded and counted. A later ward aggregation should use **area-weighted cell/ward overlaps** for boundary-crossing cells rather than treating this primary centre label as an exact area split.
6. Generate the fixed `grid_id` from the 30 m UTM lattice, compute x/y at the cell centre, and transform that centre to WGS84 latitude/longitude. IDs and coordinates are **metadata**, not default ML predictors.
7. Apply a **complete-case policy** for this first table: keep a cell only if LST, every required feature (including focal means and population density), and a unique ward assignment are present. Do not impute, replace missing with zero, or substitute DEMO DATA. Missing counts for each source and sequential exclusions are recorded before rows are dropped. This policy can reduce coverage and create spatial selection bias; inspect the counts and map retained cells before training.
8. Calculate Pearson correlations on retained features and flag pairs with `|r| ≥ 0.85`. Also report variance inflation factors above 5 as a multicollinearity screen. These are descriptive; no predictors are automatically dropped, and neither correlation nor VIF proves a causal temperature driver. Correlated NDVI/canopy or NDBI/built-up variables may split future model attribution.
9. Write a complete-case coverage map distinguishing retained cells, missing LST, missing predictors, and unassigned/ambiguous wards. Metadata records overall and per-ward retention percentages so spatial selection bias is visible rather than hidden by a single final row count. Grid IDs are generated once from unique raster row/column positions and the output reports zero duplicates.

`population_density` is included because this Step 12 request lists it among features. It remains a coarser, modelled exposure estimate, and the choice to use it as an LST predictor should be revisited during spatial validation. Optional albedo is **omitted as a column** when no defensible source is provided.

## Windows PowerShell commands

Run from the repository root. The first command installs the Parquet writer in addition to existing raster dependencies; [Apache Arrow](https://arrow.apache.org/docs/python/parquet.html) provides the Parquet implementation.

```powershell
Set-Location 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-data.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_ml_dataset.py' -v
```

After the **real** input files above are in place:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_ml_dataset.py
```

To include an independently documented albedo raster, add `--albedo` with that raster's actual absolute or repository-relative path. To skip the optional CSV sample, add `--csv-sample-rows 0`. The script prints its measured row count, date range, and the numbers of correlation/VIF flags. It stops with a precise missing-input or validation error if source data are absent.

## Outputs after a successful real-data run

- `data/processed/greenpulse_ml_grid.parquet`: one row per retained 30 m cell, target plus requested features and metadata. The Parquet file has no geometry column; `grid_id` and coordinates link it to the raster grid and wards. [Pandas/Arrow Parquet documentation](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_parquet.html) describes the format.
- `data/processed/metadata.json`: CRS, 30 m resolution, March–May date range, all source layer paths and tags, original morphology provenance, row count, per-column missing counts, sequential rejection counts, ward ambiguity, missing-data policy, correlations, VIF, and scientific cautions.
- `data/processed/greenpulse_ml_correlations.png`: feature-correlation QC plot.
- `data/processed/greenpulse_ml_coverage.png`: complete-case retention/exclusion map for spatial selection-bias review.
- `data/processed/greenpulse_ml_grid_sample.csv`: up to 200 retained rows by default, solely for manual inspection. The Parquet is the authoritative table.

Expected table columns are `grid_id`, `x`, `y`, `latitude`, `longitude`, `ward_id`, `ward_name`, `lst_c`, `ndvi`, `ndbi`, `tree_canopy_pct`, `built_pct`, `road_density`, `distance_green_m`, `population_density`, `ndvi_mean_3x3`, `ndvi_mean_5x5`, `ndbi_mean_3x3`, `ndbi_mean_5x5`, plus `albedo` only when supplied.

After a successful run, inspect the table and metadata with:

```powershell
.\.venv\Scripts\python.exe -c "import pyarrow.parquet as pq; p=pq.ParquetFile('data/processed/greenpulse_ml_grid.parquet'); print(p.metadata.num_rows); print(p.schema_arrow.names)"
Get-Content .\data\processed\metadata.json -TotalCount 35
```

Never report test-fixture row counts, correlations, or maps as Pune results. No model accuracy, R², RMSE, or intervention effect is calculated in this step.
