import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { GeoJSON, MapContainer, TileLayer, ZoomControl, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { AlertCircle, Database, Layers3, LoaderCircle, MapPinned, RotateCcw, ThermometerSun } from "lucide-react";
import "leaflet/dist/leaflet.css";
import PageIntro from "../components/PageIntro.jsx";
import SatelliteHeatLayer from "../components/SatelliteHeatLayer.jsx";
import { SATELLITE_LST, validSatelliteDate } from "../utils/satelliteLayer.js";
import { getMapCellDetail, getMapWardDetail, getMapWards, getVisibleCellHeat, getWardHeat } from "../services/api.js";

const COLORS = ["#397d85", "#77a7a2", "#d9d18a", "#e3975b", "#ad4e42"];
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL?.trim() || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const initial = { status: "loading", data: null, message: "" };

function failure(error) {
  const unavailable = error?.response?.status === 503;
  return { status: unavailable ? "no-data" : "error", data: null,
    message: unavailable ? "Required real ward, grid, or model files are not available yet."
      : error?.response?.data?.detail || error?.message || "Could not load map data." };
}

function color(value, range) {
  if (!range || !Number.isFinite(value)) return "#bac9bb";
  const t = range.max === range.min ? 0.5 : Math.max(0, Math.min(1, (value - range.min) / (range.max - range.min)));
  return COLORS[Math.min(4, Math.floor(t * 5))];
}

function ViewEvents({ onChange }) {
  const map = useMapEvents({ moveend: () => update(), zoomend: () => update() });
  const update = useCallback(() => {
    const bounds = map.getBounds();
    onChange({ zoom: map.getZoom(), west: bounds.getWest(), south: bounds.getSouth(),
      east: bounds.getEast(), north: bounds.getNorth() });
  }, [map, onChange]);
  useEffect(() => { update(); }, [update]);
  return null;
}

function FitWards({ data }) {
  const map = useMap();
  useEffect(() => {
    if (!data?.features?.length) return;
    const bounds = L.geoJSON(data).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 13 });
  }, [data, map]);
  return null;
}

function Status({ label, layer }) {
  const tone = layer.status === "ready" ? "bg-[#e8f4eb] text-[#2e7548]"
    : layer.status === "error" ? "bg-[#fff0eb] text-[#a75242]" : "bg-[#f5f1e7] text-[#94743e]";
  const description = layer.status === "ready" ? "Available" : layer.status === "loading" ? "Loading"
    : layer.status === "error" ? "Error" : "Awaiting data";
  return <div className="flex items-center justify-between border-b border-[#eef1ec] py-2.5 last:border-0">
    <span className="text-xs text-[#607467]">{label}</span>
    <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${tone}`}>{description}</span>
  </div>;
}

function Selection({ selected, detail }) {
  if (!selected) return <div className="py-8 text-center"><MapPinned size={27} className="mx-auto text-[#7c9d83]" strokeWidth={1.5} />
    <p className="mt-3 text-sm font-semibold text-[#344e3b]">Select a ward or cell</p>
    <p className="mt-2 text-xs leading-5 text-[#7b8d80]">Click a boundary or heat cell to retrieve model details.</p></div>;
  if (detail.status === "loading") return <p className="flex items-center gap-2 py-7 text-xs text-[#728477]"><LoaderCircle size={16} className="animate-spin" /> Retrieving selection…</p>;
  if (detail.status !== "ready") return <div className="rounded-xl border border-[#e9ddc7] bg-[#fbf8ef] p-3 text-xs leading-5 text-[#806f4e]">
    <p className="flex items-center gap-2 font-semibold"><AlertCircle size={15} /> {detail.status === "error" ? "Connection error" : "Selection data unavailable"}</p>
    <p className="mt-1 break-words">{detail.message}</p></div>;
  const value = detail.data;
  return <div className="space-y-4">
    <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#6c9978]">{value.selection_type === "ward" ? "Ward selection" : "30 m grid cell"}</p>
      <h3 className="mt-1 text-lg font-semibold text-[#24432e]">{value.ward_name}</h3>
      <p className="mt-1 break-all text-[11px] text-[#8b9b8d]">{value.grid_id || value.ward_id}</p>
      {value.selection_type === "ward" && <p className="mt-1 text-[11px] text-[#7d8d80]">Mean of {value.grid_cell_count?.toLocaleString()} modeled cells</p>}</div>
    <div className="rounded-xl border border-[#dceadd] bg-[#f2f8f1] p-4">
      <p className="flex items-center gap-2 text-xs text-[#547a5c]"><ThermometerSun size={16} /> Predicted land surface temperature</p>
      <p className="mt-2 text-[29px] font-semibold leading-none text-[#1f5036]">{value.predicted_lst_c.toFixed(1)}<span className="ml-1 text-base">°C</span></p></div>
    <div className="grid grid-cols-2 gap-2.5">
      <div className="rounded-xl border border-[#e6ece4] p-3"><p className="text-[11px] text-[#718476]">Heat Hazard Score</p>
        <p className="mt-1 text-sm font-semibold text-[#315b40]">{value.heat_hazard_score == null ? "Unavailable" : `${value.heat_hazard_score.toFixed(0)} / 100`}</p></div>
      <div className="rounded-xl border border-[#e6ece4] p-3"><p className="text-[11px] text-[#718476]">Confidence</p>
        <p className="mt-1 text-xs font-semibold leading-5 text-[#315b40]">{value.confidence.label}</p></div></div>
    {value.heat_hazard_score == null && <p className="text-[11px] leading-5 text-[#8a8069]">Score unavailable until documented LST references are calibrated.</p>}
    {value.confidence.spatial_cv_rmse_c != null && <p className="text-[11px] leading-5 text-[#718476]">Held-out spatial RMSE: {value.confidence.spatial_cv_rmse_c.toFixed(2)}°C. This is not a cell-level interval.</p>}
    <div className="border-t border-[#edf1eb] pt-4"><h4 className="text-xs font-semibold text-[#2a4933]">Top SHAP factors</h4>
      <p className="mt-1 text-[11px] leading-4 text-[#819184]">{value.shap_scope}</p>
      <div className="mt-3 space-y-2.5">{value.top_shap_factors.map((factor) => <div key={factor.feature} className="flex items-center justify-between gap-3 text-xs">
        <span className="truncate text-[#64796a]">{factor.feature.replaceAll("_", " ")}</span>
        <span className={`shrink-0 font-semibold ${factor.mean_shap_value_c > 0 ? "text-[#b45e4a]" : "text-[#337f76]"}`}>
          {factor.mean_shap_value_c > 0 ? "+" : ""}{factor.mean_shap_value_c.toFixed(2)}°C</span></div>)}</div></div>
    {value.selection_type === "grid_cell" && <div className="grid gap-2">
      <Link to={`/root-cause?grid_id=${encodeURIComponent(value.grid_id)}`}
        className="block rounded-lg border border-[#b9d3bd] bg-[#f2f8f1] px-3 py-2.5 text-center text-xs font-semibold text-[#2f6c45] hover:bg-[#e8f3e8] focus:outline-none focus:ring-2 focus:ring-[#6d9d79]">
        Explain this prediction
      </Link>
      <Link to={`/scenario-simulator?grid_id=${encodeURIComponent(value.grid_id)}`}
        className="block rounded-lg bg-[#397a50] px-3 py-2.5 text-center text-xs font-semibold text-white hover:bg-[#2d6842] focus:outline-none focus:ring-2 focus:ring-[#6d9d79]">
        Simulate an intervention for this cell
      </Link>
    </div>}
  </div>;
}

export default function HeatMap() {
  const [mode, setMode] = useState("satellite");
  const [date, setDate] = useState(SATELLITE_LST.defaultDate);
  const [opacity, setOpacity] = useState(0.7);
  const [satellite, setSatellite] = useState({ status: "loading", message: "Loading NASA imagery…" });
  const satelliteMode = mode === "satellite";
  const dateValid = validSatelliteDate(date);
  const [boundaries, setBoundaries] = useState(initial);
  const [wardHeat, setWardHeat] = useState(initial);
  const [cellHeat, setCellHeat] = useState({ status: "idle", data: null, message: "" });
  const [viewport, setViewport] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState({ status: "idle", data: null, message: "" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (satelliteMode) return;
    const boundaryAbort = new AbortController();
    const heatAbort = new AbortController();
    setBoundaries(initial); setWardHeat(initial);
    getMapWards(boundaryAbort.signal)
      .then((data) => setBoundaries({ status: data.features?.length ? "ready" : "no-data", data, message: "Boundary file has no wards." }))
      .catch((error) => { if (error.code !== "ERR_CANCELED") setBoundaries(failure(error)); });
    getWardHeat(heatAbort.signal)
      .then((data) => setWardHeat({ status: data.features?.length ? "ready" : "no-data", data, message: "No modeled ward cells." }))
      .catch((error) => { if (error.code !== "ERR_CANCELED") setWardHeat(failure(error)); });
    return () => { boundaryAbort.abort(); heatAbort.abort(); };
  }, [reload, satelliteMode]);

  const onViewport = useCallback((view) => setViewport(view), []);
  useEffect(() => {
    if (satelliteMode || !viewport || viewport.zoom < 16) { setCellHeat({ status: "idle", data: null, message: "" }); return; }
    const abort = new AbortController();
    setCellHeat({ status: "loading", data: null, message: "" });
    const timer = window.setTimeout(() => getVisibleCellHeat({ west: viewport.west, south: viewport.south,
      east: viewport.east, north: viewport.north }, abort.signal)
      .then((data) => setCellHeat({ status: data.too_many_cells ? "too-many" : data.features?.length ? "ready" : "no-data",
        data, message: data.message || "" }))
      .catch((error) => { if (error.code !== "ERR_CANCELED") setCellHeat(failure(error)); }), 250);
    return () => { window.clearTimeout(timer); abort.abort(); };
  }, [viewport, reload, satelliteMode]);

  const selectWard = useCallback((id) => setSelected({ kind: "ward", id }), []);
  const selectCell = useCallback((id) => setSelected({ kind: "cell", id }), []);
  useEffect(() => {
    if (satelliteMode || !selected) return;
    const abort = new AbortController();
    setDetail({ status: "loading", data: null, message: "" });
    const fetcher = selected.kind === "ward" ? getMapWardDetail : getMapCellDetail;
    fetcher(selected.id, abort.signal)
      .then((data) => setDetail({ status: "ready", data, message: "" }))
      .catch((error) => { if (error.code !== "ERR_CANCELED") setDetail(failure(error)); });
    return () => abort.abort();
  }, [selected, reload, satelliteMode]);

  const detailed = viewport?.zoom >= 16 && cellHeat.status === "ready";
  const range = useMemo(() => {
    if (detailed) {
      const values = cellHeat.data.features.map((item) => item.properties.predicted_lst_c);
      return values.length ? { min: Math.min(...values), max: Math.max(...values) } : null;
    }
    return wardHeat.status === "ready" ? wardHeat.data.temperature_range_c : null;
  }, [detailed, cellHeat, wardHeat]);
  const wards = boundaries.data?.features || [];
  const noData = boundaries.status === "no-data" && wardHeat.status === "no-data";
  const hasError = boundaries.status === "error" || wardHeat.status === "error";

  return <>
    <PageIntro eyebrow="Spatial analysis" title="Pune / PCMC heat map"
      description="Explore dated NASA satellite surface temperatures over Pune / PCMC, or switch to the research model's 30 m predictions when its data are available." />
    <fieldset className="mb-5 flex flex-wrap gap-3 rounded-xl border border-[#dfe8de] bg-white p-4">
      <legend className="px-1 text-xs font-semibold text-[#294a35]">Heat layer source</legend>
      {[ ["satellite", "Satellite observations · NASA MODIS"], ["model", "Research model · 30 m predictions"] ].map(([value, label]) =>
        <label key={value} className="flex items-center gap-2 text-sm text-[#36533d]">
          <input type="radio" name="heat-source" value={value} checked={mode === value}
            onChange={() => { setMode(value); setSelected(null); }} />{label}
        </label>)}
    </fieldset>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
      <section className="min-w-0 overflow-hidden rounded-2xl border border-[#dfe8de] bg-white shadow-[0_3px_18px_rgba(23,54,35,0.05)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#eaf0e9] px-5 py-4">
          <div><h2 className="flex items-center gap-2 text-sm font-semibold text-[#284936]"><Layers3 size={17} className="text-[#438263]" /> {satelliteMode ? "Satellite land surface temperature" : "Predicted LST layer"}</h2>
            <p className="mt-1 text-[11px] text-[#829385]">{satelliteMode ? `Terra / MODIS daytime · ${date || "select a date"} · approximately 1 km source resolution` : "Ward means at city scale · 30 m cells at zoom 16+"}</p></div>
          <button type="button" onClick={() => setReload((value) => value + 1)} className="inline-flex items-center gap-1.5 rounded-lg border border-[#d9e6d9] px-3 py-1.5 text-[11px] font-semibold text-[#39714d] hover:bg-[#f2f8f0]"><RotateCcw size={13} /> Refresh</button>
        </div>
        <div className="relative h-[470px] bg-[#edf2ed] sm:h-[560px]">
          <MapContainer center={[18.565, 73.865]} zoom={11} minZoom={10} maxZoom={19}
            zoomControl={false} preferCanvas scrollWheelZoom className="h-full w-full">
            <TileLayer url={TILE_URL} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
            <ZoomControl position="topright" />
            <ViewEvents onChange={onViewport} />
            {satelliteMode && dateValid && <SatelliteHeatLayer key={`${date}-${reload}`} date={date} opacity={opacity} onStatus={setSatellite} />}
            {!satelliteMode && <FitWards data={boundaries.status === "ready" ? boundaries.data : null} />}
            {!satelliteMode && wardHeat.status === "ready" && !detailed && <GeoJSON key={`ward-${reload}`} data={wardHeat.data}
              style={(feature) => ({ color: "#456d52", weight: 1.2, fillColor: color(feature.properties.predicted_lst_c, range), fillOpacity: 0.62 })}
              onEachFeature={(feature, layer) => layer.on("click", () => selectWard(feature.properties.ward_id))} />}
            {!satelliteMode && detailed && <GeoJSON key={`cell-${viewport.west}-${viewport.south}`} data={cellHeat.data}
              style={(feature) => ({ color: color(feature.properties.predicted_lst_c, range), weight: 0.15,
                fillColor: color(feature.properties.predicted_lst_c, range), fillOpacity: 0.82 })}
              onEachFeature={(feature, layer) => layer.on("click", () => selectCell(feature.properties.grid_id))} />}
            {!satelliteMode && boundaries.status === "ready" && <GeoJSON key={`outline-${reload}`} data={boundaries.data}
              interactive={wardHeat.status !== "ready" && !detailed}
              style={{ color: "#264b37", weight: 1.8, fillOpacity: 0, opacity: 0.85 }}
              onEachFeature={(feature, layer) => layer.on("click", () => selectWard(feature.properties.ward_id))} />}
          </MapContainer>
          {!satelliteMode && (noData || hasError) && <div className="pointer-events-none absolute left-4 top-4 z-[500] max-w-[min(360px,calc(100%-32px))] rounded-xl border border-[#e1e7df] bg-white/95 p-4 shadow-lg" aria-live="polite">
            <div className="flex items-start gap-2.5">{hasError ? <AlertCircle size={18} className="mt-0.5 shrink-0 text-[#aa6a4c]" /> : <Database size={18} className="mt-0.5 shrink-0 text-[#818d72]" />}
              <div><p className="text-xs font-semibold text-[#314e38]">{hasError ? "Map layer connection error" : "30 m model inputs are missing"}</p>
                <p className="mt-1 text-[11px] leading-5 text-[#718172]">{hasError ? "Check FastAPI, then refresh." : "This model needs verified wards, the ML grid and trained XGBoost weights. Switch to Satellite observations to see NASA surface-temperature imagery now."}</p></div></div></div>}
          {!satelliteMode && viewport?.zoom >= 16 && cellHeat.status === "too-many" && <div className="pointer-events-none absolute bottom-8 left-4 z-[500] rounded-lg border border-[#e6d9bd] bg-white/95 px-3 py-2 text-[11px] font-medium text-[#806c43] shadow-sm">Zoom in further to display the 30 m cells.</div>}
          {!satelliteMode && viewport?.zoom >= 16 && cellHeat.status === "loading" && <div className="pointer-events-none absolute bottom-8 left-4 z-[500] flex items-center gap-2 rounded-lg bg-white/95 px-3 py-2 text-[11px] text-[#4d7458] shadow-sm"><LoaderCircle size={13} className="animate-spin" /> Loading cells…</div>}
        </div>
        <div className="flex flex-wrap justify-between gap-2 border-t border-[#eaf0e9] px-5 py-3 text-[11px] text-[#728576]"><span>{satelliteMode ? `NASA satellite retrieval · ${date} · historical imagery` : "Model-estimated surface temperature · °C"}</span><span>Geographic basemap: OpenStreetMap</span></div>
      </section>
      <aside className="space-y-4">
        {satelliteMode ? <>
          <section className="rounded-2xl border border-[#e2e9e0] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-[#294a35]">Satellite layer controls</h2>
            <label className="mt-4 block text-xs font-medium text-[#617665]">Observation date (UTC)
              <input type="date" value={date} min={SATELLITE_LST.firstDate} max={new Date().toISOString().slice(0, 10)}
                onChange={(event) => setDate(event.target.value)} className="mt-2 block w-full rounded-lg border border-[#d8e4d8] px-3 py-2" />
            </label>
            <p className="mt-2 text-xs leading-5 text-[#718172]">Starts on 10 May 2025, within the research's peak-summer season. This is a dated observation, not current weather or a seasonal average.</p>
            <label className="mt-4 block text-xs font-medium text-[#617665]">Heat layer opacity: {Math.round(opacity * 100)}%
              <input type="range" min="0" max="1" step="0.05" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} className="mt-2 block w-full" />
            </label>
            <p role="status" className="mt-4 text-xs leading-5 text-[#607467]">{dateValid ? satellite.message : "Choose a valid observation date on or before today."}</p>
            <p className="mt-2 text-xs leading-5 text-[#718172]">Zooming enlarges the imagery; it does not create 30 m detail. Cloud and overpass gaps can leave some dates empty.</p>
          </section>
          <section className="rounded-2xl border border-[#e2e9e0] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-[#294a35]">NASA temperature legend</h2>
            <img src={SATELLITE_LST.legendUrl} alt="NASA land surface temperature color scale from below 200 to above 350 kelvin" className="mt-3 h-auto w-full" />
            <p className="mt-3 text-xs leading-5 text-[#718172]">The source legend uses kelvin. °C = K − 273.15; 300 K = 26.85°C and 325 K = 51.85°C.</p>
          </section>
          <section className="rounded-2xl border border-[#e2e9e0] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-[#294a35]">Source & interpretation</h2>
            <p className="mt-2 text-xs leading-5 text-[#718172]">NASA GIBS publishes Terra/MODIS daytime land-surface temperature retrievals at approximately 1 km source resolution. This imagery is independent of the GreenPulse model and does not supply SHAP values, intervention estimates or ward statistics.</p>
            <a href={SATELLITE_LST.metadataUrl} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs font-semibold text-[#39714d] underline">NASA layer metadata</a>
          </section>
        </> : <>

        <section className="rounded-2xl border border-[#e2e9e0] bg-white p-5 shadow-sm"><h2 className="text-sm font-semibold text-[#294a35]">Map layers</h2>
          <div className="mt-3"><Status label="Ward boundaries" layer={boundaries} /><Status label="Predicted ward heat" layer={wardHeat} />
            {viewport?.zoom >= 16 && <Status label="Visible 30 m cells" layer={cellHeat} />}</div>
          {(boundaries.status === "no-data" || wardHeat.status === "no-data") && <p className="mt-3 break-words text-[11px] leading-5 text-[#8c8066]">{boundaries.message || wardHeat.message}</p>}
          {wards.length > 0 && <label className="mt-4 block text-[11px] font-medium text-[#617665]">Select a ward
            <select value={selected?.kind === "ward" ? selected.id : ""} onChange={(event) => event.target.value && selectWard(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#d8e4d8] bg-white px-3 py-2 text-xs text-[#36533d] focus:border-[#6a9e77] focus:outline-none">
              <option value="">Choose a loaded ward</option>
              {wards.map((feature) => <option key={feature.properties.ward_id} value={feature.properties.ward_id}>{feature.properties.ward_name} · {feature.properties.ward_id}</option>)}
            </select></label>}</section>
        <section className="rounded-2xl border border-[#e2e9e0] bg-white p-5 shadow-sm"><h2 className="text-sm font-semibold text-[#294a35]">Predicted LST legend</h2>
          {range ? <><div className="mt-3 flex h-3 overflow-hidden rounded-full">{COLORS.map((shade) => <span key={shade} className="flex-1" style={{ backgroundColor: shade }} />)}</div>
            <div className="mt-2 flex justify-between text-[11px] font-medium text-[#657a6a]"><span>{range.min.toFixed(1)}°C</span><span>{range.max.toFixed(1)}°C</span></div>
            <p className="mt-2 text-[11px] leading-5 text-[#88978a]">Relative colors for the displayed model layer.</p></>
            : <p className="mt-3 text-xs leading-5 text-[#829183]">No climate prediction range available.</p>}</section>
        <section className="rounded-2xl border border-[#e2e9e0] bg-white p-5 shadow-sm" aria-live="polite">
          <div className="flex justify-between gap-2"><h2 className="text-sm font-semibold text-[#294a35]">Selection details</h2>
            {selected && <button type="button" onClick={() => { setSelected(null); setDetail({ status: "idle", data: null, message: "" }); }} className="text-[11px] font-semibold text-[#518460] hover:underline">Clear</button>}</div>
          <div className="mt-4"><Selection selected={selected} detail={detail} /></div></section>
        </>}
        <p className="px-1 text-[11px] leading-5 text-[#819083]">LST is not pedestrian air temperature. SHAP explains model predictions and does not prove causation.</p>
      </aside>
    </div>
  </>;
}
