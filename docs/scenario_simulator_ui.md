# Scenario Simulator UI (Step 25)

The React panel at `/scenario-simulator` sends one request to `POST /api/simulate`. It accepts a real 30 m `grid_id`, a 0–40 percentage-point canopy increase, and a 0–50% retrofit share of verified eligible roof area. A scenario can include either intervention or both. Verified plantable ground and eligible roof area are entered in m² and constrained to the 900 m² cell.

After a successful response, the panel shows baseline and scenario **land surface temperature (LST)**, signed ΔLST, nonnegative estimated cooling, the approximate 90% cooling range, MVP confidence category, prediction horizon, modified model features, and the assumptions returned by the backend. The map shows the real grid-cell polygon colored according to the baseline and scenario predictions. **Compare baseline vs scenario** places both maps side by side. The colors are relative to the two estimates, not a citywide temperature scale. **Reset scenario** clears the sliders, areas, result, and map while keeping the selected grid ID.

## Run on Windows PowerShell

In one PowerShell window:

```powershell
cd 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In another:

```powershell
cd 'D:\green plus ai\GreenPulse-AI\frontend'
npm run dev -- --host 127.0.0.1
```

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env.local`, then restart Vite if that file changed. Open `http://127.0.0.1:5173/scenario-simulator`. Select a real cell on the Heat Map and follow **Simulate an intervention for this cell**, or enter its real grid ID. Enter verified feasible areas, move either slider, and run the scenario. Inspect the Network tab for `POST /api/simulate` and, after success, `GET /api/map/cell/{grid_id}`. Change a slider and confirm the previous result and map clear. Run again; use **Compare baseline vs scenario** and **Reset scenario**.

With no matching real grid, saved XGBoost model, and spatial CV RMSE, the API refuses to produce a scenario. The panel shows an availability error and no invented temperature or map result. A nonexistent grid ID returns a not-found error after the real artifacts are installed.

## Checks

```powershell
cd 'D:\green plus ai\GreenPulse-AI\frontend'
npm run build
cd 'D:\green plus ai\GreenPulse-AI'
.\.venv\Scripts\python.exe -m pytest -q
```

These what-if values are model sensitivity estimates from assumed feature transformations. The interval is approximate, the confidence categories are MVP display thresholds, and none of these results guarantees real-world cooling. LST is not pedestrian air temperature. Tree and cool-roof parameters require local calibration, and the map does not represent predicted spillover to adjacent cells.
