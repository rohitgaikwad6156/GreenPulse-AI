# Sentinel-2 L2A manual source intake: March-May 2025

This report audits only local files selected in `data/provenance/discovery_2025.json`. No data was downloaded or created, and source verification status was not changed.

## Backend path contract

The production `discover_granules()` looks recursively below `data/raw/sentinel2/` for `*.SAFE` directories whose names contain `MSIL2A` and a March-May acquisition date. Inside each SAFE it reads `MTD_MSIL2A.xml` and each directory under `GRANULE/`. For **each** granule it requires exactly one matching JP2 at:

- `GRANULE/<original-granule-id>/IMG_DATA/R10m/*_B04_10m.jp2`
- `GRANULE/<original-granule-id>/IMG_DATA/R10m/*_B08_10m.jp2`
- `GRANULE/<original-granule-id>/IMG_DATA/R20m/*_B11_20m.jp2`
- `GRANULE/<original-granule-id>/IMG_DATA/R20m/*_SCL_20m.jp2`

The audit additionally checks that JP2 filenames carry the selected tile and acquisition date and share a granule prefix. Preserve the original SAFE and granule names from the manual download. Metadata must supply the BOA quantification and offsets required by the existing backend.

## Selected products

| Date | MGRS tile | Exact product ID | SAFE | XML | B04 10 m | B08 10 m | B11 20 m | SCL 20 m | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-03-14 | MGRS-43QCA | `S2B_MSIL2A_20250314T052649_N0511_R105_T43QCA_20250314T095315` | missing | missing | missing | missing | missing | missing | FAIL |
| 2025-03-14 | MGRS-43QDA | `S2B_MSIL2A_20250314T052649_N0511_R105_T43QDA_20250314T095315` | missing | missing | missing | missing | missing | missing | FAIL |
| 2025-04-13 | MGRS-43QCA | `S2B_MSIL2A_20250413T052649_N0511_R105_T43QCA_20250413T075318` | missing | missing | missing | missing | missing | missing | FAIL |
| 2025-04-13 | MGRS-43QDA | `S2B_MSIL2A_20250413T052649_N0511_R105_T43QDA_20250413T075318` | missing | missing | missing | missing | missing | missing | FAIL |
| 2025-05-10 | MGRS-43QCA | `S2A_MSIL2A_20250510T053241_N0511_R105_T43QCA_20250510T084438` | missing | missing | missing | missing | missing | missing | FAIL |
| 2025-05-10 | MGRS-43QDA | `S2A_MSIL2A_20250510T053241_N0511_R105_T43QDA_20250510T084438` | missing | missing | missing | missing | missing | missing | FAIL |

## Exact placement

Place each manually obtained, extracted original SAFE directly under `data/raw/sentinel2/`:

- `data/raw/sentinel2/S2B_MSIL2A_20250314T052649_N0511_R105_T43QCA_20250314T095315.SAFE/`
- `data/raw/sentinel2/S2B_MSIL2A_20250314T052649_N0511_R105_T43QDA_20250314T095315.SAFE/`
- `data/raw/sentinel2/S2B_MSIL2A_20250413T052649_N0511_R105_T43QCA_20250413T075318.SAFE/`
- `data/raw/sentinel2/S2B_MSIL2A_20250413T052649_N0511_R105_T43QDA_20250413T075318.SAFE/`
- `data/raw/sentinel2/S2A_MSIL2A_20250510T053241_N0511_R105_T43QCA_20250510T084438.SAFE/`
- `data/raw/sentinel2/S2A_MSIL2A_20250510T053241_N0511_R105_T43QDA_20250510T084438.SAFE/`

Within **each** SAFE, retain `MTD_MSIL2A.xml` at the SAFE root and the original `GRANULE/<original-granule-id>/IMG_DATA/R10m` and `R20m` directories with the four JP2 files listed above. Do not rename imagery into a different product or invent a granule ID.

## Missing manual files

- `S2B_MSIL2A_20250314T052649_N0511_R105_T43QCA_20250314T095315.SAFE`: MTD_MSIL2A.xml, B04_10m, B08_10m, B11_20m, SCL_20m
- `S2B_MSIL2A_20250314T052649_N0511_R105_T43QDA_20250314T095315.SAFE`: MTD_MSIL2A.xml, B04_10m, B08_10m, B11_20m, SCL_20m
- `S2B_MSIL2A_20250413T052649_N0511_R105_T43QCA_20250413T075318.SAFE`: MTD_MSIL2A.xml, B04_10m, B08_10m, B11_20m, SCL_20m
- `S2B_MSIL2A_20250413T052649_N0511_R105_T43QDA_20250413T075318.SAFE`: MTD_MSIL2A.xml, B04_10m, B08_10m, B11_20m, SCL_20m
- `S2A_MSIL2A_20250510T053241_N0511_R105_T43QCA_20250510T084438.SAFE`: MTD_MSIL2A.xml, B04_10m, B08_10m, B11_20m, SCL_20m
- `S2A_MSIL2A_20250510T053241_N0511_R105_T43QDA_20250510T084438.SAFE`: MTD_MSIL2A.xml, B04_10m, B08_10m, B11_20m, SCL_20m

## Current intake status

- Expected products: **6**
- SAFE directories found: **0**
- Minimum required files expected: **30**
- Required file slots found: **0**
- Products passed: **0**
- Products failed: **6**
- Overall: **FAIL / PENDING**

The JSON and CSV contain per-file presence, size, SHA-256, readability, CRS, resolution, and dimensions when a real file exists. A missing file has null measurements; no values are inferred.
