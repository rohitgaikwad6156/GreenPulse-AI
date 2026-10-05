# Landsat source-quality audit: March-May 2025

This report checks local source identity, required files, MTL calibration, GeoTIFF readability and grids, and SHA-256 integrity. It does not calculate municipal temperature or establish municipal coverage.

| Date | Product ID | Satellite | Cloud Cover % | CRS | Resolution | Required Files | Validation Status |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| 2025-03-02 | `LC08_L2SP_147047_20250302_20250311_02_T1` | Landsat 8 | 2.19 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-03-10 | `LC09_L2SP_147047_20250310_20250311_02_T1` | Landsat 9 | 0 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-03-18 | `LC08_L2SP_147047_20250318_20250327_02_T1` | Landsat 8 | 0.05 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-03-26 | `LC09_L2SP_147047_20250326_20250327_02_T1` | Landsat 9 | 0 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-04-03 | `LC08_L2SP_147047_20250403_20250411_02_T1` | Landsat 8 | 9.1 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-04-11 | `LC09_L2SP_147047_20250411_20250412_02_T1` | Landsat 9 | 2.26 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-04-19 | `LC08_L2SP_147047_20250419_20250425_02_T1` | Landsat 8 | 0.35 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-04-27 | `LC09_L2SP_147047_20250427_20250428_02_T1` | Landsat 9 | 0.24 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |
| 2025-05-05 | `LC08_L2SP_147047_20250505_20250512_02_T1` | Landsat 8 | 0.15 | EPSG:32643 | 30 × 30 m | 4/4 | PASS |

## Totals

- Total scenes expected: **9**
- Total scenes found: **9**
- Total required files expected: **36**
- Total required files found: **36**
- Scenes passed: **9**
- Scenes failed: **0**
- Overall: **PASS**

Per-file SHA-256 values and raster dimensions are in the JSON and CSV reports. Scene cloud cover is an MTL scene-wide value; pixel QA and municipal coverage still require evaluation during the real pipeline.
