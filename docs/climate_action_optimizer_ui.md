# Climate Action Optimizer UI

The `/climate-action-optimizer` route loads objective settings and `GET /api/optimizer/locations`. The location control is a keyboard-usable select populated only with locations that passed the backend evidence gate. Free-text IDs and caller-supplied ground/roof capacities have been removed.

After selecting a location, the screen shows its verified ground and roof capacities, CRS, capacity status, and number of supported interventions. Users enter only capital and annual-maintenance limits and may adjust normalized policy priorities. `POST /api/optimize` sends `location_id`, those two financial limits, and weights.

Results show integer quantities, cost, maintenance, area use, marginal cooling proxy, green-cover gain, horizon, evidence status, source IDs, and uncertainty status. Constraint bars use catalog capacities. The interaction warning states that summed marginal cooling is a linear planning proxy and can double-count overlap or miss interactions; it is not causal, observed, a ward-average forecast, or pedestrian air-temperature benefit.

When no location is complete, the select and submit button remain disabled and exact catalog blockers are shown. The current committed catalog has this state because real model artifacts, verified planning-area capacities, and authoritative/audited costs are absent. No placeholder values are shown.

Run:

```powershell
cd frontend
npm run build
```
