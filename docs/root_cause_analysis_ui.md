# Root Cause Analysis UI

The `/root-cause` page is a frontend for `POST /api/explain`. It displays only explanations calculated from the matching saved XGBoost LST model and ML grid; it contains no placeholder observations or feature contributions.

Select a cell from the Heat Map’s **Explain this prediction** action, open `/root-cause?grid_id=<real-grid-id>`, or enter an exact ID on the page. Submitting updates the query parameter, so the selection is linkable and browser navigation remains meaningful.

The page reports predicted LST, the TreeSHAP model baseline, the reconstructed prediction, the numerical reconstruction residual, signed local contributions in °C, global mean-absolute rankings, grouped local/global summaries, raw feature values and units, correlation warnings, and the hashes supplied by the explanation API. Friendly display groups map the backend categories to vegetation, built environment, albedo/reflectivity, mobility, and exposure/context; the underlying contribution values are not transformed.

Raw `shap_value_c` values are signed model-output contributions. Global `mean_abs_shap_c` values are nondirectional magnitudes. Neither is a causal intervention effect. The page explicitly states that attribution is not causation and that LST is not pedestrian air temperature, health risk, vulnerability, or probability.

The interface distinguishes initial no-selection, loading, malformed/no-data response, HTTP 404, HTTP 422, HTTP 503, connection error, and other server errors. Charts retain visible values and accessible list/item labels, controls are native keyboard-operable elements, and wide feature tables scroll within narrow screens.

Run from the project root:

```powershell
cd frontend
npm run build
```

For a live check, start FastAPI and Vite as documented in `README.md`, then open `/root-cause`. Without the required real grid and model, a submitted cell ID must show the 503 unavailable state rather than fabricated values.
