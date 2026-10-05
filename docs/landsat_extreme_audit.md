These are full-scene diagnostic observations and are not Pune, PMC, or PCMC temperature results.

# Landsat 2025 full-scene extreme audit

All statistics use QA-valid source pixels on original scene grids. Thresholds below are diagnostic counts only; no pixel was altered or removed. The 0–10 °C range means 0 ≤ Celsius < 10, and the <10 °C cluster count includes negative values.

| Date | Product ID | Valid pixels | Min °C | P1 °C | P5 °C | P25 °C | Median °C | Mean °C | P75 °C | P95 °C | P99 °C | Max °C | <0 | 0–10 | >60 | >70 | >80 | >90 | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2025-03-02 | `LC08_L2SP_147047_20250302_20250311_02_T1` | 37718969 | 16.97 | 28.78 | 31.16 | 35.20 | 38.09 | 37.94 | 40.78 | 44.25 | 46.29 | 68.01 | 0 | 0 | 17 | 0 | 0 | 0 | PASS |
| 2025-03-10 | `LC09_L2SP_147047_20250310_20250311_02_T1` | 39546962 | 25.46 | 33.09 | 35.63 | 39.52 | 42.53 | 42.48 | 45.35 | 49.40 | 52.49 | 99.85 | 0 | 0 | 262 | 84 | 42 | 31 | PASS |
| 2025-03-18 | `LC08_L2SP_147047_20250318_20250327_02_T1` | 39479488 | 6.86 | 34.34 | 37.24 | 41.69 | 44.94 | 44.70 | 47.94 | 51.29 | 53.60 | 72.02 | 0 | 6 | 1184 | 3 | 0 | 0 | PASS |
| 2025-03-26 | `LC09_L2SP_147047_20250326_20250327_02_T1` | 39701103 | 26.10 | 33.01 | 36.53 | 41.76 | 44.89 | 44.59 | 47.87 | 51.15 | 53.23 | 69.42 | 0 | 0 | 372 | 0 | 0 | 0 | PASS |
| 2025-04-03 | `LC08_L2SP_147047_20250403_20250411_02_T1` | 32956060 | -10.95 | 31.87 | 34.37 | 38.85 | 42.70 | 42.41 | 45.98 | 49.84 | 52.48 | 69.72 | 32 | 111 | 182 | 0 | 0 | 0 | PASS |
| 2025-04-11 | `LC09_L2SP_147047_20250411_20250412_02_T1` | 37073680 | 16.53 | 32.81 | 36.29 | 42.26 | 45.66 | 45.30 | 48.83 | 52.64 | 55.00 | 64.60 | 0 | 0 | 260 | 0 | 0 | 0 | PASS |
| 2025-04-19 | `LC08_L2SP_147047_20250419_20250425_02_T1` | 39361599 | 15.49 | 34.87 | 38.61 | 44.38 | 47.71 | 47.25 | 50.66 | 53.90 | 55.82 | 69.60 | 0 | 0 | 5769 | 0 | 0 | 0 | PASS |
| 2025-04-27 | `LC09_L2SP_147047_20250427_20250428_02_T1` | 39443265 | 20.00 | 36.43 | 40.16 | 45.93 | 49.46 | 48.96 | 52.37 | 56.10 | 58.36 | 71.18 | 0 | 0 | 108517 | 9 | 0 | 0 | PASS |
| 2025-05-05 | `LC08_L2SP_147047_20250505_20250512_02_T1` | 39631868 | 25.70 | 34.32 | 38.21 | 44.55 | 48.25 | 47.72 | 51.52 | 54.94 | 57.06 | 71.90 | 0 | 0 | 24736 | 17 | 0 | 0 | PASS |

**Overall:** PASS — 9/9 scenes passed.

## Investigated scenes

### 2025-03-10 — `LC09_L2SP_147047_20250310_20250311_02_T1`

Absolute maximum: **99.85 °C** at zero-based row 6438, column 1286 (projected x/y 308580.00, 2000760.00; longitude/latitude 73.1911615, 18.0870973). DN 65535; QA_PIXEL 21824; QA_RADSAT 96.

Bulk comparison: P1 **33.09 °C**, median **42.53 °C**, P99 **52.49 °C**. The absolute extreme is distinct from these distribution summaries.

| Diagnostic range | QA-valid pixels | 8-neighbour clusters | Largest cluster | Largest cluster pixel-centre bounds |
| --- | ---: | ---: | ---: | --- |
| above 80 °C | 42 | 1 | 42 | x 308550.00–308760.00, y 2000640.00–2000790.00 m; lon 73.190875–73.192873, lat 18.086011–18.087384 |
| above 90 °C | 31 | 1 | 31 | x 308580.00–308760.00, y 2000640.00–2000790.00 m; lon 73.191159–73.192873, lat 18.086013–18.087384 |

5×5 neighbourhood centred on the absolute extreme (invalid QA cells have no reported Celsius value):

| Relative row | -2 | -1 | 0 | +1 | +2 |
| ---: | --- | --- | --- | --- | --- |
| -2 | 57.02 °C (valid) | 61.76 °C (valid) | 69.32 °C (valid) | 72.96 °C (valid) | 73.07 °C (valid) |
| -1 | 65.51 °C (valid) | 75.15 °C (valid) | 87.79 °C (valid) | 95.83 °C (valid) | 98.88 °C (valid) |
| 0 | 71.10 °C (valid) | 84.12 °C (valid) | 99.85 °C (valid) | 99.85 °C (valid) | 99.85 °C (valid) |
| 1 | 73.43 °C (valid) | 85.73 °C (valid) | 99.85 °C (valid) | 99.85 °C (valid) | 99.85 °C (valid) |
| 2 | 72.45 °C (valid) | 80.93 °C (valid) | 92.35 °C (valid) | 99.85 °C (valid) | 99.85 °C (valid) |

The >80 °C and >90 °C pixels each form one small contiguous cluster, rather than isolated pixels or a large scene-wide region.

The maximum has DN **65535**, the maximum representable `uint16` value; **21** QA-valid pixels in this scene share that DN. This is a possible source saturation or capping signal, not a confirmed cause. The raw QA values are retained above and in JSON.

### 2025-04-03 — `LC08_L2SP_147047_20250403_20250411_02_T1`

Absolute minimum: **-10.95 °C** at zero-based row 7475, column 4858 (projected x/y 416940.00, 1969950.00; longitude/latitude 74.2162292, 17.8155254). DN 33119; QA_PIXEL 21824; QA_RADSAT 0.

Bulk comparison: P1 **31.87 °C**, median **42.70 °C**, P99 **52.48 °C**. The absolute extreme is distinct from these distribution summaries.

| Diagnostic range | QA-valid pixels | 8-neighbour clusters | Largest cluster | Largest cluster pixel-centre bounds |
| --- | ---: | ---: | ---: | --- |
| below 10 °C | 143 | 9 | 55 | x 416670.00–417000.00, y 1969950.00–1970280.00 m; lon 74.213668–74.216795, lat 17.815515–17.818510 |
| below 0 °C | 32 | 5 | 19 | x 416820.00–417000.00, y 1969950.00–1970070.00 m; lon 74.215092–74.216795, lat 17.815521–17.816612 |

5×5 neighbourhood centred on the absolute extreme (invalid QA cells have no reported Celsius value):

| Relative row | -2 | -1 | 0 | +1 | +2 |
| ---: | --- | --- | --- | --- | --- |
| -2 | invalid QA | -9.37 °C (valid) | -7.65 °C (valid) | -5.70 °C (valid) | -3.52 °C (valid) |
| -1 | invalid QA | invalid QA | -9.89 °C (valid) | -8.10 °C (valid) | -5.97 °C (valid) |
| 0 | invalid QA | invalid QA | -10.95 °C (valid) | -9.64 °C (valid) | -7.46 °C (valid) |
| 1 | invalid QA | invalid QA | invalid QA | invalid QA | invalid QA |
| 2 | invalid QA | invalid QA | invalid QA | invalid QA | invalid QA |

The <10 °C and <0 °C pixels form several small clusters, rather than one isolated pixel or a large scene-wide region.

Within the 5×5 window, **15** of 24 neighbours fail the production QA mask; **15** neighbours carry the dilated-cloud bit. The coldest pixel itself passes QA. This pattern warrants inspection for a possible QA-edge effect; it does not establish the cause.

Coordinates are pixel centres. Cluster bounds enclose pixel centres, not full pixel edges. The JSON report contains all per-scene extreme coordinates, raw QA values, full 5×5 cells, and cluster bounds. These diagnostics cannot identify the land feature or cause without further source investigation.
