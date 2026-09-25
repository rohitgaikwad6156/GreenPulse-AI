import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, BarChart3, CheckCircle2, Database, LoaderCircle, RotateCcw, Search, TriangleAlert } from "lucide-react";
import PageIntro from "../components/PageIntro.jsx";
import { explainGridCell, getMethodology } from "../services/api.js";

const initial = { status: "idle", data: null, message: "" };
const GROUP_LABELS = { "Vegetation / Canopy": "Vegetation", "Built Environment": "Built environment",
  "Surface Reflectivity": "Albedo / reflectivity", "Road / Infrastructure": "Mobility", Other: "Exposure / context" };

function ArtifactStatus({ availability }) {
  const files = [
    ["Real 30 m ML grid", availability?.real_ml_grid_available, "Aligned Landsat/Sentinel/GIS feature cells"],
    ["Matching XGBoost model", availability?.trained_model_available, "A saved model with spatial-validation metadata"],
  ];
  return <section className="rounded-2xl border border-[#eadfc9] bg-[#fbf8ef] p-6" role="status">
    <div className="flex items-start gap-3"><Database className="mt-0.5 shrink-0 text-[#a36d45]" size={20} aria-hidden="true" />
      <div className="min-w-0"><h2 className="font-semibold text-[#5e4c32]">Model explanation is waiting for research data</h2>
        <p className="mt-2 text-sm leading-6 text-[#806f56]">TreeSHAP needs the same validated 30 m feature grid and trained XGBoost artifact used for predictions. The NASA satellite view is real imagery, but it does not contain the model features or explainable predictions.</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">{files.map(([name, present, detail]) => <div key={name} className="rounded-xl border border-[#eadfc9] bg-white px-3 py-3"><p className="text-xs font-semibold text-[#5e4c32]">{name}: {availability ? present ? "available" : "missing" : "checking"}</p><p className="mt-1 text-[11px] leading-5 text-[#806f56]">{detail}</p></div>)}</div>
        <div className="mt-4 flex flex-wrap gap-2"><Link to="/heat-map" className="rounded-lg bg-[#397a50] px-3 py-2 text-xs font-semibold text-white hover:bg-[#2d6842]">Open satellite heat map</Link><Link to="/methodology" className="rounded-lg border border-[#dac8a7] bg-white px-3 py-2 text-xs font-semibold text-[#775c36]">View data requirements</Link></div>
      </div>
    </div>
  </section>;
}

function label(value = "") {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function groupLabel(value) { return GROUP_LABELS[value] || value; }

function featureUnit(name) {
  if (["ndvi", "ndvi_mean_3x3", "ndvi_mean_5x5", "ndbi", "ndbi_mean_3x3", "ndbi_mean_5x5", "albedo"].includes(name)) return "unitless";
  if (["tree_canopy_pct", "built_pct"].includes(name)) return "%";
  if (name === "building_fraction") return "fraction (0–1)";
  if (name === "road_density") return "km/km²";
  if (name === "distance_green_m") return "m";
  if (name === "population_density") return "people/km²";
  return "source units";
}

function number(value, digits = 3) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "Unavailable";
}

function detailMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).filter(Boolean).join(" ");
  return error?.message || "The explanation request failed.";
}

function requestFailure(error) {
  if (!error?.response) return { status: "connection-error", data: null,
    message: "Could not reach the GreenPulse API. Confirm the backend URL and that FastAPI is running." };
  const status = error.response.status;
  if (status === 404) return { status: "not-found", data: null, message: detailMessage(error) };
  if (status === 422) return { status: "invalid", data: null, message: detailMessage(error) };
  if (status === 503) return { status: "unavailable", data: null, message: detailMessage(error) };
  return { status: "error", data: null, message: detailMessage(error) };
}

function StateCard({ state, onRetry }) {
  const titles = { "not-found": "Grid cell not found", invalid: "Invalid grid cell ID",
    unavailable: "Model explanation unavailable", "connection-error": "API connection error",
    "no-data": "No explanation data returned", error: "Explanation request failed" };
  return <section className="rounded-2xl border border-[#eadfc9] bg-[#fbf8ef] p-6 shadow-sm" role="alert">
    <div className="flex items-start gap-3"><AlertCircle className="mt-0.5 shrink-0 text-[#a36d45]" size={20} aria-hidden="true" />
      <div><h2 className="font-semibold text-[#5e4c32]">{titles[state.status] || "Explanation unavailable"}</h2>
        <p className="mt-2 text-sm leading-6 text-[#806f56]">{state.message}</p>
        <div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg border border-[#dac8a7] bg-white px-3 py-2 text-xs font-semibold text-[#775c36] hover:bg-[#fffdf8] focus:outline-none focus:ring-2 focus:ring-[#ad9061]">
          <RotateCcw size={14} aria-hidden="true" /> Retry</button>
          <Link to="/heat-map" className="rounded-lg px-3 py-2 text-xs font-semibold text-[#39714d] hover:bg-[#edf5ed] focus:outline-none focus:ring-2 focus:ring-[#6d9d79]">Choose on heat map</Link></div>
      </div></div>
  </section>;
}

function SignedBars({ rows }) {
  const max = Math.max(...rows.map((row) => Math.abs(row.shap_value_c)), 0.000001);
  return <div className="space-y-3" role="list" aria-label="Signed local SHAP contributions in degrees Celsius">
    {rows.map((row) => {
      const contribution = Number(row.shap_value_c);
      const width = Math.max(1, Math.abs(contribution) / max * 48);
      const warming = contribution >= 0;
      return <div key={row.feature} role="listitem" className="grid gap-1 sm:grid-cols-[minmax(120px,180px)_minmax(180px,1fr)_74px] sm:items-center"
        aria-label={`${label(row.feature)}: ${warming ? "plus" : "minus"} ${Math.abs(contribution).toFixed(3)} degrees Celsius`}>
        <div className="min-w-0"><p className="truncate text-xs font-medium text-[#395544]">{label(row.feature)}</p><p className="text-[10px] text-[#829083]">{groupLabel(row.category)}</p></div>
        <div className="relative h-5 rounded bg-[#f2f5f1]" aria-hidden="true"><span className="absolute inset-y-0 left-1/2 w-px bg-[#8da091]" />
          <span className={`absolute inset-y-1 rounded-sm ${warming ? "bg-[#cf785f]" : "bg-[#3e8b80]"}`}
            style={{ left: warming ? "50%" : `${50 - width}%`, width: `${width}%` }} /></div>
        <p className={`text-right text-xs font-semibold ${warming ? "text-[#b75f49]" : "text-[#337c72]"}`}>{warming ? "+" : ""}{number(contribution)} °C</p>
      </div>;
    })}
    <div className="grid grid-cols-2 text-[10px] font-medium text-[#819084] sm:ml-[180px]"><span>Cooling contribution</span><span className="text-right">Warming contribution</span></div>
  </div>;
}

function RankingBars({ rows }) {
  const max = Math.max(...rows.map((row) => Number(row.mean_abs_shap_c)), 0.000001);
  return <div className="space-y-3" role="list" aria-label="Global mean absolute SHAP feature rankings">
    {rows.map((row, index) => <div key={row.feature} role="listitem" className="grid grid-cols-[22px_minmax(100px,170px)_minmax(120px,1fr)_70px] items-center gap-2"
      aria-label={`Rank ${index + 1}, ${label(row.feature)}, mean absolute contribution ${number(row.mean_abs_shap_c)} degrees Celsius`}>
      <span className="text-[11px] font-semibold text-[#829084]">{index + 1}</span><span className="truncate text-xs font-medium text-[#395544]">{label(row.feature)}</span>
      <span className="h-2.5 overflow-hidden rounded-full bg-[#edf2ec]" aria-hidden="true"><span className="block h-full rounded-full bg-[#4b8a62]" style={{ width: `${Math.max(1, Number(row.mean_abs_shap_c) / max * 100)}%` }} /></span>
      <span className="text-right text-[11px] font-semibold text-[#4a6954]">{number(row.mean_abs_shap_c)} °C</span>
    </div>)}
  </div>;
}

function GroupCards({ local, global }) {
  const globalByGroup = new Map(global.map((row) => [row.category, row.sum_feature_mean_abs_shap_c]));
  return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
    {local.map((row) => <div key={row.category} className="rounded-xl border border-[#e4ebe2] bg-[#fafcf9] p-4">
      <p className="text-[11px] font-bold uppercase tracking-[0.1em] text-[#6f8374]">{groupLabel(row.category)}</p>
      <p className={`mt-2 text-lg font-semibold ${row.shap_value_c > 0 ? "text-[#b75f49]" : row.shap_value_c < 0 ? "text-[#337c72]" : "text-[#52685a]"}`}>{row.shap_value_c > 0 ? "+" : ""}{number(row.shap_value_c)} °C</p>
      <p className="mt-1 text-[11px] text-[#839185]">Local signed contribution</p>
      {globalByGroup.has(row.category) && <p className="mt-2 border-t border-[#e8eee7] pt-2 text-[11px] text-[#627468]">Global mean absolute sum: {number(globalByGroup.get(row.category))} °C</p>}
    </div>)}
  </div>;
}

export default function RootCauseAnalysis() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedGridId = searchParams.get("grid_id") || "";
  const [gridId, setGridId] = useState(selectedGridId);
  const [state, setState] = useState(initial);
  const [validation, setValidation] = useState("");
  const [reload, setReload] = useState(0);
  const [availability, setAvailability] = useState(null);

  useEffect(() => { setGridId(selectedGridId); }, [selectedGridId]);
  useEffect(() => {
    const controller = new AbortController();
    getMethodology(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setAvailability(data?.data_status || null); })
      .catch(() => { if (!controller.signal.aborted) setAvailability(null); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selectedGridId) { setState(initial); return undefined; }
    const controller = new AbortController();
    setState({ status: "loading", data: null, message: "" });
    explainGridCell(selectedGridId, controller.signal).then((data) => {
      if (!Array.isArray(data?.local_explanation?.features)
          || !Array.isArray(data?.global_explanation?.feature_importance_bar_data)) {
        setState({ status: "no-data", data: null, message: "The API response did not contain complete local and global explanation data." });
      }
      else setState({ status: "ready", data, message: "" });
    }).catch((error) => { if (error.code !== "ERR_CANCELED") setState(requestFailure(error)); });
    return () => controller.abort();
  }, [selectedGridId, reload]);

  function submit(event) {
    event.preventDefault();
    const value = gridId.trim();
    if (!value || value.length > 120) { setValidation("Enter a grid cell ID between 1 and 120 characters."); return; }
    setValidation("");
    if (value === selectedGridId) setReload((count) => count + 1);
    else setSearchParams({ grid_id: value });
  }

  const local = state.data?.local_explanation;
  const global = state.data?.global_explanation;
  const reconstruction = useMemo(() => {
    if (!local) return null;
    const rebuilt = Number(local.baseline_lST) + local.features.reduce((sum, row) => sum + Number(row.shap_value_c), 0);
    const residual = rebuilt - Number(local.predicted_lst);
    return { rebuilt, residual, passes: Math.abs(residual) <= 0.001 + 1e-5 * Math.abs(Number(local.predicted_lst)) };
  }, [local]);

  return <>
    <PageIntro eyebrow="Model interpretation" title="Root Cause Analysis"
      description="Inspect how recorded features contribute to an XGBoost land surface temperature prediction. Attribution explains model behavior; it does not establish cause and effect." />
    <section className="rounded-2xl border border-[#dfe8de] bg-white p-5 shadow-[0_3px_18px_rgba(23,54,35,0.05)] sm:p-6">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="min-w-0 flex-1 text-sm font-medium text-[#294532]">Grid cell ID
          <input value={gridId} maxLength={120} onChange={(event) => { setGridId(event.target.value); setValidation(""); }} aria-describedby={validation ? "grid-id-error" : "grid-id-help"} aria-invalid={Boolean(validation)}
            placeholder="Select a real 30 m grid cell" className="mt-2 w-full rounded-xl border border-[#dce7dc] bg-white px-3 py-2.5 text-sm text-[#294532] outline-none focus:border-[#5a9a6c] focus:ring-2 focus:ring-[#dcebdd]" />
        </label>
        <button type="submit" disabled={state.status === "loading"} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-[#397a50] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#2d6842] focus:outline-none focus:ring-2 focus:ring-[#6d9d79] disabled:cursor-wait disabled:opacity-60">
          {state.status === "loading" ? <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> : <Search size={16} aria-hidden="true" />} Explain cell</button>
      </form>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs"><p id="grid-id-help" className="text-[#788a7c]">Use an exact grid ID from the validated ML dataset.</p><Link to="/heat-map" className="font-semibold text-[#397a50] hover:underline focus:outline-none focus:ring-2 focus:ring-[#6d9d79]">Choose a cell on the Heat Map</Link></div>
      {validation && <p id="grid-id-error" className="mt-2 text-xs font-medium text-[#a94f40]" role="alert">{validation}</p>}
    </section>

    <div className="mt-5" aria-live="polite">
      {state.status === "idle" && <div className="space-y-4"><ArtifactStatus availability={availability} /><section className="rounded-2xl border border-dashed border-[#cad8ca] bg-[#f9fbf8] px-6 py-10 text-center"><BarChart3 size={30} className="mx-auto text-[#72957b]" strokeWidth={1.5} aria-hidden="true" /><h2 className="mt-3 font-semibold text-[#34503d]">Select a real model grid cell</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[#78887c]">Enter an exact ID from the validated ML dataset or navigate here from a selected cell in the Research model heat-map view. No placeholder explanation is shown.</p></section></div>}
      {state.status === "loading" && <section className="rounded-2xl border border-[#e2e9e0] bg-white px-6 py-14 text-center"><LoaderCircle size={28} className="mx-auto animate-spin text-[#438263]" aria-hidden="true" /><p className="mt-3 text-sm font-medium text-[#526d5b]">Computing TreeSHAP explanations…</p><p className="mt-1 text-xs text-[#819084]">This may take longer for a large global sample.</p></section>}
      {!["idle", "loading", "ready"].includes(state.status) && <StateCard state={state} onRetry={() => setReload((count) => count + 1)} />}
      {state.status === "ready" && local && global && <div className="space-y-5">
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[{ name: "Predicted LST", value: `${number(local.predicted_lst, 2)} °C` }, { name: "Model baseline", value: `${number(local.baseline_lST, 2)} °C` }, { name: "Reconstructed", value: `${number(reconstruction.rebuilt, 2)} °C` }, { name: "Additivity check", value: reconstruction.passes ? "Pass" : "Review", icon: reconstruction.passes ? CheckCircle2 : TriangleAlert }].map((card) => <div key={card.name} className="rounded-2xl border border-[#e1e9df] bg-white p-5 shadow-sm"><p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#748679]">{card.name}</p><p className="mt-2 flex items-center gap-2 text-xl font-semibold text-[#285039]">{card.icon && <card.icon size={18} aria-hidden="true" />}{card.value}</p>{card.name === "Additivity check" && <p className="mt-1 text-[11px] text-[#7a8a7e]">Residual {reconstruction.residual >= 0 ? "+" : ""}{number(reconstruction.residual, 6)} °C</p>}</div>)}
        </section>

        <section className="rounded-2xl border border-[#e1e9df] bg-white p-5 shadow-sm sm:p-6"><div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="text-base font-semibold text-[#294b36]">Local signed contributions</h2><p className="mt-1 text-xs leading-5 text-[#79897c]">Raw TreeSHAP values reconstruct this cell’s model prediction in °C.</p></div><span className="rounded-full bg-[#eef5ed] px-3 py-1 text-[10px] font-bold text-[#4b7557]">{local.grid_id}</span></div><div className="mt-6"><SignedBars rows={local.features} /></div></section>

        <section className="rounded-2xl border border-[#e1e9df] bg-white p-5 shadow-sm sm:p-6"><h2 className="text-base font-semibold text-[#294b36]">Functional groups</h2><p className="mt-1 text-xs leading-5 text-[#79897c]">Local values are signed. Global values sum mean absolute feature contributions and are not directional.</p><div className="mt-5"><GroupCards local={local.group_contributions || []} global={global.group_importance_bar_data || []} /></div></section>

        <div className="grid gap-5 xl:grid-cols-2">
          <section className="rounded-2xl border border-[#e1e9df] bg-white p-5 shadow-sm sm:p-6"><h2 className="text-base font-semibold text-[#294b36]">Global importance ranking</h2><p className="mt-1 text-xs leading-5 text-[#79897c]">Mean absolute SHAP across {global.sample_rows?.toLocaleString()} of {global.dataset_rows?.toLocaleString()} cells; larger values mean greater average model influence.</p><div className="mt-5"><RankingBars rows={global.feature_importance_bar_data || []} /></div></section>
          <section className="overflow-hidden rounded-2xl border border-[#e1e9df] bg-white shadow-sm"><div className="p-5 pb-3 sm:px-6"><h2 className="text-base font-semibold text-[#294b36]">Feature values and units</h2><p className="mt-1 text-xs text-[#79897c]">Recorded model inputs for the selected cell.</p></div><div className="overflow-x-auto"><table className="w-full min-w-[460px] text-left text-xs"><thead className="bg-[#f5f8f4] text-[10px] uppercase tracking-[0.1em] text-[#718175]"><tr><th className="px-6 py-3">Feature</th><th className="px-4 py-3">Raw value</th><th className="px-4 py-3">Unit</th><th className="px-6 py-3 text-right">SHAP</th></tr></thead><tbody>{local.features.map((row) => <tr key={row.feature} className="border-t border-[#edf1ec]"><th scope="row" className="px-6 py-3 font-medium text-[#395544]">{label(row.feature)}</th><td className="px-4 py-3 tabular-nums text-[#596d5f]">{number(row.raw_value, 4)}</td><td className="px-4 py-3 text-[#76877a]">{featureUnit(row.feature)}</td><td className={`px-6 py-3 text-right font-semibold ${row.shap_value_c > 0 ? "text-[#b75f49]" : "text-[#337c72]"}`}>{row.shap_value_c > 0 ? "+" : ""}{number(row.shap_value_c)} °C</td></tr>)}</tbody></table></div></section>
        </div>

        <section className="rounded-2xl border border-[#ead9c8] bg-[#fffaf3] p-5 sm:p-6"><div className="flex items-start gap-3"><TriangleAlert size={20} className="mt-0.5 shrink-0 text-[#a56842]" aria-hidden="true" /><div><h2 className="font-semibold text-[#694b32]">Interpret attribution carefully</h2><p className="mt-2 text-sm leading-6 text-[#7d654e]">{global.redundancy_warning}</p><p className="mt-2 text-sm font-semibold leading-6 text-[#714e36]">Attribution is not causation. SHAP describes this fitted model’s prediction; it does not prove that changing a feature will cause the displayed temperature change.</p>{global.feature_correlations?.highly_redundant_pairs?.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-[#806950]">{global.feature_correlations.highly_redundant_pairs.map((pair) => <li key={`${pair.feature_a}-${pair.feature_b}`}>{label(pair.feature_a)} ↔ {label(pair.feature_b)}: r = {number(pair.pearson_r, 3)}</li>)}</ul>}</div></div></section>

        <section className="rounded-2xl border border-[#e1e9df] bg-white p-5 shadow-sm sm:p-6"><div className="flex items-center gap-2"><Database size={17} className="text-[#4d7c5b]" aria-hidden="true" /><h2 className="text-base font-semibold text-[#294b36]">Model and data provenance</h2></div><dl className="mt-4 grid gap-x-6 gap-y-4 text-xs sm:grid-cols-2"><div><dt className="font-semibold text-[#536a5a]">Dataset version</dt><dd className="mt-1 break-all text-[#77877b]">{local.model_dataset_version || global.model_dataset_version}</dd></div><div><dt className="font-semibold text-[#536a5a]">Model artifact SHA-256</dt><dd className="mt-1 break-all text-[#77877b]">{local.model_artifact_sha256 || global.model_artifact_sha256}</dd></div><div><dt className="font-semibold text-[#536a5a]">Dataset SHA-256</dt><dd className="mt-1 break-all text-[#77877b]">{local.dataset_sha256 || global.dataset_sha256}</dd></div><div><dt className="font-semibold text-[#536a5a]">Dataset metadata SHA-256</dt><dd className="mt-1 break-all text-[#77877b]">{local.dataset_metadata_sha256 || global.dataset_metadata_sha256}</dd></div><div><dt className="font-semibold text-[#536a5a]">Model metadata SHA-256</dt><dd className="mt-1 break-all text-[#77877b]">{local.model_metadata_sha256 || global.model_metadata_sha256}</dd></div><div><dt className="font-semibold text-[#536a5a]">Explanation method</dt><dd className="mt-1 text-[#77877b]">{global.method}</dd></div><div><dt className="font-semibold text-[#536a5a]">Global sample seed</dt><dd className="mt-1 text-[#77877b]">{global.sample_seed}</dd></div><div><dt className="font-semibold text-[#536a5a]">Target and unit</dt><dd className="mt-1 text-[#77877b]">Land surface temperature · °C</dd></div></dl><p className="mt-5 border-t border-[#edf1ec] pt-4 text-xs leading-5 text-[#76877a]">LST is remotely sensed land surface temperature, not pedestrian air temperature, human-health risk, vulnerability, or probability.</p></section>
      </div>}
    </div>
  </>;
}
