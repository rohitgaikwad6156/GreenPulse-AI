# Climate Action Optimizer UI (Step 26)

The React route `/climate-action-optimizer` sends a named location, capital budget in INR, annual maintenance limit in INR/year, available ground and roof in m², and three optional policy weights to `POST /api/optimize`. The weights start from the backend's `GET /api/optimizer/config`; moving a priority slider sends its value to the solver. The budget number input and slider stay synchronized. After the first run, changing any planning input reruns the optimizer after a 400 ms pause, and older in-flight requests are canceled.

A successful response displays selected integer quantities, block sizes, occupied ground/roof area, capital and annual costs, modeled marginal cooling proxy, green-cover gain, and the intervention horizon from the catalog. A summary shows budget use, unused budget, estimated cooling proxy, green gain, constraints, and normalized policy weights. The Cost vs Cooling chart plots selected intervention totals and the current portfolio. A previous successful portfolio is retained for comparison when inputs change.

## Run and inspect on Windows PowerShell

Start FastAPI from the project root:

```powershell
cd 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window:

```powershell
cd 'D:\green plus ai\GreenPulse-AI\frontend'
npm run dev -- --host 127.0.0.1
```

Ensure `frontend/.env.local` contains `VITE_API_BASE_URL=http://127.0.0.1:8000`. Open `http://127.0.0.1:5173/climate-action-optimizer`. Enter a catalog location ID and planning limits, then press **Optimize action portfolio**. The browser Network tab should show `GET /api/optimizer/config` followed by `POST /api/optimize`. Moving the budget slider after a run issues another POST with the updated budget.

At present, [interventions.csv](../data/processed/interventions.csv) contains **DEMO COST ASSUMPTIONS** and deliberately blank cooling, site capacity, and location fields. A complete plan, green gain, and chart must therefore remain unavailable. The expected API response is HTTP 503 naming a missing field, such as `predicted_cooling_benefit_c`. No Pune or PCMC portfolio is fabricated to fill the screen.

## Verify

```powershell
cd 'D:\green plus ai\GreenPulse-AI\frontend'
npm run build
cd 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pytest -q
```

The solver tests use **ARTIFICIAL / SYNTHETIC TEST FIXTURES** only. They check integer blocks, resource limits, policy-weight changes, and returned green gain and horizon. With completed real evidence, a returned portfolio is **optimal under the modeled objective, assumptions and constraints**. The sum of per-block LST cooling values is a linear planning proxy, not ward-average LST, pedestrian air temperature, or a guaranteed real-world outcome. Time horizons can differ across interventions; the chart does not account for those timing differences.
