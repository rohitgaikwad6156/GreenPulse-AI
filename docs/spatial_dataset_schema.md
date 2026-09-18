# GreenPulse AI spatial dataset schema

Status: design only, version 0.1. No data have been downloaded, fabricated, or processed for this specification.

Primary research reference: GreenPulse_AI_Research_Symbols_Cleaned.pdf, especially the variable inventory, hybrid grid/ward strategy, source inventory, continuous LST target, and spatial validation sections (pages 30–52). Candidate sources named below still require an availability, license, coverage, and quality audit before use.

## 1. What one row means

- Spatial unit: one fixed 30 m × 30 m square grid cell. The grid is built in EPSG:32643 (UTM zone 43N); centroid latitude/longitude are transformed to EPSG:4326.
- Temporal unit: one eligible daytime Landsat LST observation date. If multiple scenes cover the same cell on one date, they must be resolved into one documented composite before creating a row.
- Primary key: (grid_id, observation_date). grid_id never changes between dates. The same cell can appear on several dates.
- Target: lst_c, observed satellite land surface temperature in degrees Celsius. No 0–100 risk score is an ML target.
- Training table: only rows with a quality-accepted lst_c are eligible. Cells with masked LST remain in the grid and interim layers as no-data, not as zero-temperature training examples.
- Final reporting unit: a verified PMC or PCMC ward. Ward summaries are calculated after cell-level analysis.
- Geometry: full, uncut 900 m² grid squares in EPSG:32643. Study-area and ward intersections are handled by masks and overlap weights, so border cells do not silently change shape.

The 30 m spacing is an analysis grid. Landsat thermal observations have a coarser native footprint, although the delivered product is gridded at 30 m. Adjacent 30 m LST values are therefore not independent 30 m thermometer readings. LST is surface skin temperature, not 2 m pedestrian air temperature.

## 2. Planned files and directory responsibilities

No files listed in this table are data files created by this step. Names are the planned output contract for later ingestion work.

| Directory / planned file | Purpose | Mutation rule |
| --- | --- | --- |
| data/raw/landsat/, sentinel2/, worldcover/, osm/, dem/, population/, wards/ | Original downloaded rasters, vectors, and source metadata | Keep source bytes unchanged; record URL, acquisition time, license, checksum, product version, and download date. Create subfolders only when obtaining a verified source. |
| data/raw/stations/ | Optional point observations for air temperature, humidity, and AQI | Store only if access and spatial/temporal coverage are verified. |
| data/interim/ | Cloud-masked, reprojected, clipped, and date-aligned working layers | Regenerable from raw inputs; preserve no-data masks and provenance. |
| data/processed/grid_cells.geoparquet | One row per permanent 30 m cell: grid_id, geometry, coordinates, primary ward assignment, static features | Versioned output; no LST target. |
| data/processed/grid_observations.parquet | One row per grid_id × observation_date: LST, date-matched spectral values, source identifiers, and quality information | Versioned output; masked values remain NULL. |
| data/processed/ml_grid_table.geoparquet | Materialized join with the complete dictionary below, including geometry and target-present rows | Candidate ML input; no model training in this step. |
| data/processed/grid_ward_overlap.parquet | grid_id, ward_id, intersection_area_m2, and overlap weight | Reporting crosswalk; a border cell may contribute to more than one ward. |
| data/processed/ward_boundaries.geoparquet | Verified ward_id, ward_name, municipality, boundary version, and polygon | Reporting geometry; never an ML predictor. |
| data/processed/source_manifest.json and quality_report.json | Product versions, date rules, CRS, masks, coverage, and rejected-row counts | Required provenance and QA artifacts. |

The existing data/boundaries/ directory may hold a clearly identified working copy of verified ward files. Original downloads belong in data/raw/wards/; normalized boundaries belong in data/processed/. The existing data/demo/ directory remains separate and must be labeled DEMO DATA if ever used.

## 3. Data dictionary conventions

Roles: Target = observed value the ML model will learn; Feature = candidate predictor; Metadata = identity, provenance, validation grouping, or reporting field. "Optional" means no invented substitute if the source is absent. A field can be stored as metadata for decision support without entering the default LST model.

Ranges below are admissible domains or QA expectations, not measured Pune/PCMC results. "Finite" means no fixed local bound is asserted before inspecting genuine data. NULL means an actual missing value, never a fabricated zero. Source resolution describes the original information content; every value is aligned to a 30 m output cell later.

The default candidate LST feature set is ndvi, ndbi, tree_canopy_pct, built_pct, albedo, road_density, distance_green_m, elevation_m, ndvi_mean_3x3, ndvi_mean_5x5, ndbi_mean_3x3, and ndbi_mean_5x5. This is a schema-level candidate list, not a fitted model. A feature without a defensible source or adequate coverage must be omitted with the reason recorded before training; in particular, cool-roof simulation must wait for a documented albedo/roof-response method rather than filling albedo with a guess.

### 3.1 Identity, location, and provenance

| Variable and type | Role | Meaning and why it is kept | Unit and admissible range | Proposed source and source resolution | Missing-value handling |
| --- | --- | --- | --- | --- | --- |
| grid_id: string | Metadata | Stable cell identifier; joins geometry, dates, predictions, and ward reports. It is not an ML feature. | Nonempty unique identifier per cell; no physical unit. | Deterministic 30 m EPSG:32643 grid; 30 m cell. | Never NULL; reject duplicate or missing IDs. |
| observation_date: date | Metadata | Date of the LST observation; prevents mixing seasons and supports later temporal checks. Not an ML feature by default. | Valid ISO date; no numeric range. | Landsat product acquisition metadata; scene-level date. | Never NULL in the observation/training table. |
| latitude: float64 | Metadata | WGS84 latitude of the cell centroid for map display and source checks; not a default predictor. | Degrees north, −90 to 90; must lie within verified study extent. | Derived from the 30 m grid via EPSG:4326 transform; 30 m centroid spacing. | Recompute from geometry; never impute. |
| longitude: float64 | Metadata | WGS84 longitude of the cell centroid for map display and source checks; not a default predictor. | Degrees east, −180 to 180; must lie within verified study extent. | Derived from the 30 m grid via EPSG:4326 transform; 30 m centroid spacing. | Recompute from geometry; never impute. |
| x: float64 | Metadata | EPSG:32643 easting of centroid; used for distances, grid alignment, and spatial blocks. Not a default predictor. | Metres, finite and inside verified projected extent. | Derived from the 30 m projected grid; 30 m centroid spacing. | Recompute from geometry; never impute. |
| y: float64 | Metadata | EPSG:32643 northing of centroid; same purpose as x. Not a default predictor. | Metres, finite and inside verified projected extent. | Derived from the 30 m projected grid; 30 m centroid spacing. | Recompute from geometry; never impute. |
| geometry: polygon | Metadata | The full 30 m square used for geospatial joins and maps; not a predictor. | EPSG:32643 polygon with 900 m² nominal area. | Generated grid; 30 m × 30 m. | Never NULL or invalid; repair the grid construction rather than impute. |
| ward_id: string | Metadata | Primary ward assignment for cell lookup; kept out of the LST model. Prefix or otherwise qualify IDs so PMC and PCMC codes cannot collide. | Verified identifier; no physical unit. | Official PMC/PCMC ward polygons; vector boundaries, variable mapping precision. | NULL if boundaries are missing or assignment is ambiguous; exclude from ward reports until resolved. |
| ward_name: string | Metadata | Human-readable ward label for the dashboard; not an ML feature. | Verified text label. | Same ward boundary attributes as ward_id; ward polygon scale. | NULL when ward_id is NULL; never infer a name from location text. |
| lst_source_id: string | Metadata | Traceable Landsat scene or composite identifier; helps reproduce each target row. | Nonempty source identifier. | Landsat 8/9 Level-2 product metadata; scene/composite level. | Required whenever lst_c is present; otherwise NULL only in interim no-data records. |
| optical_window_start: date | Metadata | Start date of optical imagery used for NDVI/NDBI, making temporal matching auditable. | Valid date no later than optical_window_end. | Sentinel-2 Level-2A metadata; scene/composite date range. | NULL when no optical source is available; dependent indices then NULL. |
| optical_window_end: date | Metadata | End date of the optical composite; must not be later than observation_date for a prospective-prediction dataset. | Valid date from start through observation_date. | Sentinel-2 Level-2A metadata; scene/composite date range. | NULL with optical_window_start when unavailable; no silent future-date fill. |
| spatial_block_id: string | Metadata | Groups nearby cells for later spatial block cross-validation; never supplied as a model feature. All dates of one grid_id stay in the same block. | Nonempty tile identifier; no physical unit. | Derived from x/y using a fixed projected block layout; provisional 5 km × 5 km blocks from the research. | Recompute from coordinates; never impute. |

### 3.2 Target and core physical predictors

| Variable and type | Role | Meaning and why the LST model may need it | Unit and admissible range | Proposed source and source resolution | Missing-value handling |
| --- | --- | --- | --- | --- | --- |
| lst_c: float32 | Target | Observed daytime land surface skin temperature. This is the continuous physical quantity to predict. | °C; finite and above absolute zero. No invented Pune-specific min/max. | Landsat 8/9 Level-2 Surface Temperature; thermal sensor footprint about 100 m, delivered on a 30 m grid. | Cloud, shadow, invalid-quality, or absent target = NULL; exclude that row from training, never fill from nearby LST. |
| ndvi: float32 | Feature | Vegetation greenness from (NIR − red)/(NIR + red); candidate cooling-related surface predictor. | Unitless, −1 to 1. | Sentinel-2 L2A B8/B4; 10 m bands, aggregated to the 30 m cell. | NULL for cloud/shadow, invalid reflectance, or near-zero denominator; future model missing-value treatment stays inside training folds. |
| ndbi: float32 | Feature | Built-up spectral contrast from (SWIR − NIR)/(SWIR + NIR); candidate surface-material predictor, not a measured impervious fraction. | Unitless, −1 to 1. | Sentinel-2 L2A B11/B8; effective source detail limited by the 20 m SWIR band, then aggregated to 30 m. | NULL for invalid optical inputs or denominator; do not substitute built_pct or zero. |
| tree_canopy_pct: float32 | Feature | Percentage of cell classified as tree cover; candidate vegetation/shade proxy. With WorldCover it is a tree-cover class fraction, not measured crown volume or mature shade. | Percent of cell area, 0 to 100. | Candidate: ESA WorldCover tree-cover class at 10 m, or verified municipal canopy polygons if available. | NULL if source vintage or class mask is unavailable; 0 only when source coverage confirms no tree class. Record method in source manifest. |
| built_pct: float32 | Feature | Percentage classified as built-up; candidate urban morphology proxy. WorldCover built-up is not identical to sealed/impervious area. | Percent of cell area, 0 to 100. | Candidate: ESA WorldCover built-up class at 10 m; later a verified impervious map may replace it. | NULL when classification coverage is missing; 0 only when valid mapping confirms no built-up class. |
| albedo: float32 | Feature | Estimated broadband surface reflectance, relevant to solar heating and future cool-roof scenarios. It is not directly supplied by an arbitrary slider. | Fraction, 0 to 1. | Candidate: documented broadband conversion from Landsat 8/9 Level-2 surface-reflectance bands; 30 m reflectance inputs. | NULL until a documented conversion and QA procedure is chosen; do not invent values or infer albedo directly from NDBI. |
| road_density: float32 | Feature | Mapped road-centreline length per unit area in a centred 150 m × 150 m neighborhood; captures nearby paved-network morphology, not traffic flow. | km of road/km², 0 or greater; no fixed upper bound. | OpenStreetMap road lines, vector mapping of variable completeness; aggregated to the stated window. | NULL where the road extract is incomplete/unavailable; 0 only after confirming complete coverage of that window. |
| distance_green_m: float32 | Feature | Euclidean distance from cell centroid to the nearest mapped qualifying park/green polygon edge; captures nearby green-space context, not park quality. | Metres, 0 or greater; 0 inside a qualifying polygon. | OSM parks/green polygons or verified municipal green-space polygons; vector mapping of variable completeness. | NULL if no trusted green-space inventory covers the search region; do not use an arbitrary large distance. |
| elevation_m: float32 | Feature | Surface elevation; controls broad terrain-related temperature variation. | Metres above the DEM vertical datum; finite, with study-area QA bounds set after inspection. | SRTM or NASADEM candidate noted in the research; nominal 30 m DEM. | NULL for DEM voids or invalid cells; any fill method must be documented and fitted without target information. |
| population_density: float32 | Metadata (exposure) | Estimated residential population density for ward prioritization and exposure reporting. It is not a default physical LST predictor. | People/km², 0 or greater; no fixed upper bound. | WorldPop population count grid, about 100 m. Transfer counts conservatively before converting to density; do not imply 30 m census detail. | NULL for unavailable year/coverage; never treat missing as zero population. |

### 3.3 Spatial context predictors

The windows are centred on the cell and include it. A 3×3 window covers 90 m × 90 m; a 5×5 window covers 150 m × 150 m on the analysis grid. Compute means from same-date valid source cells, including context just outside municipal boundaries when available. A provisional minimum is 5/9 valid cells for 3×3 and 13/25 for 5×5; below that, store NULL. The final threshold must be frozen before model evaluation and reported in the quality report.

| Variable and type | Role | Meaning and why the LST model may need it | Unit and admissible range | Proposed source and source resolution | Missing-value handling |
| --- | --- | --- | --- | --- | --- |
| ndvi_mean_3x3: float32 | Feature | Local 90 m greenness context; captures nearby vegetation beyond the central cell. | Unitless, −1 to 1. | Focal mean of aligned NDVI grid; underlying Sentinel-2 NIR/red 10 m, output 90 m window. | NULL if fewer than 5 valid cells; never compute from LST. |
| ndvi_mean_5x5: float32 | Feature | Wider 150 m greenness context and potential neighborhood cooling influence. | Unitless, −1 to 1. | Focal mean of aligned NDVI grid; underlying 10 m optical source, output 150 m window. | NULL if fewer than 13 valid cells; never substitute 3×3 mean. |
| ndbi_mean_3x3: float32 | Feature | Local 90 m built-up spectral context. | Unitless, −1 to 1. | Focal mean of aligned NDBI grid; underlying SWIR detail about 20 m, output 90 m window. | NULL if fewer than 5 valid cells. |
| ndbi_mean_5x5: float32 | Feature | Wider 150 m built-up context. | Unitless, −1 to 1. | Focal mean of aligned NDBI grid; underlying SWIR detail about 20 m, output 150 m window. | NULL if fewer than 13 valid cells. |

### 3.4 Optional context and action-planning columns

Optional point observations must retain sensor identity, observation time, and source quality in the raw/interim records. They are not automatically spread across the grid. The default LST training feature list excludes air_temp_c, humidity_pct, aqi, population_density, and roof_fraction; their uses below are validation, context, exposure, or intervention feasibility. A later model change must document and spatially validate any decision to include them.

| Variable and type | Role | Meaning and why it is kept | Unit and admissible range | Proposed source and source resolution | Missing-value handling |
| --- | --- | --- | --- | --- | --- |
| air_temp_c: float32 | Optional metadata | Measured near-surface air temperature for separate point-based assessment of human conditions. It is not ground truth for satellite LST. | °C; finite and above absolute zero, with source QA bounds. | Verified IMD/municipal sensor or field logger; sparse point location and timestamp, not 30 m coverage. | Usually NULL; populate only for defensibly located and time-matched cell observations. Never interpolate citywide by default. |
| humidity_pct: float32 | Optional metadata | Relative humidity at a verified station, relevant to separate heat-stress analysis, not core LST regression. | Percent, 0 to 100. | Verified IMD/municipal sensor; sparse point location and timestamp. | Usually NULL; no ward-wide copy or invented interpolation. |
| aqi: float32 | Optional metadata | Reported air-quality index for separate context; it is not a direct surface-temperature measurement. | Unitless, 0 or greater; valid upper bound and averaging time follow the documented source standard. | Verified CPCB/SAFAR/MPCB or other audited station feed; sparse point and reporting period. | Usually NULL; do not convert a station value into a 30 m field without a separately validated method. |
| roof_fraction: float32 | Optional metadata / optimizer input | Mapped building-roof footprint area divided by cell area; candidate upper-bound proxy for a cool-roof action, not proof that roofs are suitable or accessible. | Fraction, 0 to 1. | OSM or municipal building footprints; vector completeness and positional accuracy vary. | NULL if footprint completeness is unknown; 0 only with verified complete mapping and no roofs. |
| lulc_class: string | Optional feature | Dominant land-cover class may capture surface type not fully represented by spectral indices. Category codes must follow one documented legend and vintage. | Valid category from selected product legend; no numeric range. | Candidate: ESA WorldCover 10 m or a verified municipal LULC product; do not mix their taxonomies. | NULL if unmapped/ambiguous; never guess a category. Encode only inside future training folds. |

## 4. Data alignment and leakage rules

1. Mask cloud, cloud shadow, saturation, and invalid thermal/optical pixels using each source product's QA fields before aggregation. Preserve no-data as NULL.
2. Align sources in EPSG:32643 on one snapped 30 m grid. Use appropriate methods: continuous variables by documented averaging/resampling, class fractions by area/count of valid source pixels, vectors by geometric overlay. A finer output grid never upgrades native information content.
3. Anchor each row to observation_date. Prefer same-date optical data; otherwise use a predeclared, audited prior-date window. Store the actual optical window. Never use imagery dated after the target for a prospective prediction record.
4. Match annual WorldCover, DEM, population, OSM, and boundary vintages explicitly in the manifest. Do not assign a later urban land-cover state to an earlier target without acknowledging the temporal mismatch.
5. Do not derive predictors from lst_c, model residuals, SHAP output, post-intervention outcomes, or a 0–100 risk score. Coordinates, ward IDs, source IDs, and spatial_block_id remain metadata, not default predictors.
6. Build neighborhood features from predictors only. Adjacent blocks may share neighborhood context; spatial validation must hold out complete blocks and consider a boundary buffer if strict geographic transfer is claimed. Repeated dates for one grid_id must remain in the same geographic fold.
7. Do not pre-impute predictor values from the full study table before spatial cross-validation. Any later imputer or category encoder must be fitted inside each training fold. The processed dataset preserves observed NULLs.

## 5. Ward reporting contract

Use verified, versioned PMC and PCMC polygons. For each grid cell/ward intersection, store area a(g,w) in m² and overlap weight a(g,w)/900. A cell crossing a boundary can contribute to both wards. Keep ward_id in the main row as a convenient primary label only; use the overlap table for authoritative ward summaries.

For a valid temperature field T(g) on an observation date, ward mean LST is:

T_ward = sum over valid g of [a(g,w) × T(g)] / sum over valid g of a(g,w).

Report the valid observed area and coverage fraction with the result. Observed LST, predicted LST, and simulated LST must be separate fields/views later. No ward heat score, action recommendation, or accuracy statistic is generated in this schema step. Because neighboring 30 m LST cells can share the same coarser thermal information, do not treat cell count as independent sample size for uncertainty.

## 6. Acceptance checks before any ML step

- Exactly one record per (grid_id, observation_date) in the materialized table; one valid geometry per grid_id.
- Grid squares align to one 30 m projected lattice; x/y agree with geometry centroids, and latitude/longitude agree with coordinate transformation.
- Target and feature domains above pass checks. Out-of-range or invalid QA values become rejected/NULL with counts in the quality report, never silently clipped into invented values.
- Landsat target date, optical windows, and static-source vintages are traceable; no future optical imagery enters a prospective row.
- Confirm valid-area coverage by date, municipality, ward, and source. Missingness is reported separately from genuine zero values.
- Ward polygons have a documented vintage and no unresolved overlaps/gaps in the intended reporting area. Overlap areas never exceed a 900 m² cell beyond numerical tolerance.
- The source manifest identifies whether tree_canopy_pct and built_pct are land-cover proxies; albedo remains NULL until its derivation is documented.
- No model fitting, model metrics, sensor calibration, or environmental conclusions follow from this document alone.
