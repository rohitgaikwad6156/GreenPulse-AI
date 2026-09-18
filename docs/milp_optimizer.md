# Step 22 — MILP climate action optimizer

GreenPulse AI is an AI-powered Urban Climate Decision-Support System. This step adds the discrete-action optimizer. It does not create a Pune or PCMC action plan: the current [catalog](../data/processed/interventions.csv) intentionally has blank cooling benefit and maximum feasible units. Its costs are **DEMO COST ASSUMPTIONS**, not verified municipal costs.

## Inputs and units

The API accepts `location` (exact ward/site identifier), `budget_inr` (capital INR), `maintenance_cap_inr_per_year` (annual INR), `available_ground_m2`, and `available_roof_m2`. ₹10 lakh is **₹1,000,000**. Every candidate action must have the same `location`, per-block cost, annual maintenance, ground and roof area, modeled marginal cooling in °C, green-cover gain in m², a 0–5 catalog co-benefit score, and a verified nonnegative integer `maximum_feasible_units`. Blank benefit or capacity fields make the request unavailable; zero is accepted only if it is a documented modeled value.

The editable [objective configuration](../backend/app/optimizer/objective_config.json) holds prototype weights α=1, β=0.5, γ=0.2. `C_ref` and `G_ref` are the maximum positive **per-block** cooling and green gain among the submitted candidates. A dimension with all zero benefits contributes zero. The co-benefit divisor is 10 as specified for this step. The Step 21 catalog uses scores from 0 to 5, so its normalized co-benefit reaches at most 0.5. Changing the candidate set can change the two maximum-based references and hence the ranking; record the candidates and configuration for reproducibility.

For block i, `u_i = α(C_i/C_ref) + β(G_i/G_ref) + γ(B_i/10)`. SciPy minimizes `-u·x` with `x_i` constrained to nonnegative integers and `x_i ≤ U_i`. Four upper-bound rows restrict total capital, annual maintenance, ground area, and roof area. The result includes selected integer quantities, resource totals, unused budget, normalized objective, and a *linear modeled cooling proxy*. A returned optimal status means **“Optimal under the modeled objective, assumptions and constraints.”** It does not certify the best real-world climate plan.

Summing marginal cooling in °C across blocks is a simplified planning proxy, not a ward-average LST forecast. Adjacent interventions can overlap or interact; planting takes time and roof performance can age. Interventions may have different horizons. Ground/roof eligibility, verified costs, maintenance, and benefits must be gathered or calibrated per location before municipal use. LST is not pedestrian air temperature.

## Files and test

- [MILP solver](../backend/app/optimizer/milp_optimizer.py)
- [Objective configuration](../backend/app/optimizer/objective_config.json)
- [Endpoint](../backend/app/main.py): `POST /api/optimizer/plan`
- [Tests](../tests/test_milp_optimizer.py): **ARTIFICIAL / SYNTHETIC TEST FIXTURE** only

From the project root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-optimizer.txt
.\.venv\Scripts\python.exe -m unittest tests.test_milp_optimizer -v
```

Expected: six tests pass. They cover the integer portfolio, four resource limits, budget conversion, invalid inputs, location matching, and refusal to optimize the incomplete real catalog. The fixture's cooling values are artificial test values, not Pune predictions.

To inspect the endpoint with the current catalog, start FastAPI as in the README, open `http://127.0.0.1:8000/docs`, and expand `POST /api/optimizer/plan`. Supply an actual ward identifier and planning limits. Expected now: HTTP 503 describing the missing `predicted_cooling_benefit_c`. This is intentional. Supplying a budget, even ₹10 lakh, cannot create missing intervention science.

Common errors: `ModuleNotFoundError: scipy` means install the optimizer requirements in the project virtual environment; a 503 missing-benefit/capacity/location error means complete and document the ward-specific catalog; HTTP 422 means an invalid input such as a negative budget or mismatched location.

SciPy solver reference: [scipy.optimize.milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html).
