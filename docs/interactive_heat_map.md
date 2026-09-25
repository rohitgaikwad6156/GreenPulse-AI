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

At city scale it colors ward polygons by the mean XGBoost-predicted **land surface temperature (LST, °C)** across complete-case 30 m cells. At zoom 16 or greater it requests only cells in the current viewport. Clicking a ward or cell calls FastAPI for its prediction, Heat Hazard Score if calibrated, confidence status, and descriptive TreeSHAP factors. No fake markers or fallback climate readings are added.

## Required real artifacts

| File | Role |
| --- | --- |
| `data/boundaries/pmc_pcmc_wards.geojson` | PMC/PCMC WGS84 polygon input, using the Step 12 ward schema. Verify the issuing authority and version before municipal use. |
| `data/processed/greenpulse_ml_grid.parquet` and `metadata.json` | Real, aligned complete-case 30 m cells and their features. |
| `models/xgboost_lst.joblib` and `model_metadata.json` | Matching trained continuous-LST model and held-out spatial metrics. |

These files are **not currently present**. The research-model view therefore shows geographic context and an explicit missing-input state; the default NASA view remains independently usable. The demo CSV is never used in the map API. A numeric Heat Hazard Score also needs calibrated reference values in model metadata. Without them, the selection panel says `Unavailable`. The confidence panel reports that no cell-level interval is calibrated; where available, it shows held-out spatial RMSE separately.

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

Open `http://localhost:5173/heat-map`. Expect NASA satellite heat colors, source/date/resolution labels, a date input, opacity control and the NASA legend. Check date changes, zooming, opacity and Refresh. Switch to Research model to see `Awaiting data` for missing local boundary/model layers. Switch back to restore satellite imagery. In Swagger at `http://127.0.0.1:8000/docs`, all five `/api/map/...` routes appear; they return 503 until real artifacts exist. Once the verified inputs are prepared, expect ward outlines and a ward heat layer, then 30 m cells on zooming in. Click a ward or cell and compare the selection panel to its corresponding API response.

To run the labelled artificial fixture tests and frontend build:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_heat_map_api -v
Set-Location frontend
npm run build
```

The tests create temporary **ARTIFICIAL / SYNTHETIC** geometry and a tiny fitted test model. Their outputs are not Pune observations, model accuracy, or intervention results.

## Limits and common errors

- A 503 from ward boundaries means the required GeoJSON is missing or structurally invalid. An API check of its fields and geometry does not certify its legal boundary provenance.
- A 503 from heat or selection routes means a real model/grid artifact is missing or mismatched. No demo values are substituted.
- `too_many_cells` means the view exceeds 2,500 modeled cells; zoom in. A wide city view uses ward aggregation instead.
- Ward means include only complete-case modeled cells. They are not area-weighted estimates for every part of a ward.
- Land surface temperature is not pedestrian air temperature. Landsat's underlying thermal footprint is coarser than the 30 m output grid. SHAP describes model predictions, not causal heat drivers.
- The OpenStreetMap tile layer is a geographic basemap, not a climate measurement. The tile URL is configurable with `VITE_MAP_TILE_URL`; retain visible OSM attribution and comply with the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Do not bulk download tiles.
