# Landsat processing smoke test: March-May 2025

These are full-scene source-processing diagnostics. They are not PMC/PCMC or Pune temperature results because the verified municipal boundary is not yet available.

The figures below use QA-valid pixels over each original scene footprint. No municipal crop or production raster was created.

| Date | Product ID | Satellite | Total pixels | Nonzero ST | QA-valid pixels | QA-valid % | Finite Celsius | Min °C | Max °C | Mean °C | Median °C | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2025-03-02 | `LC08_L2SP_147047_20250302_20250311_02_T1` | Landsat 8 | 59376811 | 40509239 | 37718969 | 63.5247 | 37718969 | 16.97 | 68.01 | 37.94 | 38.09 | PASS |
| 2025-03-10 | `LC09_L2SP_147047_20250310_20250311_02_T1` | Landsat 9 | 59454621 | 40636985 | 39546962 | 66.5162 | 39546962 | 25.46 | 99.85 | 42.48 | 42.53 | PASS |
| 2025-03-18 | `LC08_L2SP_147047_20250318_20250327_02_T1` | Landsat 8 | 59454621 | 40505249 | 39479488 | 66.4027 | 39479488 | 6.86 | 72.02 | 44.70 | 44.94 | PASS |
| 2025-03-26 | `LC09_L2SP_147047_20250326_20250327_02_T1` | Landsat 9 | 59376811 | 40636403 | 39701103 | 66.8630 | 39701103 | 26.10 | 69.42 | 44.59 | 44.89 | PASS |
| 2025-04-03 | `LC08_L2SP_147047_20250403_20250411_02_T1` | Landsat 8 | 59453121 | 40505380 | 32956060 | 55.4320 | 32956060 | -10.95 | 69.72 | 42.41 | 42.70 | PASS |
| 2025-04-11 | `LC09_L2SP_147047_20250411_20250412_02_T1` | Landsat 9 | 59376811 | 40640059 | 37073680 | 62.4380 | 37073680 | 16.53 | 64.60 | 45.30 | 45.66 | PASS |
| 2025-04-19 | `LC08_L2SP_147047_20250419_20250425_02_T1` | Landsat 8 | 59376811 | 40499059 | 39361599 | 66.2912 | 39361599 | 15.49 | 69.60 | 47.25 | 47.71 | PASS |
| 2025-04-27 | `LC09_L2SP_147047_20250427_20250428_02_T1` | Landsat 9 | 59376811 | 40637449 | 39443265 | 66.4287 | 39443265 | 20.00 | 71.18 | 48.96 | 49.46 | PASS |
| 2025-05-05 | `LC08_L2SP_147047_20250505_20250512_02_T1` | Landsat 8 | 59454621 | 40499979 | 39631868 | 66.6590 | 39631868 | 25.70 | 71.90 | 47.72 | 48.25 | PASS |

## Summary

- Expected scenes: **9**
- Scenes processed: **9**
- Scenes passed: **9**
- Scenes failed: **0**
- Overall: **PASS**

## Observed full-scene extremes for review

- Lowest QA-valid Celsius value: **-10.95 °C** in `LC08_L2SP_147047_20250403_20250411_02_T1`.
- Highest QA-valid Celsius value: **99.85 °C** in `LC09_L2SP_147047_20250310_20250311_02_T1`.
- These extremes are preserved without clipping or extra QA rules. Their location and cause have not been established.

No temperature range filter was applied. A PASS means the source files decoded, matched grids, and yielded finite QA-valid values; it does not verify municipal coverage or support a city temperature claim.
