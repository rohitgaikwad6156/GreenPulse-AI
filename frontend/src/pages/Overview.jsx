import { useEffect, useState } from "react";
import { ArrowRight, MapPinned, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import BackendStatus from "../components/BackendStatus.jsx";
import PageIntro from "../components/PageIntro.jsx";
import { getMethodology } from "../services/api.js";
import { researchWorkflow } from "../utils/researchWorkflow.js";

export default function Overview() {
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState({ loading: true, data: null, error: "" });
  useEffect(() => {
    const controller = new AbortController();
    setStatus({ loading: true, data: null, error: "" });
    getMethodology(controller.signal)
      .then((data) => {
        if (!data?.data_status) throw new Error("The backend returned an incomplete research status.");
        if (!controller.signal.aborted) setStatus({ loading: false, data: data.data_status, error: "" });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setStatus({ loading: false, data: null,
          error: error.response ? `The backend returned HTTP ${error.response.status}. Retry after the service is available.`
            : "Cannot check research inputs. The backend may be starting; retry the connection." });
      });
    return () => controller.abort();
  }, [attempt]);
  const stages = researchWorkflow(status.data);
  const cards = [
    ["Satellite ML grid", status.data?.real_ml_grid_available, "Observed Landsat LST and aligned features"],
    ["Trained XGBoost model", status.data?.trained_model_available, "Saved model and metadata; results require validation"],
    ["Planning evidence", status.data?.optimizer_location_available, "At least one location with verified planning inputs"],
  ];

  return <>
    <PageIntro eyebrow="Pune / PCMC climate planning" title="From surface heat to climate action"
      description="Follow the research workflow: locate heat, explain model predictions, compare interventions, optimize a budget and evaluate observed outcomes." />
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <BackendStatus key={attempt} />
      {cards.map(([label, present, detail]) => <section key={label} className="rounded-2xl border border-[#e4ebe3] bg-white p-5">
        <h2 className="text-xs font-semibold text-[#6f8274]">{label}</h2>
        <p className="mt-4 text-lg font-semibold text-[#294532]">{status.loading ? "Checking…" : !status.data ? "Not checked" : present ? "Inputs present" : "Inputs needed"}</p>
        <p className="mt-3 text-xs leading-5 text-[#687c6d]">{detail}</p>
      </section>)}
    </div>
    <section className="mt-5 rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-[#294532]">Research input status</h2>
        <button type="button" disabled={status.loading} onClick={() => setAttempt((value) => value + 1)}
          className="inline-flex items-center gap-2 rounded-lg border border-[#c8dcca] bg-white px-3 py-2 text-xs font-semibold text-[#32774a] disabled:opacity-50">
          <RefreshCw size={14} aria-hidden="true" /> Refresh status
        </button>
      </div>
      <p role="status" className="mt-2 text-sm leading-6 text-[#536d59]">
        {status.loading ? "Checking the backend for research artifacts. A sleeping service may take about a minute to start."
          : status.error || (status.data.real_ml_grid_available && status.data.trained_model_available
            ? "Grid and model files are present. Open each research stage to run its evidence and compatibility checks."
            : "The research pipeline is implemented, but the real satellite grid and trained model are not both available. Climate predictions require these inputs.")}
      </p>
      <p className="mt-2 text-xs leading-5 text-[#536d59]">Input availability is separate from model accuracy and field validation. Missing measurements are never replaced with demonstration values.</p>
    </section>
    <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
        <h2 className="text-lg font-semibold text-[#294532]">Your research workflow</h2>
        <ol className="mt-4 space-y-3">
          {stages.map((stage) => <li key={stage.to} className="rounded-xl border border-[#e4ebe3] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link to={stage.to} className="inline-flex items-center gap-2 font-semibold text-[#32774a] hover:underline">{stage.title}<ArrowRight size={15} aria-hidden="true" /></Link>
              <span className="rounded-full bg-[#f2f6f1] px-2 py-1 text-xs text-[#607467]">{status.loading ? "Checking…" : stage.state}</span>
            </div>
            <p className="mt-2 text-sm leading-6 text-[#687c6d]">{stage.detail}</p>
            <p className="mt-1 text-xs leading-5 text-[#687c6d]">{stage.missing}</p>
          </li>)}
        </ol>
      </section>
      <aside className="space-y-5">
        <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5">
          <MapPinned size={26} className="text-[#4e875f]" aria-hidden="true" />
          <h2 className="mt-3 font-semibold text-[#294532]">Explore the study area</h2>
          <p className="mt-2 text-sm leading-6 text-[#687c6d]">Open the interactive map to inspect available wards and grid cells. The map reports any missing climate layers.</p>
          <Link to="/heat-map" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-[#32774a]">Open heat map <ArrowRight size={15} aria-hidden="true" /></Link>
        </section>
        <section className="rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5">
          <h2 className="font-semibold text-[#2f6240]">Scientific boundary</h2>
          <p className="mt-2 text-xs leading-5 text-[#607d66]">LST measures surface temperature, not pedestrian air temperature. TreeSHAP explains the model; scenario cooling is an estimate. Heat Hazard Score is a relative display index, not a health-risk probability.</p>
          <Link to="/methodology" className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-[#32774a]">Read methodology <ArrowRight size={14} aria-hidden="true" /></Link>
        </section>
      </aside>
    </div>
  </>;
}
