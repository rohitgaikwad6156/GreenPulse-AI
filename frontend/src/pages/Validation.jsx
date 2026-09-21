import { useEffect, useRef, useState } from "react";
import { Activity, AlertCircle, FlaskConical, Plus, RotateCcw, Trash2 } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import PageIntro from "../components/PageIntro.jsx";
import { analyzeValidationDataset, calculateValidation, getValidationDatasets, getValidationDemo } from "../services/api.js";
import { calibrationEvidenceMessage } from "../utils/validationEvidence.js";

const DEMO_LABEL = "DEMO VALIDATION SCENARIO";
const USER_LABEL = "USER-SUPPLIED OBSERVATIONS — PROVENANCE NOT VERIFIED BY API";
const temperature = (value) => `${Number(value).toFixed(2)} °C`;
const ndvi = (value) => Number(value).toFixed(3);
const newRow = (key, group) => ({
  key, group, gridId: "", preLst: "", postLst: "", preNdvi: "", postNdvi: "", predictedDelta: "",
});

function finiteRange(value, label, min, max) {
  if (value === "" || !Number.isFinite(Number(value)) || Number(value) < min || Number(value) > max) {
    throw new Error(`${label} must be a number from ${min} to ${max}.`);
  }
  return Number(value);
}

function DataField({ label, value, onChange, min, max, step = "0.01", placeholder }) {
  return <label className="block text-xs font-medium text-[#526957]">{label}
    <input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder} className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-2.5 py-2 text-sm text-[#294532] outline-none focus:border-[#5a9a6c]" />
  </label>;
}

export default function Validation() {
  const nextKey = useRef(0);
  const requestToken = useRef(0);
  const [scenarioLabel, setScenarioLabel] = useState(USER_LABEL);
  const [intervention, setIntervention] = useState("");
  const [prePeriod, setPrePeriod] = useState("");
  const [postPeriod, setPostPeriod] = useState("");
  const [sourceNote, setSourceNote] = useState("");
  const [rows, setRows] = useState([]);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [datasets, setDatasets] = useState(null);
  const [selectedDataset, setSelectedDataset] = useState("");
  const [datasetError, setDatasetError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getValidationDatasets(controller.signal).then(setDatasets).catch((requestError) => {
      if (requestError.name !== "CanceledError") setDatasetError("Imported validation datasets could not be loaded.");
    });
    return () => controller.abort();
  }, []);

  async function analyzeImported() {
    if (!selectedDataset) return;
    const token = ++requestToken.current;
    setSubmitting(true); setError(""); setReport(null);
    try {
      const response = await analyzeValidationDataset(selectedDataset);
      if (token === requestToken.current) {
        setScenarioLabel(response.evidence_label); setReport(response);
      }
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      if (token === requestToken.current) setError(typeof detail === "string" ? detail : requestError.message || "Imported validation could not run.");
    } finally { if (token === requestToken.current) setSubmitting(false); }
  }

  function clearReport() {
    requestToken.current += 1;
    setReport(null); setError(""); setSubmitting(false); setLoadingDemo(false);
  }
  function updateRow(key, field, value) {
    setRows((current) => current.map((row) => row.key === key ? { ...row, [field]: value } : row));
    clearReport();
  }
  function addRow(group) {
    nextKey.current += 1;
    setRows((current) => [...current, newRow(`manual-${nextKey.current}`, group)]);
    clearReport();
  }
  function clearScenario() {
    clearReport();
    setScenarioLabel(USER_LABEL); setIntervention(""); setPrePeriod(""); setPostPeriod("");
    setSourceNote(""); setRows([]);
  }
  async function loadDemo() {
    const token = ++requestToken.current;
    setLoadingDemo(true); setSubmitting(false); setError(""); setReport(null);
    try {
      const demo = await getValidationDemo();
      if (token !== requestToken.current) return;
      if (demo.scenario_label !== DEMO_LABEL) throw new Error("The demo response lacks its synthetic-data label.");
      const grouped = new Map();
      demo.observations.forEach((item) => {
        const key = `${item.group}/${item.grid_id}`;
        if (!grouped.has(key)) grouped.set(key, newRow(`demo-${grouped.size}`, item.group));
        const row = grouped.get(key);
        row.gridId = item.grid_id;
        row[`${item.period}Lst`] = String(item.lst_c);
        row[`${item.period}Ndvi`] = item.ndvi == null ? "" : String(item.ndvi);
      });
      const predictions = new Map(demo.predictions.map((item) => [item.grid_id, item.predicted_delta_lst_c]));
      setRows([...grouped.values()].map((row) => ({
        ...row, predictedDelta: predictions.has(row.gridId) ? String(predictions.get(row.gridId)) : "",
      })));
      setScenarioLabel(DEMO_LABEL);
      setIntervention(demo.intervention); setPrePeriod(demo.pre_period); setPostPeriod(demo.post_period);
      setSourceNote(demo.source_note || "");
    } catch (requestError) {
      if (token === requestToken.current) setError(requestError.message || "Could not load the explicitly labelled demo scenario.");
    } finally { if (token === requestToken.current) setLoadingDemo(false); }
  }

  function buildPayload() {
    if (!intervention.trim() || !prePeriod.trim() || !postPeriod.trim() || !sourceNote.trim()) {
      throw new Error("Enter the intervention, distinct pre/post periods, and a source/provenance note.");
    }
    if (prePeriod.trim() === postPeriod.trim()) throw new Error("Pre and post periods must differ.");
    if (!rows.some((row) => row.group === "treated") || !rows.some((row) => row.group === "control")) {
      throw new Error("Add at least one paired treated cell and one paired control cell.");
    }
    const ndviEntries = rows.flatMap((row) => [row.preNdvi, row.postNdvi]);
    const useNdvi = ndviEntries.some((value) => value !== "");
    if (useNdvi && ndviEntries.some((value) => value === "")) {
      throw new Error("Enter pre and post NDVI for every cell, or leave every NDVI field empty.");
    }
    const treated = rows.filter((row) => row.group === "treated");
    const usePredictions = treated.some((row) => row.predictedDelta !== "");
    if (usePredictions && treated.some((row) => row.predictedDelta === "")) {
      throw new Error("Enter a predicted ΔLST for every treated cell, or leave all predictions empty.");
    }
    const observations = rows.flatMap((row) => {
      if (!row.gridId.trim()) throw new Error("Every row needs a grid cell ID.");
      return ["pre", "post"].map((period) => ({
        grid_id: row.gridId.trim(), group: row.group, period,
        lst_c: finiteRange(row[`${period}Lst`], `${row.gridId} ${period} LST`, -100, 100),
        ndvi: useNdvi ? finiteRange(row[`${period}Ndvi`], `${row.gridId} ${period} NDVI`, -1, 1) : null,
      }));
    });
    const predictions = usePredictions ? treated.map((row) => ({
      grid_id: row.gridId.trim(),
      predicted_delta_lst_c: finiteRange(row.predictedDelta, `${row.gridId} predicted ΔLST`, -100, 100),
    })) : [];
    return { scenario_label: scenarioLabel, intervention: intervention.trim(),
      pre_period: prePeriod.trim(), post_period: postPeriod.trim(), source_note: sourceNote.trim(),
      observations, predictions };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const token = ++requestToken.current;
    setReport(null); setError("");
    let payload;
    try { payload = buildPayload(); }
    catch (validationError) { setError(validationError.message); return; }
    setSubmitting(true);
    try {
      const response = await calculateValidation(payload);
      if (token === requestToken.current) setReport(response);
    }
    catch (requestError) {
      const detail = requestError.response?.data?.detail;
      if (token === requestToken.current) setError(typeof detail === "string" ? detail : requestError.message || "Validation could not run.");
    } finally { if (token === requestToken.current) setSubmitting(false); }
  }

  const isDemo = scenarioLabel === DEMO_LABEL;
  const isProvenanceReport = Boolean(report?.report_schema_version);
  const comparison = report?.prediction_comparison || [];
  const predictedMean = comparison.length
    ? comparison.reduce((sum, row) => sum + row.predicted_delta_lst_c, 0) / comparison.length : null;
  const residualMean = comparison.length
    ? comparison.reduce((sum, row) => sum + row.residual_c, 0) / comparison.length : null;
  const trend = report && !isProvenanceReport ? [
    { period: "Pre", Treated: report.group_means_c.treated.pre, Control: report.group_means_c.control.pre },
    { period: "Post", Treated: report.group_means_c.treated.post, Control: report.group_means_c.control.post },
  ] : report?.provenance?.periods.map((period) => ({
    period: period.period_id,
    Treated: report.period_group_means_c.treated[period.period_id],
    Control: report.period_group_means_c.control[period.period_id],
  })) || [];

  return <>
    <PageIntro eyebrow="Post-implementation evidence" title="Validation"
      description="Compare paired treated and control grid cells across two periods, then check modeled LST changes against control-adjusted follow-up observations." />
    <div className="grid gap-5 xl:grid-cols-[minmax(0,520px)_minmax(0,1fr)]">
      <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)] sm:p-6">
        <div className="flex items-center gap-2 text-[#397a50]"><Activity size={19} aria-hidden="true" />
          <h2 className="text-sm font-semibold text-[#294532]">Paired observations</h2></div>
        <p className="mt-2 text-xs leading-5 text-[#718276]">Imported datasets are checksum-verified against the 30 m grid. The manual calculator below remains descriptive and cannot verify typed provenance.</p>
        <div className="mt-4 rounded-xl border border-[#dce9dd] bg-[#f5f9f4] p-4">
          <label className="block text-xs font-semibold text-[#294532]">Imported real intervention dataset
            <select value={selectedDataset} onChange={(event) => setSelectedDataset(event.target.value)}
              disabled={!datasets?.datasets.length}
              className="mt-2 w-full rounded-lg border border-[#dce7dc] bg-white px-3 py-2 text-sm disabled:bg-[#eef1ed]">
              <option value="">{datasets?.datasets.length ? "Select imported dataset" : "No genuine dataset available"}</option>
              {datasets?.datasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>
                {item.location_id} · {item.intervention_id} · {item.dataset_version}
              </option>)}
            </select>
          </label>
          <button type="button" onClick={analyzeImported} disabled={!selectedDataset || submitting}
            className="mt-3 rounded-lg bg-[#397a50] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">
            Analyze imported evidence
          </button>
          {datasets?.validation_status === "BLOCKED" && <p className="mt-3 text-xs leading-5 text-[#856834]">Real-validation status: BLOCKED — {datasets.blocker}</p>}
          {datasetError && <p className="mt-3 text-xs text-[#a55345]">{datasetError}</p>}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={loadDemo} disabled={loadingDemo}
            className="inline-flex items-center gap-2 rounded-lg border border-[#d9cda9] bg-[#fcf9ef] px-3 py-2 text-xs font-semibold text-[#775f29] disabled:opacity-50">
            <FlaskConical size={15} aria-hidden="true" /> {loadingDemo ? "Loading demo…" : "Load DEMO VALIDATION SCENARIO"}
          </button>
          <button type="button" onClick={clearScenario}
            className="inline-flex items-center gap-2 rounded-lg border border-[#dce7dc] px-3 py-2 text-xs font-semibold text-[#31543b]">
            <RotateCcw size={15} aria-hidden="true" /> Start blank
          </button>
        </div>
        {isDemo && <p className="mt-4 rounded-xl border border-[#e8d9a8] bg-[#fff9e8] p-3 text-xs font-bold leading-5 text-[#775f29]">
          DEMO / SYNTHETIC DATA — invented workflow test values, not Pune or PCMC measurements or model performance.
        </p>}
        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          <label className="block text-xs font-medium text-[#526957]">Intervention
            <input value={intervention} onChange={(event) => { setIntervention(event.target.value); clearReport(); }}
              placeholder="Describe the implemented action"
              className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-3 py-2 text-sm text-[#294532] outline-none focus:border-[#5a9a6c]" />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-[#526957]">Before period
              <input value={prePeriod} onChange={(event) => { setPrePeriod(event.target.value); clearReport(); }}
                placeholder="e.g. March–May year 1" className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-3 py-2 text-sm text-[#294532]" />
            </label>
            <label className="block text-xs font-medium text-[#526957]">After period
              <input value={postPeriod} onChange={(event) => { setPostPeriod(event.target.value); clearReport(); }}
                placeholder="e.g. March–May year 2" className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-3 py-2 text-sm text-[#294532]" />
            </label>
          </div>
          <label className="block text-xs font-medium text-[#526957]">Source and comparability note
            <textarea value={sourceNote} onChange={(event) => { setSourceNote(event.target.value); clearReport(); }}
              placeholder="Data source, scene dates, QA method, control selection"
              rows={2} className="mt-1.5 w-full resize-y rounded-lg border border-[#dce7dc] px-3 py-2 text-sm text-[#294532]" />
          </label>
          {["treated", "control"].map((group) => <div key={group} className="border-t border-[#e8eee7] pt-5">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold capitalize text-[#294532]">{group} area</h3>
              <button type="button" onClick={() => addRow(group)} className="inline-flex items-center gap-1 text-xs font-semibold text-[#397a50]">
                <Plus size={14} aria-hidden="true" /> Add grid cell
              </button>
            </div>
            <p className="mt-1 text-xs leading-5 text-[#718276]">{group === "treated" ? "Cells receiving the intervention." : "Comparable cells without this intervention."}</p>
            <div className="mt-3 space-y-3">
              {rows.filter((row) => row.group === group).map((row) => <div key={row.key} className="rounded-xl border border-[#e4ebe3] bg-[#fbfcfa] p-3">
                <div className="flex items-center gap-2">
                  <input aria-label={`${group} grid cell ID`} value={row.gridId} onChange={(event) => updateRow(row.key, "gridId", event.target.value)}
                    placeholder="30 m grid cell ID" className="min-w-0 flex-1 rounded-lg border border-[#dce7dc] px-2.5 py-2 text-sm text-[#294532]" />
                  <button type="button" aria-label={`Remove ${row.gridId || group} cell`}
                    onClick={() => { setRows((current) => current.filter((item) => item.key !== row.key)); clearReport(); }}
                    className="rounded-lg p-2 text-[#8d6c5d] hover:bg-[#f7ebe6]"><Trash2 size={16} aria-hidden="true" /></button>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <DataField label="Before LST (°C)" value={row.preLst} onChange={(value) => updateRow(row.key, "preLst", value)} min="-100" max="100" />
                  <DataField label="After LST (°C)" value={row.postLst} onChange={(value) => updateRow(row.key, "postLst", value)} min="-100" max="100" />
                  <DataField label="Before NDVI (optional)" value={row.preNdvi} onChange={(value) => updateRow(row.key, "preNdvi", value)} min="-1" max="1" step="0.001" />
                  <DataField label="After NDVI (optional)" value={row.postNdvi} onChange={(value) => updateRow(row.key, "postNdvi", value)} min="-1" max="1" step="0.001" />
                  {group === "treated" && <DataField label="Predicted ΔLST (°C, optional)" value={row.predictedDelta}
                    onChange={(value) => updateRow(row.key, "predictedDelta", value)} min="-100" max="100" />}
                </div>
              </div>)}
              {!rows.some((row) => row.group === group) && <p className="rounded-xl border border-dashed border-[#dce7dc] p-4 text-xs text-[#839286]">No {group} cells entered.</p>}
            </div>
          </div>)}
          <button type="submit" disabled={submitting}
            className="w-full rounded-xl bg-[#397a50] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#2d6842] disabled:opacity-50">
            {submitting ? "Calculating validation…" : "Calculate validation"}
          </button>
        </form>
        {error && <p role="alert" className="mt-4 flex gap-2 rounded-xl border border-[#eadfca] bg-[#fcf8f0] p-3 text-sm text-[#856834]">
          <AlertCircle size={17} className="mt-0.5 shrink-0" aria-hidden="true" />{error}
        </p>}
      </section>

      <div className="space-y-5">
        {!report ? <section className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-center">
          <Activity className="mx-auto text-[#79a984]" size={30} aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold text-[#294532]">No follow-up analysis yet</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[#718276]">Enter paired observed LST for treated and control cells, with optional NDVI and predicted changes. Or load the explicitly labelled demo to test the workflow.</p>
        </section> : <>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <p className={`text-xs font-bold uppercase tracking-[0.1em] ${isDemo || report.validation_status === "BLOCKED" ? "text-[#94652e]" : "text-[#5c8465]"}`}>{report.label || `${report.evidence_label} · ${report.validation_status}`}</p>
            <h2 className="mt-2 text-lg font-semibold text-[#294532]">Predicted vs actual follow-up</h2>
            <p className="mt-2 text-xs leading-5 text-[#718276]">{report.source_note || (report.provenance ? `${report.provenance.source.organization} · ${report.provenance.source.product} · ${report.dataset_version}` : "")}</p>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {[
                ["Predicted ΔLST", predictedMean == null ? "Unavailable" : temperature(predictedMean)],
                [isDemo ? "Synthetic actual ΔLST" : "Control-adjusted actual ΔLST", temperature(report.difference_in_differences_c)],
                ["Difference · actual − predicted", residualMean == null ? "Unavailable" : temperature(residualMean)],
                ["Difference-in-Differences", temperature(report.difference_in_differences_c)],
              ].map(([label, value]) => <div key={label} className="rounded-xl border border-[#e5ece4] bg-[#f8faf7] p-3">
                <p className="text-xs leading-5 text-[#718276]">{label}</p>
                <p className="mt-2 text-lg font-semibold text-[#294532]">{value}</p>
              </div>)}
            </div>
            <p className="mt-4 text-xs leading-5 text-[#617566]">Treated change {temperature(report.treated_change_c)} minus control change {temperature(report.control_change_c)} = DiD {temperature(report.difference_in_differences_c)}. Signed realized cooling = {temperature(report.realized_cooling_c)}; negative means relative warming.</p>
            {report.ndvi_changes ? <p className="mt-2 text-xs text-[#617566]">ΔNDVI: treated {ndvi(report.ndvi_changes.treated)} · control {ndvi(report.ndvi_changes.control)}. NDVI change alone does not prove the intervention caused cooling.</p>
              : <p className="mt-2 text-xs text-[#718276]">ΔNDVI unavailable because paired NDVI was not supplied.</p>}
          </section>
          {isProvenanceReport && <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <h2 className="text-sm font-semibold text-[#294532]">Provenance and sample</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[["Treated cells", report.sample_size.treated_cells], ["Control cells", report.sample_size.control_cells],
                ["Pre periods", report.sample_size.pre_periods], ["Post periods", report.sample_size.post_periods]]
                .map(([label, value]) => <div key={label} className="rounded-xl bg-[#f7faf6] p-3"><p className="text-xs text-[#718276]">{label}</p><p className="mt-1 text-lg font-semibold text-[#294532]">{value}</p></div>)}
            </div>
            <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
              <div><dt className="text-[#718276]">Season / CRS</dt><dd className="mt-1 font-medium text-[#294532]">{report.provenance.season} · {report.provenance.crs}</dd></div>
              <div><dt className="text-[#718276]">QA policy</dt><dd className="mt-1 font-medium text-[#294532]">{report.provenance.qa_policy}</dd></div>
              <div><dt className="text-[#718276]">Observation hash</dt><dd className="mt-1 break-all font-mono text-[#294532]">{report.provenance.observations_sha256}</dd></div>
              <div><dt className="text-[#718276]">Grid hash</dt><dd className="mt-1 break-all font-mono text-[#294532]">{report.provenance.reference_grid_sha256}</dd></div>
            </dl>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs">
              <thead className="border-b border-[#e4ebe3] text-[#718276]"><tr><th className="py-2">Period</th><th>Phase</th><th>Date</th><th>Scene</th><th>Overpass</th><th>QA</th></tr></thead>
              <tbody>{report.provenance.periods.map((period) => <tr key={period.period_id} className="border-b border-[#edf1ec]"><td className="py-2 font-medium">{period.period_id}</td><td>{period.phase}</td><td>{period.acquisition_date}</td><td>{period.scene_id}</td><td>{period.overpass_time_local}</td><td>{period.qa_criteria}</td></tr>)}</tbody>
            </table></div>
          </section>}
          {isProvenanceReport && <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <h2 className="text-sm font-semibold text-[#294532]">Diagnostics and uncertainty</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-[#f7faf6] p-4"><p className="text-xs text-[#718276]">Parallel pre-trends</p><p className="mt-1 font-semibold text-[#294532]">{report.parallel_trends.passed ? "Within declared threshold" : "FAILED"}</p><p className="mt-1 text-xs text-[#718276]">Absolute slope difference {report.parallel_trends.absolute_slope_difference_c_per_period.toFixed(3)} °C/period; threshold {report.parallel_trends.declared_threshold_c_per_period}.</p></div>
              <div className="rounded-xl bg-[#f7faf6] p-4"><p className="text-xs text-[#718276]">Control spillover screen</p><p className="mt-1 font-semibold text-[#294532]">{report.control_diagnostics.passed ? "No controls inside declared distance" : "CONTAMINATED CONTROLS"}</p><p className="mt-1 text-xs text-[#718276]">{report.control_diagnostics.contaminated_controls.length} flagged; minimum distance {report.control_diagnostics.nearest_treated_distance_m_min.toFixed(0)} m.</p></div>
              <div className="rounded-xl bg-[#f7faf6] p-4"><p className="text-xs text-[#718276]">95% interval</p><p className="mt-1 font-semibold text-[#294532]">{report.uncertainty.lower_c == null ? "Unavailable" : `${temperature(report.uncertainty.lower_c)} to ${temperature(report.uncertainty.upper_c)}`}</p><p className="mt-1 text-xs text-[#718276]">{report.uncertainty.method}. {report.uncertainty.coverage_warning}</p></div>
              <div className="rounded-xl bg-[#f7faf6] p-4"><p className="text-xs text-[#718276]">Spatial autocorrelation</p><p className="mt-1 font-semibold text-[#294532]">{report.spatial_autocorrelation.moran_i == null ? "Unavailable" : `Moran’s I ${report.spatial_autocorrelation.moran_i.toFixed(3)}`}</p><p className="mt-1 text-xs text-[#718276]">{report.spatial_autocorrelation.warning || "No positive residual autocorrelation warning from the declared neighborhood."}</p></div>
            </div>
            <p className="mt-4 rounded-xl border border-[#eadfca] bg-[#fcf8f0] p-3 text-xs leading-5 text-[#856834]">Calibration: {calibrationEvidenceMessage(report)}</p>
          </section>}
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <h2 className="text-sm font-semibold text-[#294532]">Treated and control LST by period</h2>
            <p className="mt-1 text-xs text-[#718276]">Group means from the entered paired cells, not a causal effect plot.</p>
            <div className="mt-3 h-[260px] w-full" role="img" aria-label="Line chart comparing treated and control mean LST before and after">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 10, right: 25, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke="#e8eee7" strokeDasharray="3 3" />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: "#718276" }} />
                  <YAxis unit=" °C" tick={{ fontSize: 11, fill: "#718276" }} width={58} domain={["dataMin - 1", "dataMax + 1"]} />
                  <Tooltip formatter={(value) => temperature(value)} />
                  <Legend />
                  <Line type="linear" dataKey="Treated" stroke="#c97451" strokeWidth={2.5} dot={{ r: 4 }} />
                  <Line type="linear" dataKey="Control" stroke="#397d85" strokeWidth={2.5} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <h2 className="text-sm font-semibold text-[#294532]">Prediction performance</h2>
            {report.performance ? <>
              <p className="mt-2 text-xs leading-5 text-[#718276]">{report.performance.residual_definition || report.performance.definition}; M = {report.performance.count_treated_cells || report.performance.count} treated cells.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-[#f7faf6] p-4"><p className="text-xs text-[#718276]">Validation MAE</p><p className="mt-1 text-xl font-semibold text-[#294532]">{temperature(report.performance.mae_c)}</p></div>
                <div className="rounded-xl bg-[#f7faf6] p-4"><p className="text-xs text-[#718276]">Validation RMSE</p><p className="mt-1 text-xl font-semibold text-[#294532]">{temperature(report.performance.rmse_c)}</p></div>
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[530px] text-left text-xs">
                  <thead className="border-b border-[#e4ebe3] text-[#718276]"><tr><th className="py-2 pr-3">Treated cell</th><th className="py-2 pr-3">Predicted Δ</th><th className="py-2 pr-3">Adjusted actual Δ</th><th className="py-2">Residual</th></tr></thead>
                  <tbody>{comparison.map((row) => <tr key={row.grid_id} className="border-b border-[#edf1ec] text-[#294532]">
                    <td className="py-2 pr-3 font-medium">{row.grid_id}</td><td className="py-2 pr-3">{temperature(row.predicted_delta_lst_c)}</td>
                    <td className="py-2 pr-3">{temperature(row.actual_control_adjusted_delta_lst_c)}</td><td className="py-2">{temperature(row.residual_c)}</td>
                  </tr>)}</tbody>
                </table>
              </div>
            </> : <p className="mt-3 text-xs leading-5 text-[#718276]">Predicted ΔLST was not supplied for every treated cell, so residual, MAE, and RMSE are unavailable.</p>}
          </section>
          <section className="rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5 text-xs leading-5 text-[#607d66]">
            <h2 className="text-sm font-semibold text-[#294532]">Scientific limits</h2>
            <ul className="mt-2 list-disc space-y-1 pl-4">{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        </>}
      </div>
    </div>
  </>;
}
