# GreenPulse AI — Data Card

**Status:** PRE-MODEL / PARTIALLY ACQUIRED

**Last reviewed:** 2026-10-05

**Purpose:** Document the provenance, processing, intended use, quality controls, and known limitations of data feeding the GreenPulse urban heat model.

This card documents real project sources and their intended processing. Fields that depend on the unfinished production pipeline remain explicitly unavailable. File presence alone is not evidence of a verified production dataset.

## Dataset summary

| Item | Contract and current status |
| --- | --- |
| Project and study area | GreenPulse AI; intended PMC + PCMC municipal extent. The combined verified production boundary is **PENDING**. |
| Primary target | `lst_c`: land-surface temperature (LST) in °C. LST is not pedestrian-level air temperature. |
| Intended first study period | 2025-03-01 to 2025-05-31. Confirm the actual period from real output metadata after the pipeline runs. |
| Analysis grid | 30 m × 30 m in EPSG:32643. This is an analysis grid, not native independent 30 m Landsat thermal sensing. |
| Unit of analysis | One QA-complete grid cell in the verified municipal extent, after exact target/predictor alignment. Real retained row count and coverage: **NOT AVAILABLE YET**. |
| First heat-map source gate | `municipal_boundary`, `landsat_lst_scenes`, `sentinel2_l2a_scenes`, `esa_worldcover`, `osm_roads`, as enforced by [the build script](../scripts/build_heat_map_pipeline.py). |

The broader [source manifest](../data/source_manifest.json) also labels some later-stage sources `required_mvp`. That label does not add WorldPop, wards, OSM green spaces, or the peri-urban reference to this first five-source build gate.

## First-build source inventory

Status, access dates, rights, and checksum evidence below reflect the current manifest and audits. **PENDING** means the record is incomplete; it is not an inferred value. Source-native CRS may vary and is checked before reprojection to the EPSG:32643 analysis grid.

| Source ID | Dataset / product | Role | Authority / organization | Acquisition / access date | Observation period | Native spatial resolution | Processing / output resolution | CRS | License / reuse status | Checksum status | Verification status | QA procedure | Known limitations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `municipal_boundary` | Verified PMC + PCMC outlines and combined polygon required | Clipping and modelling extent | **NOT YET RECORDED** for the missing PMC source; official PCMC outline staged | **PENDING** for combined import | Boundary effective/version date **NOT AVAILABLE YET** | Vector | 30 m municipal mask | Manifest: EPSG:4326 source | **NOT YET CONFIRMED** for combined source | **NOT AVAILABLE UNTIL VERIFIED IMPORT** | **PENDING**; PCMC staged, PMC missing, combined boundary unverified | Authority, geometry, CRS, provenance, checksum and extent validation before clipping | Boundary version and authority must fit the study; no municipal output can yet be accepted |
| `landsat_lst_scenes` | Landsat 8/9 Collection 2 Level-2 L2SP Surface Temperature | Observed `lst_c` target | USGS Earth Resources Observation and Science Center | 2026-10-05 recorded | Nine selected March–May 2025 scenes | Thermal sensing coarser than delivered ST grid (about 100 m native); delivered `ST_B10` 30 m | 30 m analysis grid | Source-native mixed; output EPSG:32643 | Public domain; retain USGS citation (manifest) | SHA-256 recorded for 36 required files | **VERIFIED**; 9/9 source and processing audits pass | MTL calibration; nonzero `ST_B10`; `QA_PIXEL` cloud/fill/cirrus/shadow/snow/water rejection; `QA_RADSAT` terrain-occlusion rejection; grid checks | Scene-footprint outliers require investigation; 30 m delivery does not add independent thermal detail |
| `sentinel2_l2a_scenes` | Sentinel-2 Level-2A SAFE products | NDVI and NDBI predictors | European Union Copernicus Programme / ESA | **PENDING** | Six selected products on 2025-03-14, 2025-04-13, 2025-05-10; tiles 43QCA and 43QDA | B04/B08 10 m; B11/SCL 20 m | Aggregated/aligned to 30 m LST grid | Source-native mixed; output EPSG:32643 | Copernicus Sentinel Data Legal Notice; free/full/open (manifest) | **PENDING** | **PENDING**; 0/6 SAFE products and 0/30 required file slots found in latest audit | SAFE/metadata and band checks; metadata-based reflectance scaling; SCL filtering; indices and alignment | No real Sentinel feature or coverage statistics are available; optical dates need not equal thermal dates |
| `esa_worldcover` | ESA WorldCover 2021 v200 | Tree-cover and built-up fractions | ESA WorldCover Consortium | 2026-09-19 recorded | 2021 land-cover snapshot | 10 m | Fraction of each 30 m cell | EPSG:4326 source; output EPSG:32643 | CC BY 4.0 (manifest) | SHA-256 recorded | **VERIFIED** source | Raster/CRS checks; area-weighted categorical class fractions | Tree class is a proxy, not a measured 2025 3D canopy inventory; built class is not exact roof or impervious fraction |
| `osm_roads` | OpenStreetMap road-network extract | Road-density predictor | OpenStreetMap contributors / OSM Foundation | 2026-09-19 recorded | Snapshot 2026-09-19 | Vector | Eligible mapped motor-road centreline length in each 900 m² cell, in km/km² | EPSG:4326 source; output EPSG:32643 | ODbL 1.0 with attribution (manifest) | SHA-256 recorded | **VERIFIED** source | Geometry and road-class filtering; intersection length normalized by cell area | Coverage and mapping completeness vary; zero mapped density does not establish absence of a physical road |

The Landsat source audit verifies nine scenes and 36 required files; its processing audit confirms QA masking and calibration over full scenes. The [extreme audit](landsat_extreme_audit.md) documents unusual QA-valid scene-footprint extremes without changing source values or production QA. No Pune, PMC, or PCMC temperature result follows from those full-scene diagnostics. See [source quality](landsat_quality_audit.md), [processing](landsat_processing_audit.md), and [extremes](landsat_extreme_audit.md). The [Sentinel intake audit](sentinel_quality_audit.md) remains FAIL/PENDING; its six selected products are recorded in [discovery](../data/provenance/discovery_2025.json).

## Supporting and later-stage sources

| Source ID | Role and provenance | Current status | Scope and limitation |
| --- | --- | --- | --- |
| `worldpop` | WorldPop / University of Southampton 2025 India unconstrained population counts, approximately 100 m; CC BY 4.0; accessed 2026-09-19; SHA-256 recorded | **VERIFIED** source | Exposure context, not one of the five first-profile predictors or five-source heat-map gate. Processed exposure is **PENDING REAL PIPELINE RUN**. |
| `ward_boundaries` | Ward reporting/UI; source authority, access date, license and checksum **PENDING** | **PENDING** | Separate from the municipal outline; not required to train the first cell-level model. |
| `osm_green_spaces` | OSM green-space context; ODbL recorded; source access date and checksum **PENDING** | **PENDING** | In the broader manifest, outside the first five-source build gate; OSM coverage can vary. |
| `periurban_lst_reference` | Same-season QA-valid Landsat reference for later Heat Hazard calibration; USGS public-domain source description in manifest | **PENDING**; access date/checksum **NOT AVAILABLE YET** | Separate from initial `lst_c` model training and the first five-source gate. Reference selection and non-overlap require verification. |

Optional `osm_buildings` and `measured_albedo`, plus future `municipal_sensor_observations`, are also listed in the manifest. Their pending records are not substitutes for the first-profile inputs. See the [intake contract](data_intake_contract.md).

## Processing and quality controls

**Implemented sequence:** source acquisition → provenance/checksum validation → per-scene Landsat LST calibration and QA → Sentinel BOA-scaled NDVI/NDBI and SCL QA → WorldCover/OSM predictors → exact 30 m grid alignment → complete-case ML grid → spatial block cross-validation. No synthetic values are substituted for missing production inputs.

Landsat uses per-scene MTL multiplier and offset on `ST_B10`, rejects invalid pixels with the existing `QA_PIXEL` and terrain-occlusion `QA_RADSAT` rules, and is designed to form a March–May pixelwise median plus valid-count raster after verified municipal clipping. It does **not** apply an arbitrary temperature clip. Sentinel expects B04 and B08 at 10 m, B11 and SCL at 20 m; metadata scaling and SCL filtering precede NDVI/NDBI calculation and 30 m alignment. See [Landsat](landsat_lst_pipeline.md) and [Sentinel](sentinel2_indices_pipeline.md).

| Control | Implemented procedure | Executed real-data evidence |
| --- | --- | --- |
| Source provenance and SHA-256 | Manifest/import validation records paths, identity, authority and hashes | Landsat, WorldCover, OSM roads and WorldPop verified; Sentinel and combined boundary **PENDING** |
| Raster metadata, CRS, resolution, alignment | Readability and grid checks; exact target/predictor alignment before table assembly | Landsat source/processing audits pass; aligned municipal grid **NOT AVAILABLE YET** |
| Cloud/quality masking and nodata | Landsat QA; Sentinel SCL; preserve invalid cells as nodata | Landsat audited; Sentinel scenes absent, so real Sentinel masking **NOT AVAILABLE YET** |
| Complete cases and impossible finite values | Reject missing target/features and impossible finite values without arbitrary LST clipping | Real retained-row count and coverage **NOT AVAILABLE YET** |
| Correlation/VIF and coverage map | Diagnostics for redundant predictors and geographic retention | **PENDING REAL PIPELINE RUN** |
| Saved audit trail and spatial folds | Source audits, dataset metadata, 5 km block assignment and fold metadata | Source audits exist; accepted real grid/fold artifacts **NOT AVAILABLE YET** |

The source verification state does not by itself certify a finished municipal raster or model table. See [morphology](urban_morphology_pipeline.md) and [ML dataset assembly](ml_dataset_pipeline.md).

## Known limitations and appropriate use

This dataset is intended for research analysis of seasonal urban land-surface patterns at the municipal grid scale after the source gate passes. It is not a current heat event map or a measure of 2 m air temperature. Landsat thermal information is coarser than the analysis grid; the March–May median mixes dates rather than describing an instantaneous event. Sentinel and Landsat clear observations may occur on different days. Cloud/QA gaps and complete-case filtering may create spatially uneven coverage and selection bias. WorldCover predates the thermal season by four years, and the OSM roads snapshot is from 2026. Municipal boundary authority/version and ward GIS remain unresolved. Tree, built, road and optical features are proxies and correlations; they do not establish causal heat drivers.

## Production dataset artifacts

| Artifact | Expected path | Current state | Populated from |
| --- | --- | --- | --- |
| ML grid | `data/processed/greenpulse_ml_grid.parquet` | File present locally, but associated metadata labels the grid **DEMO / SYNTHETIC DATA**; accepted real grid **NOT AVAILABLE YET** | Successful real five-source build and complete-case assembly |
| Grid metadata | `data/processed/metadata.json` | File present; explicitly says **DEMO / SYNTHETIC DATA**; real metadata **NOT AVAILABLE YET** | Real dataset build: period, CRS, resolution, features, rows and provenance |
| Spatial fold map | `data/processed/spatial_cv_blocks.parquet` | Legacy file present; accepted real fold map **NOT AVAILABLE YET** | Spatial CV assignment from accepted real grid |
| Spatial fold metadata | `data/processed/spatial_cv_metadata.json` | Legacy file present; accepted real fold metadata **NOT AVAILABLE YET** | Real 5 km block/five-fold run |

Do not copy row counts, coverage or feature distributions from the existing demo files into a real-data card. After the verified boundary and six SAFE products are acquired, rerun preflight and the documented [real heat-map pipeline](real_heat_map_pipeline.md), then replace placeholders only with accepted output evidence. The [final acceptance review](final_acceptance_review.md) records the current gate.
