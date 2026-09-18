# Step 27 — Post-implementation validation

GreenPulse AI validates land surface temperature (LST) using the same 30 m grid cell IDs before and after an intervention. Every treated and control cell needs one pre and one post LST value. NDVI is optional but must be present in both periods for every cell if used. Predicted intervention ΔLST is optional but must cover every treated cell if used.

The descriptive Difference-in-Differences estimate is:

    DiD = (mean treated post LST − mean treated pre LST)
        − (mean control post LST − mean control pre LST)

Signed realized cooling is −DiD. Positive means relative cooling; negative means relative warming. Paired ΔNDVI is mean post NDVI minus mean pre NDVI for each group.

For each treated cell, control-adjusted actual ΔLST is its observed post-pre change minus the mean control post-pre change. Residual equals adjusted actual ΔLST minus predicted ΔLST. MAE is the mean absolute residual over M treated cells; RMSE is the square root of their mean squared residual. Mean adjusted actual ΔLST equals DiD. These follow-up metrics are separate from spatial block cross-validation metrics.

## Data provenance

There are no verified historical before/after intervention observations in this workspace. The file [validation_scenario.json](../data/demo/validation_scenario.json) is **DEMO / SYNTHETIC DATA**. Its LST, NDVI, and prediction values exist solely to check arithmetic and UI behavior. The UI loads it only after the explicit **Load DEMO VALIDATION SCENARIO** action. **Start blank** clears it for user-supplied observations. The API cannot verify a manually entered source, so manual results carry an unverified-provenance label.

The dashboard shows predicted ΔLST, control-adjusted actual ΔLST, mean residual, DiD, paired ΔNDVI, individual treated-cell comparisons, MAE, and RMSE when enough inputs are supplied.

## Windows PowerShell

Start FastAPI in one window:

    cd 'D:\green plus ai\GreenPulse-AI'
    .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

Start Vite in another:

    cd 'D:\green plus ai\GreenPulse-AI\frontend'
    npm run dev -- --host 127.0.0.1

Set VITE_API_BASE_URL=http://127.0.0.1:8000 in frontend/.env.local and restart Vite after changing it. Open http://127.0.0.1:5173/validation. Click **Load DEMO VALIDATION SCENARIO**, then **Calculate validation**. The Network tab should show GET /api/validation/demo followed by POST /api/validation/did. The result must retain the **DEMO VALIDATION SCENARIO** label.

To verify:

    cd 'D:\green plus ai\GreenPulse-AI\frontend'
    npm run build
    cd 'D:\green plus ai\GreenPulse-AI'
    .\.venv\Scripts\python.exe -m pytest -q

The bundled demo is a calculation check, **not** evidence of Pune model accuracy. DiD is descriptive here: causal interpretation requires credible parallel trends, comparable seasonal imagery and overpass times, appropriate control selection, no spillover, and attention to other changes. NDVI gain does not itself prove cooling. LST is not pedestrian air temperature.
