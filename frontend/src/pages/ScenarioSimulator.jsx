import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { AlertCircle, Building2, Leaf, RotateCcw, SlidersHorizontal } from "lucide-react";
import PageIntro from "../components/PageIntro.jsx";
import { getCoolRoofConfig, getMapCellDetail, getTreeCanopyConfig, simulateScenario } from "../services/api.js";

const TILE_URL = import.meta.env.VITE_MAP_TILE_URL?.trim() || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

function formatTemperature(value) {
  return `${Number(value).toFixed(2)} °C`;
}

function FitCell({ geometry }) {
  const map = useMap();
  useEffect(() => {
    const bounds = L.geoJSON({ type: "Feature", geometry, properties: {} }).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [65, 65], maxZoom: 18 });
  }, [geometry, map]);
  return null;
}

function CellMap({ geometry, latitude, longitude, temperature, color, label }) {
  const feature = { type: "Feature", geometry, properties: {} };
  return <div className="overflow-hidden rounded-xl border border-[#dfe8de] bg-white">
    <div className="flex items-center justify-between border-b border-[#eaf0e9] px-3 py-2 text-xs">
      <span className="font-semibold text-[#31543b]">{label}</span>
      <span className="font-semibold text-[#31543b]">{formatTemperature(temperature)}</span>
    </div>
    <div className="h-[230px]">
      <MapContainer center={[latitude, longitude]} zoom={17} zoomControl={false} scrollWheelZoom={false}
        preferCanvas className="h-full w-full">
        <TileLayer url={TILE_URL} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        <FitCell geometry={geometry} />
        <GeoJSON key={`${label}-${temperature}`} data={feature}
          style={{ color: "#274936", weight: 2, fillColor: color, fillOpacity: 0.78 }} />
      </MapContainer>
    </div>
  </div>;
}

export default function ScenarioSimulator() {
  const [searchParams] = useSearchParams();
  const selectedGridId = searchParams.get("grid_id");
  const requestToken = useRef(0);
  const [config, setConfig] = useState(null);
  const [roofConfig, setRoofConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const [gridId, setGridId] = useState(searchParams.get("grid_id") || "");
  const [feasibleArea, setFeasibleArea] = useState("");
  const [increase, setIncrease] = useState(0);
  const [retrofit, setRetrofit] = useState(0);
  const [eligibleRoofArea, setEligibleRoofArea] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [mapCell, setMapCell] = useState({ status: "idle", data: null, message: "" });
  const [compare, setCompare] = useState(false);

  useEffect(() => {
    if (selectedGridId) {
      requestToken.current += 1;
      setGridId(selectedGridId);
      setResult(null);
      setError("");
      setSubmitting(false);
      setMapCell({ status: "idle", data: null, message: "" });
      setCompare(false);
    }
  }, [selectedGridId]);

  function invalidateScenario() {
    requestToken.current += 1;
    setResult(null);
    setError("");
    setMapCell({ status: "idle", data: null, message: "" });
    setCompare(false);
    setSubmitting(false);
  }

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getTreeCanopyConfig(controller.signal), getCoolRoofConfig(controller.signal)])
      .then(([treeSettings, roofSettings]) => { setConfig(treeSettings); setRoofConfig(roofSettings); })
      .catch((requestError) => {
        if (requestError.name !== "CanceledError") {
          setConfigError("The simulation settings are unavailable. Check the backend connection.");
        }
      });
    return () => controller.abort();
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setResult(null);
    setError("");
    if (!gridId.trim()) {
      setError("Enter a real grid ID.");
      return;
    }
    if (increase === 0 && retrofit === 0) {
      setError("Move at least one intervention slider above zero.");
      return;
    }
    const ground = feasibleArea === "" ? null : Number(feasibleArea);
    const roof = eligibleRoofArea === "" ? null : Number(eligibleRoofArea);
    if ((ground !== null && (!Number.isFinite(ground) || ground < 0 || ground > 900))
      || (roof !== null && (!Number.isFinite(roof) || roof < 0 || roof > 900))
      || (ground !== null && roof !== null && ground + roof > 900)
      || (increase > 0 && ground !== null && ground < (900 * increase) / 100)
      || (retrofit > 0 && roof !== null && roof <= 0)) {
      setError("Check entered capacities: each is 0–900 m², together they fit one cell, and planting ground covers the requested canopy increase.");
      return;
    }
    const token = ++requestToken.current;
    setMapCell({ status: "idle", data: null, message: "" });
    setCompare(false);
    setSubmitting(true);
    try {
      const payload = {
        grid_id: gridId.trim(),
        scenario_type: increase > 0 && retrofit > 0 ? "combined" : increase > 0 ? "tree_canopy" : "cool_roof",
        ...(increase > 0 ? { canopy_increase_percentage_points: increase,
          ...(ground === null ? {} : { feasible_ground_area_m2: ground }) } : {}),
        ...(retrofit > 0 ? { retrofit_fraction: retrofit / 100,
          ...(roof === null ? {} : { eligible_roof_area_m2: roof }) } : {}),
      };
      const response = await simulateScenario(payload);
      if (token !== requestToken.current) return;
      setResult(response);
      setMapCell({ status: "loading", data: null, message: "" });
      try {
        const cell = await getMapCellDetail(gridId.trim());
        if (token === requestToken.current) {
          setMapCell(cell.geometry ? { status: "ready", data: cell, message: "" }
            : { status: "no-data", data: null, message: "This cell has no map geometry." });
        }
      } catch (mapError) {
        if (token === requestToken.current) setMapCell({ status: "error", data: null,
          message: mapError.response?.status === 503 ? "Cell geometry requires the matching real grid and model." : "Could not load cell geometry." });
      }
    } catch (requestError) {
      if (token !== requestToken.current) return;
      if (requestError.response?.status === 503) {
        setError("A matching real grid dataset, trained XGBoost model, and spatial CV RMSE are required before a scenario range can be shown.");
      } else {
        setError(requestError.response?.data?.detail || "The simulation could not run. Check the backend connection.");
      }
    } finally {
      if (token === requestToken.current) setSubmitting(false);
    }
  }

  function resetScenario() {
    invalidateScenario();
    setIncrease(0); setRetrofit(0); setFeasibleArea(""); setEligibleRoofArea("");
  }

  return (
    <>
      <PageIntro
        eyebrow="Intervention planning"
        title="Intervention simulator"
        description="Test tree canopy, cool roofs, or both together by modifying a grid cell's features and re-running the XGBoost LST model."
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)] sm:p-7">
          <div className="flex items-center gap-2 text-[#397a50]">
            <SlidersHorizontal size={19} aria-hidden="true" />
            <h2 className="text-sm font-semibold text-[#294532]">Tree canopy + cool roof scenarios</h2>
          </div>
          <p className="mt-2 text-xs leading-5 text-[#718276]">The increase is in percentage points of a 30 m cell. For example, a 10-point increase requires 90 m² of additional canopy area.</p>
          <form onSubmit={handleSubmit} className="mt-7 space-y-6">
            <label className="block text-sm font-medium text-[#294532]">
              <span className="flex items-center justify-between gap-2">Grid cell ID <Link to="/heat-map" className="text-xs font-semibold text-[#397a50] hover:underline">Choose on heat map</Link></span>
              <input
                value={gridId}
                onChange={(event) => { setGridId(event.target.value); invalidateScenario(); }}
                placeholder="Select a real grid cell"
                className="mt-2 w-full rounded-xl border border-[#dce7dc] bg-white px-3 py-2.5 text-sm text-[#294532] outline-none focus:border-[#5a9a6c]"
              />
            </label>
            <label className="block text-sm font-medium text-[#294532]">
              Available planting ground (m², optional when verified spatial capacity exists)
              <input
                type="number"
                min="0"
                max={config?.cell_area_m2}
                step="0.01"
                value={feasibleArea}
                onChange={(event) => { setFeasibleArea(event.target.value); invalidateScenario(); }}
                placeholder="Leave blank to use verified spatial capacity"
                className="mt-2 w-full rounded-xl border border-[#dce7dc] bg-white px-3 py-2.5 text-sm text-[#294532] outline-none focus:border-[#5a9a6c]"
              />
              <span className="mt-1 block text-xs font-normal leading-5 text-[#7b8c7e]">Entered capacity is labelled user-supplied. If blank, the API uses a documented verified capacity column when available; built percentage alone is never treated as plantable ground.</span>
            </label>
            <div>
              <div className="flex items-center justify-between text-sm font-medium text-[#294532]">
                <label htmlFor="canopy-increase">Tree canopy increase</label>
                <span>+{increase}%</span>
              </div>
              <input
                id="canopy-increase"
                type="range"
                min="0"
                max={config?.max_canopy_increase_percentage_points ?? 0}
                step="1"
                value={increase}
                disabled={!config}
                onChange={(event) => { setIncrease(Number(event.target.value)); invalidateScenario(); }}
                className="mt-4 w-full accent-[#397a50] disabled:opacity-40"
              />
              <div className="mt-1 flex justify-between text-xs text-[#7b8c7e]">
                <span>0%</span><span>{config ? `+${config.max_canopy_increase_percentage_points}%` : "Loading settings"}</span>
              </div>
              {config && <p className="mt-3 text-xs text-[#7b8c7e]">Additional canopy area requested: {(config.cell_area_m2 * increase / 100).toFixed(1)} m²</p>}
            </div>
            <div className="border-t border-[#edf1ec] pt-6">
              <div className="flex items-center gap-2 text-[#397a50]"><Building2 size={17} aria-hidden="true" /><h3 className="text-sm font-semibold text-[#294532]">Cool roof retrofit</h3></div>
              <label className="mt-4 block text-sm font-medium text-[#294532]">
                Eligible roof area (m², optional when verified spatial capacity exists)
                <input
                  type="number"
                  min="0"
                  max={roofConfig?.cell_area_m2}
                  step="0.01"
                  value={eligibleRoofArea}
                  onChange={(event) => { setEligibleRoofArea(event.target.value); invalidateScenario(); }}
                  placeholder="Leave blank to use verified spatial capacity"
                  className="mt-2 w-full rounded-xl border border-[#dce7dc] bg-white px-3 py-2.5 text-sm text-[#294532] outline-none focus:border-[#5a9a6c]"
                />
                <span className="mt-1 block text-xs font-normal leading-5 text-[#7b8c7e]">Entered capacity is labelled user-supplied. A blank value requires a verified per-cell roof-capacity field; non-roof ground remains unchanged.</span>
              </label>
              <div className="mt-5 flex items-center justify-between text-sm font-medium text-[#294532]">
                <label htmlFor="roof-retrofit">Retrofit share of eligible roof</label>
                <span>{retrofit}%</span>
              </div>
              <input
                id="roof-retrofit"
                type="range"
                min="0"
                max={roofConfig?.max_retrofit_percent_of_eligible_roof ?? 0}
                step="1"
                value={retrofit}
                disabled={!roofConfig}
                onChange={(event) => { setRetrofit(Number(event.target.value)); invalidateScenario(); }}
                className="mt-4 w-full accent-[#397a50] disabled:opacity-40"
              />
              <div className="mt-1 flex justify-between text-xs text-[#7b8c7e]">
                <span>0%</span><span>{roofConfig ? `${roofConfig.max_retrofit_percent_of_eligible_roof}%` : "Loading settings"}</span>
              </div>
              {eligibleRoofArea !== "" && <p className="mt-3 text-xs text-[#7b8c7e]">Roof area to retrofit: {(Number(eligibleRoofArea) * retrofit / 100).toFixed(1)} m²</p>}
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={!config || !roofConfig || submitting}
                className="rounded-xl bg-[#397a50] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#2d6842] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Running XGBoost…" : "Run selected scenario"}
              </button>
              <button type="button" onClick={resetScenario}
                className="inline-flex items-center gap-2 rounded-xl border border-[#dce7dc] px-5 py-2.5 text-sm font-semibold text-[#31543b] hover:bg-[#f3f8f2]">
                <RotateCcw size={15} aria-hidden="true" /> Reset scenario
              </button>
            </div>
          </form>
          {(configError || error) && (
            <p role="alert" className="mt-5 flex items-start gap-2 rounded-xl border border-[#eadfca] bg-[#fcf8f0] p-3 text-sm text-[#856834]">
              <AlertCircle size={17} className="mt-0.5 shrink-0" aria-hidden="true" />
              {configError || error}
            </p>
          )}
          {result && (
            <div className="mt-8 border-t border-[#e4ebe3] pt-6">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#5c8465]">Model what-if estimate · not observed cooling</p>
              {result.training_support?.is_ood && <div role="alert" className="mt-4 rounded-xl border border-[#e8c99f] bg-[#fff7e8] p-4 text-xs leading-5 text-[#805d2e]">
                <p className="font-semibold">Out-of-distribution warning</p><p className="mt-1">The vector remains inside observed training extrema but one or more modified features fall outside the training p01–p99 range. Treat this model sensitivity result with additional caution.</p>
                <ul className="mt-2 list-disc pl-5">{result.training_support.warnings.map((warning) => <li key={warning.feature}>{warning.feature}: {warning.scenario_value.toFixed(4)}; typical range {warning.typical_training_range[0].toFixed(4)}–{warning.typical_training_range[1].toFixed(4)}</li>)}</ul>
              </div>}
              {result.training_support?.is_ood === false && <p className="mt-3 inline-flex rounded-full bg-[#e8f4eb] px-3 py-1 text-[11px] font-semibold text-[#2e7548]">Scenario vector is within the model’s training p01–p99 ranges</p>}
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {[
                  ["Baseline LST", result.baseline_lst_c],
                  ["Scenario LST", result.scenario_lst_c],
                  ["ΔLST (scenario − baseline)", result.delta_lst_c],
                  ["Cooling magnitude", result.cooling_magnitude_c],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-[#e4ebe3] bg-[#f8faf7] p-4">
                    <p className="text-xs text-[#718276]">{label}</p>
                    <p className="mt-2 text-xl font-semibold text-[#294532]">{formatTemperature(value)}</p>
                  </div>
                ))}
              </div>
              <section className="mt-6 rounded-xl border border-[#e4ebe3] bg-[#fbfcfa] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-[#294532]">Grid cell map</h3>
                    <p className="mt-1 text-xs text-[#718276]">The selected 30 m cell is colored by the model's LST estimates.</p>
                  </div>
                  <button type="button" aria-pressed={compare} onClick={() => setCompare((value) => !value)}
                    className="rounded-lg border border-[#a9c7ae] px-3 py-2 text-xs font-semibold text-[#31543b] hover:bg-[#edf5ec]">
                    {compare ? "Show scenario only" : "Compare baseline vs scenario"}
                  </button>
                </div>
                {mapCell.status === "loading" && <p role="status" className="mt-4 text-xs text-[#718276]">Loading selected cell geometry…</p>}
                {(mapCell.status === "error" || mapCell.status === "no-data") &&
                  <p role="status" className="mt-4 text-xs text-[#856834]">{mapCell.message} The numeric model result remains available above.</p>}
                {mapCell.status === "ready" && (
                  <div className={`mt-4 grid gap-3 ${compare ? "lg:grid-cols-2" : ""}`}>
                    {compare && <CellMap geometry={mapCell.data.geometry} latitude={mapCell.data.latitude}
                      longitude={mapCell.data.longitude} temperature={result.baseline_lst_c}
                      color={result.delta_lst_c < 0 ? "#e3975b" : result.delta_lst_c > 0 ? "#397d85" : "#77a7a2"}
                      label="Baseline predicted LST" />}
                    <CellMap geometry={mapCell.data.geometry} latitude={mapCell.data.latitude}
                      longitude={mapCell.data.longitude} temperature={result.scenario_lst_c}
                      color={result.delta_lst_c < 0 ? "#397d85" : result.delta_lst_c > 0 ? "#e3975b" : "#77a7a2"}
                      label="Scenario predicted LST" />
                  </div>
                )}
                {mapCell.status === "ready" && <p className="mt-3 text-[11px] leading-4 text-[#718276]">Blue-green marks the cooler estimate and orange the warmer estimate for this pair. Colors are relative to this comparison, not a citywide LST scale. The map geometry is unchanged by the scenario.</p>}
              </section>
              {result.retrofit_area_m2 !== undefined && <p className="mt-4 text-xs text-[#617566]">Retrofitted roof area: {result.retrofit_area_m2.toFixed(1)} m² · Grid albedo: {result.changed_albedo.baseline.toFixed(3)} → {result.changed_albedo.scenario.toFixed(3)}</p>}
              {result.changed_ndbi && <p className="mt-2 text-xs text-[#617566]">Empirical NDBI adjustment: {result.changed_ndbi.baseline.toFixed(3)} → {result.changed_ndbi.scenario.toFixed(3)}</p>}
              {result.uncertainty && (
                <section className="mt-6 rounded-xl border border-[#dce9dd] bg-[#f3f8f2] p-4">
                  <h3 className="text-sm font-semibold text-[#294532]">Uncalibrated model-sensitivity range</h3>
                  <p className="mt-2 text-2xl font-semibold text-[#2f6240]">
                    {formatTemperature(result.uncertainty.lower_bound_c)} to {formatTemperature(result.uncertainty.upper_bound_c)}
                  </p>
                  <p className="mt-2 text-xs text-[#617566]">Model-estimated cooling magnitude: {formatTemperature(result.uncertainty.mean_cooling_c)} · MVP communication category: {result.uncertainty.confidence_category}</p>
                  <p className="mt-3 text-xs leading-5 text-[#617566]">{result.uncertainty.prediction_horizon}</p>
                  <p className="mt-2 text-xs font-semibold leading-5 text-[#795b32]">{result.uncertainty.interval_label}. This is not a coverage-calibrated interval.</p>
                  <p className="mt-2 text-xs leading-5 text-[#617566]">{result.uncertainty.assumptions.limitations}</p>
                  <details className="mt-3 text-xs text-[#617566]">
                    <summary className="cursor-pointer font-semibold">Show uncertainty assumptions</summary>
                    <p className="mt-2">Model spatial CV RMSE: {formatTemperature(result.uncertainty.sigma_model_c)} · Parameter σ: {formatTemperature(result.uncertainty.sigma_param_c)} · Total σ: {formatTemperature(result.uncertainty.sigma_total_c)}</p>
                    <p className="mt-2">Configured intervention CV: {Object.entries(result.uncertainty.assumptions.selected_cv_coefficients).map(([name, value]) => `${name} ${value}`).join(", ")}</p>
                    <p className="mt-2">{result.uncertainty.assumptions.label}</p>
                    <p className="mt-2"><strong>Uncertainty provenance:</strong> {result.uncertainty.provenance.parameter_source}</p>
                    <p className="mt-2"><strong>Horizon provenance:</strong> {result.uncertainty.provenance.growth_horizon_source}</p>
                    <p className="mt-2"><strong>Survival:</strong> {result.uncertainty.provenance.survival_source}</p>
                  </details>
                </section>
              )}
              {result.feasibility && <section className="mt-6 rounded-xl border border-[#e4ebe3] bg-[#f8faf7] p-4 text-xs leading-5 text-[#617566]">
                <h3 className="text-sm font-semibold text-[#294532]">Feasibility evidence</h3>
                {Object.entries(result.feasibility).map(([name, evidence]) => <p key={name} className="mt-2"><strong>{name.replaceAll("_", " ")}:</strong> {evidence.value_m2.toFixed(1)} m² · {evidence.source_type.replaceAll("_", " ")}. {evidence.source || evidence.verified_source || "No independent spatial verification recorded by the API."}{evidence.method ? ` Method: ${evidence.method}.` : ""}</p>)}
              </section>}
              <h3 className="mt-6 text-sm font-semibold text-[#294532]">Modified model features</h3>
              <ul className="mt-2 space-y-2 text-xs text-[#617566]">
                {Object.entries(result.modified_features).map(([name, values]) => (
                  <li key={name}>{name}: {values.baseline.toFixed(3)} → {values.scenario.toFixed(3)}</li>
                ))}
              </ul>
              <section className="mt-6 rounded-xl border border-[#e4ebe3] bg-[#f8faf7] p-4 text-xs leading-5 text-[#617566]">
                <h3 className="text-sm font-semibold text-[#294532]">Assumptions used for this run</h3>
                {result.assumptions.tree_canopy && <p className="mt-2"><strong>Tree canopy:</strong> {result.assumptions.tree_canopy.label} NDVI change per canopy point: {result.assumptions.tree_canopy.ndvi_per_canopy_percentage_point}.</p>}
                {result.assumptions.cool_roof && <p className="mt-2"><strong>Cool roof:</strong> {result.assumptions.cool_roof.label} Existing roof albedo: {result.assumptions.cool_roof.existing_roof_albedo}; cool roof albedo: {result.assumptions.cool_roof.cool_roof_albedo}; empirical NDBI coefficient: {result.assumptions.cool_roof.k_roof_ndbi_per_retrofit_fraction}.</p>}
                {result.assumptions.label && <p className="mt-2">{result.assumptions.label}</p>}
                {(result.assumptions.tree_canopy?.provenance || result.assumptions.provenance) && <p className="mt-2"><strong>Canopy evidence:</strong> {(result.assumptions.tree_canopy?.provenance || result.assumptions.provenance).canopy_to_ndvi}</p>}
                {(result.assumptions.cool_roof?.provenance || result.assumptions.provenance)?.roof_albedo && <p className="mt-2"><strong>Roof evidence:</strong> {(result.assumptions.cool_roof?.provenance || result.assumptions.provenance).roof_albedo}</p>}
                {result.assumptions.combined_note && <p className="mt-2">{result.assumptions.combined_note}</p>}
                {result.assumptions.limitations && <p className="mt-2">{result.assumptions.limitations}</p>}
              </section>
            </div>
          )}
        </section>
        <aside className="space-y-5">
          <section className="rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5">
            <div className="flex items-center gap-2 text-[#397a50]"><Leaf size={18} aria-hidden="true" /><h2 className="text-sm font-semibold">MVP assumption</h2></div>
            <p className="mt-3 text-xs leading-5 text-[#607d66]">{config?.assumption_label || "Loading backend assumptions"}</p>
            {config && <><p className="mt-3 text-xs font-semibold uppercase tracking-wide text-[#80653b]">Evidence status: {config.evidence_status.replaceAll("_", " ")}</p><p className="mt-2 text-xs leading-5 text-[#607d66]">NDVI changes by {config.ndvi_per_canopy_percentage_point} per canopy percentage point before clipping. {config.provenance.canopy_to_ndvi}</p><p className="mt-2 text-xs leading-5 text-[#607d66]">Growth horizon: {config.provenance.growth_horizon}. Survival: {config.provenance.survival}.</p></>}
          </section>
          <section className="rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5">
            <div className="flex items-center gap-2 text-[#397a50]"><Building2 size={18} aria-hidden="true" /><h2 className="text-sm font-semibold">Cool roof assumption</h2></div>
            <p className="mt-3 text-xs leading-5 text-[#607d66]">{roofConfig?.assumption_label || "Loading backend assumptions"}</p>
            {roofConfig && <><p className="mt-3 text-xs font-semibold uppercase tracking-wide text-[#80653b]">Evidence status: {roofConfig.evidence_status.replaceAll("_", " ")}</p><p className="mt-2 text-xs leading-5 text-[#607d66]">Assumed existing roof albedo {roofConfig.existing_roof_albedo}; cool roof albedo {roofConfig.cool_roof_albedo}. Empirical NDBI coefficient {roofConfig.k_roof_ndbi_per_retrofit_fraction} (zero means unchanged). {roofConfig.provenance.roof_albedo}</p></>}
          </section>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5">
            <h2 className="text-sm font-semibold text-[#294532]">Interpretation</h2>
            <p className="mt-3 text-xs leading-5 text-[#718276]">The model may predict warming or cooling. Cooling magnitude is zero when scenario LST is not lower. Results describe model sensitivity to assumed feature changes, not measured or causal intervention effects. LST is not pedestrian air temperature.</p>
            {result && <p className="mt-3 text-xs leading-5 text-[#718276]">{result.assumptions.combined_note || result.assumptions.limitations || result.assumptions.cool_roof?.limitations}</p>}
          </section>
        </aside>
      </div>
    </>
  );
}
