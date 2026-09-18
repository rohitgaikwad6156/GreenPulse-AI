# Step 21: discrete climate intervention catalog

GreenPulse AI is **An AI-powered Urban Climate Decision-Support System**. This catalog prepares six integer-sized intervention actions for a later MILP step. It does **not** optimize or recommend actions yet. The GreenPulse research PDF describes the intervention and MILP planning concept; its example costs and cooling outputs are not treated as verified Pune results.

## Files

- [`data/demo/intervention_catalog_assumptions.json`](../data/demo/intervention_catalog_assumptions.json): editable **DEMO / SYNTHETIC DATA — DEMO COST ASSUMPTIONS** for block sizes, capital costs, annual maintenance, area requirements, illustrative green-cover gain, subjective co-benefit scores, horizons, and source notes. These are not PMC/PCMC prices, bids, invoices, or measured impacts.
- [`backend/app/ml/uncertainty_assumptions.json`](../backend/app/ml/uncertainty_assumptions.json): the single source for the four available MVP uncertainty CV coefficients. Shade structures and green corridors have no calibrated CV and therefore have a blank CV field.
- [`backend/app/optimizer/catalog.py`](../backend/app/optimizer/catalog.py): validates the demo label, discrete blocks, nonnegative costs/areas, references, and absent cooling/feasibility results before writing a CSV.
- [`scripts/build_intervention_catalog.py`](../scripts/build_intervention_catalog.py): reproduces the processed catalog.
- [`data/processed/interventions.csv`](../data/processed/interventions.csv): generated six-row output. Every row carries the demo label and `cost_status`.

| Intervention | Integer action block | Area used by one block |
| --- | --- | --- |
| Street Trees | 1 tree | Demo 9 m² plantable ground |
| Cool Roofs | 50 m² | 50 m² eligible roof |
| Green Roofs | 25 m² | 25 m² eligible roof |
| Shade Structures | 1 structure | Demo 25 m² ground site |
| Green Corridors | 25 m² | 25 m² ground |
| Reflective Pavements | 50 m² | 50 m² eligible ground/pavement |

The CSV includes `name`, `unit_type`, `block_size`, `capital_cost_inr`, `annual_maintenance_inr`, `ground_area_required_m2`, `roof_area_required_m2`, `predicted_cooling_benefit_c`, `green_cover_gain_m2`, `co_benefit_score_0_5`, `maximum_feasible_units`, `time_horizon`, `uncertainty_cv`, `assumptions`, and `source_reference`, plus explicit status and feasibility-rule columns. Capital cost is INR per block; maintenance is INR per block per year; green-cover gain and area use m²; cooling benefit would use °C per block if later established. The 0–5 co-benefit scale is an **illustrative ordinal demo input**, not a validated measure of health, equity, or biodiversity.

**Cooling benefit is blank for all six actions.** The real trained model and spatial inputs are absent, and only tree/cool-roof what-if code exists. It would be scientifically wrong to copy an example °C benefit into a supposedly predicted column. **Maximum feasible units is blank** because it must be calculated for each ward or site using verified eligible ground/roof area and additional restrictions. The CSV gives a transparent `maximum_feasible_units_rule` as a first area-only upper bound; later planning must also check tree spacing, roof structure/ownership, road access, maintenance, and other site constraints. Blank means **unknown**, not zero. A future optimizer must reject rows with missing benefits or feasible maxima instead of treating them as free/zero-benefit actions.

The four CV values copied from Step 20 remain **MVP assumptions**, not measured Pune uncertainty. The two blank CVs mean a separate model/calibration is needed. Time horizons describe intervention state (for example, *after canopy establishment*) without inventing exact years or survival rates. LST cooling, when eventually predicted, is not pedestrian air-temperature cooling.

## Windows PowerShell commands

From the `GreenPulse-AI` project root, regenerate the CSV after editing demo assumptions:

```powershell
.\.venv\Scripts\python.exe scripts\build_intervention_catalog.py
```

Expected message: `Saved 6 discrete intervention types`, followed by the path to `data/processed/interventions.csv`. The script states that cooling and feasible maxima remain unestimated. Open the CSV in a text editor or spreadsheet and verify all six rows carry `DEMO COST ASSUMPTIONS`, have integer block sizes, and leave the two unestimated columns blank.

Run the focused tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_intervention_catalog -v
```

Expected: three tests pass. They verify the six rows, cost configurability with retained demo labels, CV provenance, and rejection of fabricated cooling or fractional action blocks. Common errors are a missing assumptions JSON, removed demo label, negative cost/area, fractional block size, or a cooling value entered without a verified benefit model; the builder stops before writing a new CSV.
