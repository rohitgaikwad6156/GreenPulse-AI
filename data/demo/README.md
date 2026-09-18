# DEMO / SYNTHETIC DATA

`intervention_catalog_assumptions.json` contains separate **DEMO COST ASSUMPTIONS** and other illustrative planning inputs for six discrete actions. It generates `../processed/interventions.csv`. Its costs, co-benefit scores, and area assumptions are not verified PMC/PCMC values; cooling benefits and site-specific feasible maxima remain blank. See [Step 21 catalog documentation](../../docs/intervention_catalog.md).

`greenpulse_demo_grid.csv` contains 3,600 computer-generated 30 m grid cells. It is for exercising GreenPulse file loading, charts, APIs, and UI only. It is **not** observed Pune or PCMC climate data. `DEMO_WARD_01` through `DEMO_WARD_06` are fictional partitions, not official wards. The map centre near Pune is only a coordinate-system test anchor. No actual ward boundary, satellite raster, or sensor reading was used.

The CSV has the 17 requested Step 6 fields plus `data_label`, which contains `DEMO / SYNTHETIC DATA` in every row. It is one undated synthetic snapshot. Do not join it to real date-based observations or report its descriptive statistics as measured climate results.

## Reproduce

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\scripts\requirements-demo.txt
.\.venv\Scripts\python.exe .\scripts\create_demo_dataset.py
```

The fixed seed `20260917` makes reruns reproducible. The script writes `greenpulse_demo_grid.csv` and two images in `figures/`. It validates row count, unique IDs, coordinate spacing, missing values, sensible ranges, every data label, and intended correlation directions.

## Synthetic LST label equation

All coefficients are arbitrary demonstration assumptions. Let `N` be NDVI, `B` be NDBI, `C` be canopy percent, `U` be built percent, `A` be albedo, `R` be road density in km/km², `D` be distance to green space in metres, `E` be elevation in metres, and `(row, col)` be the artificial grid indices. The generator computes:

```text
LST_demo (°C) = 32.0 + 5.2 B + 3.8(U/100) - 4.8 N - 2.5(C/100)
                - 13.0(A - 0.20) + 0.20 R + 0.50(D/1000)
                - 0.45((E - 560)/100)
                + 0.45 sin(col/7) cos(row/9) + Normal(0, 1.45°C)
```

Other synthetic features share a noisy artificial urbanity gradient, so their simple correlations with LST need not equal their equation coefficients. The random noise prevents perfect relationships. This equation is **only the synthetic data generator**. It is **not** the final GreenPulse prediction model, a calibrated physical model, or evidence of intervention effects. The actual project target remains observed continuous land surface temperature in °C. LST is not pedestrian air temperature.

## Diagnostic charts

- `figures/demo_distributions.png`: six histograms for range and shape checks.
- `figures/demo_correlations.png`: Pearson correlation matrix for LST and five requested directional features. These correlations are a property of the generator, not a discovery about Pune.
