# Step 24 — Interactive Pune / PCMC heat map

The [Heat Map page](../frontend/src/pages/HeatMap.jsx) uses React Leaflet and offers two explicit sources.

## Satellite observations (default)

NASA GIBS Terra/MODIS daytime land-surface temperature imagery renders directly
from the public WMS service, independent of FastAPI, ward GIS and local models.
The initial date is **2025-05-10**, a historical peak-summer date with verified
imagery over the study area. Users can change the observation date and opacity.
This is daily imagery, not a summer composite or current weather.

- WMS: `https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi`
- Layer: `MODIS_Terra_Land_Surface_Temp_Day`
- [NASA source metadata](https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/MODIS_Terra_Land_Surface_Temp_Day.json)
- [Original NASA legend](https://gibs.earthdata.nasa.gov/legends/MODIS_Land_Surface_Temp_H.png)

The source is approximately **1 km**, not 30 m. Zooming enlarges the imagery;
it does not add spatial detail. The original legend is in kelvin and the UI
explains conversion to Celsius. Transparent pixels can mean clouds, missing
swaths or no retrieval, never zero temperature. Tile-load success indicates
image delivery, not complete measurement coverage. Service failures appear
beside the controls; Refresh remounts the layer to retry.

The satellite view does not call model APIs or show SHAP, ward estimates,
intervention effects or model accuracy. It does not write imagery into the
research training data. No numerical temperatures are inferred from RGB colors.

## Research model (separate selectable view)

When verified ward GIS is available, city scale colors ward polygons by the mean XGBoost-predicted **land surface temperature (LST, °C)** across complete-case 30 m cells. Independently, at zoom 16 or greater the cell view requests cells in the current viewport. Clicking a ward or cell calls FastAPI for its prediction, Heat Hazard Score if calibrated, confidence status, and descriptive TreeSHAP factors. No fake markers or fallback climate readings are added.

### Research-model readiness UX

On page load, the Heat Map reads the canonical `GET /api/readiness` contract.
It refreshes that evidence only when the user requests a status refresh, not on
map movement. Its required-source checklist comes directly from
`required_sources`; display labels do not define which groups are required.
The source gate (`first_heat_map`) and the real grid/XGBoost artifact statuses
(`artifacts`) are shown as separate steps. A ready source gate still requires
real processing, training and spatial validation; source readiness does not
establish model accuracy.

When sources or artifacts are missing, Research Model mode shows an explanatory
panel with current blockers, next actions, an artifact summary and a link to
the full Data Readiness evidence. The layer, view and season controls are
disabled until the model is ready. The geographic basemap remains visible,
without a model legend, hotspot ranking or fabricated selection values.
Malformed readiness evidence or an unreachable API produces an unknown state
with a retry action; it never displays presumed pending sources.

Verified ward GIS remains a reporting/UI dependency. If the cell model is
ready but ward GIS is not, the map explains that ward reporting is unavailable
and keeps the cell view distinct from the first-build source gate. An initial
failed model load may still select MODIS automatically. Choosing Research Model
explicitly keeps that choice visible so the user can read the readiness panel
and switch to MODIS deliberately. NASA MODIS is an independent historical
observation layer at approximately 1 km source resolution, never a 30 m
GreenPulse prediction.

## Required real artifacts

| File | Role |
| --- | --- |
| `data/boundaries/pmc_pcmc.geojson` | Verified PMC and PCMC municipal outlines required to define the 30 m study grid. |
| `data/boundaries/pmc_pcmc_wards.geojson` | Optional for training; required for ward aggregation and ward UI, with verified issuing authority and version. |
| `data/processed/greenpulse_ml_grid.parquet` and `metadata.json` | Real, aligned complete-case 30 m cells and their features. |
| `models/xgboost_lst.joblib` and `model_metadata.json` | Matching trained continuous-LST model and held-out spatial metrics. |

The combined municipal outline is not yet verified, and current grid/model files are not accepted real production artifacts. The research-model view therefore shows geographic context and an explicit readiness panel; the default NASA view remains independently usable. Missing ward GIS blocks ward views only. The demo CSV is never used in the map API. A numeric Heat Hazard Score also needs calibrated reference values in model metadata. Without them, the selection panel says `Unavailable`. The confidence panel reports that no cell-level interval is calibrated; where available, it shows held-out spatial RMSE separately.

## Map API

- `GET /api/map/wards`: ward-boundary GeoJSON.
- `GET /api/map/heat/wards`: ward polygons with mean predicted LST and a data-derived color range.
- `GET /api/map/heat/cells?west=...&south=...&east=...&north=...`: viewport 30 m polygons with predicted LST. More than 2,500 cells returns `too_many_cells: true` and no partial heat layer; zoom in.
- `GET /api/map/ward/{ward_id}`: ward mean predicted LST, optional hazard score, uncertainty status, and top SHAP factors from a deterministic sample of at most 100 ward cells.
- `GET /api/map/cell/{grid_id}`: one cell's predicted LST, optional hazard score, uncertainty status, and local SHAP factors.

Model and dataset version/hash checks run before any prediction. Backend ward summaries are cached by artifact signatures. Grid view reads Parquet in batches; the browser requests cells after a 250 ms pan/zoom pause and cancels stale requests. Leaflet uses canvas rendering and the heat-map route loads as a separate frontend bundle.

## Run and verify on Windows PowerShell

From `GreenPulse-AI`, start FastAPI in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm run dev -- --host localhost --port 5173 --strictPort
```

Open `http://localhost:5173/heat-map`. Expect NASA satellite heat colors, source/date/resolution labels, a date input, opacity control and the NASA legend. Check date changes, zooming, opacity and Refresh. Switch to Research Model to inspect the canonical source checklist, blockers and artifact states; the radio choice should remain selected. Use the in-page MODIS button to switch back. In Swagger at `http://127.0.0.1:8000/docs`, all five `/api/map/...` routes appear; they return 503 until real artifacts exist. Once the verified inputs are prepared, expect ward outlines and a ward heat layer, then 30 m cells on zooming in. Click a ward or cell and compare the selection panel to its corresponding API response.

To run the labelled artificial fixture tests and frontend build:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_heat_map_api -v
Set-Location frontend
npm run build
```

The tests create temporary **ARTIFICIAL / SYNTHETIC** geometry and a tiny fitted test model. Their outputs are not Pune observations, model accuracy, or intervention results.

## Limits and common errors

- A 503 from ward boundaries means verified official ward GIS is unavailable or does not match the processed grid. Cell routes remain independent of wards.
- A 503 from heat or selection routes means a real model/grid artifact is missing or mismatched. No demo values are substituted.
- `too_many_cells` means the view exceeds 2,500 modeled cells; zoom in. A wide city view uses ward aggregation instead.
- Ward means include only complete-case modeled cells. They are not area-weighted estimates for every part of a ward.
- Land surface temperature is not pedestrian air temperature. Landsat's underlying thermal footprint is coarser than the 30 m output grid. SHAP describes model predictions, not causal heat drivers.
- The OpenStreetMap tile layer is a geographic basemap, not a climate measurement. The tile URL is configurable with `VITE_MAP_TILE_URL`; retain visible OSM attribution and comply with the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Do not bulk download tiles.


### Research map controls

Research Model is selected on initial load when verified ward predictions exist;
otherwise the map falls back to optional MODIS imagery. Existing route paths and
fields are preserved. Added response fields supply the cell-weighted city baseline,
model date range, grouped SHAP attributions, and layer values.

LST, calibrated Heat Hazard Score, and Confidence are separate layers. Confidence
currently displays model-wide held-out spatial CV RMSE, not local certainty.
A calibrated 90% prediction interval is not produced by the current pipeline;
the detail field remains null and the UI reports calibration required. No RMSE
multiplier is substituted for a calibrated prediction interval.

Ward means or viewport-limited 30 m cells can be selected. Top 5 hotspots ranks
available ward means or visible cells by predicted LST, explicitly labeling scope.
The city comparison uses the full modeled grid, never the current viewport.
Grouped SHAP sums all features in each category per sample before averaging and
ranking by mean absolute group contribution; at most three groups are shown.
Ward Explain expands that interpretation; ward Simulate zooms to cells for an
explicit cell selection before using the existing simulation route.

Peak Summer is labeled only for a model with a documented March–May period.
Other seasonal selections report unavailable and hide predictions; they never
reuse summer predictions as another season. MODIS keeps its independent dated
observation controls and source resolution.
