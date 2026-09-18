import { ArrowRight, Database, Layers3, MapPinned, ShieldCheck, ThermometerSun } from "lucide-react";
import { Link } from "react-router-dom";
import BackendStatus from "../components/BackendStatus.jsx";
import PageIntro from "../components/PageIntro.jsx";

const summaryCards = [
  { label: "Observed LST", detail: "Satellite layer not connected", icon: Layers3 },
  { label: "Model status", detail: "No model has been trained", icon: Database },
  { label: "Action plans", detail: "Optimizer not connected", icon: ShieldCheck },
  { label: "Heat Hazard Score", detail: "Awaiting observed LST and documented peri-urban reference", icon: ThermometerSun },
];

export default function Overview() {
  return (
    <>
      <PageIntro
        eyebrow="Planning workspace"
        title="Urban climate overview"
        description="A single place to inspect surface heat, understand model predictions, and prepare feasible climate actions for Pune and PCMC."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <BackendStatus />
        {summaryCards.map(({ label, detail, icon: Icon }) => (
          <section key={label} className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-[#6f8274]">{label}</p>
              <Icon size={17} className="text-[#6e9b79]" strokeWidth={1.8} aria-hidden="true" />
            </div>
            <div className="mt-4 text-[28px] font-semibold leading-none text-[#a7b5a8]">—</div>
            <p className="mt-3 text-xs text-[#91a092]">{detail}</p>
          </section>
        ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="overflow-hidden rounded-2xl border border-[#e4ebe3] bg-white shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#edf1ec] px-5 py-4 sm:px-6">
            <div>
              <h2 className="text-sm font-semibold text-[#294532]">Spatial overview</h2>
              <p className="mt-1 text-xs text-[#91a092]">Pune / PCMC · 30 m analysis grid planned</p>
            </div>
            <Link to="/heat-map" className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#377b50] hover:text-[#235c38]">
              Open heat map <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          <div className="spatial-grid flex min-h-[410px] flex-col items-center justify-center px-6 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[#dce9dd] bg-white text-[#4e875f] shadow-sm">
              <MapPinned size={28} strokeWidth={1.5} aria-hidden="true" />
            </div>
            <h3 className="mt-6 text-lg font-semibold text-[#294532]">Spatial layers are not connected</h3>
            <p className="mt-2 max-w-sm text-sm leading-6 text-[#7b8c7e]">
              Verified satellite observations, grid cells, and ward boundaries will appear here in a later step.
            </p>
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#6c9a76]">Project status</p>
            <h2 className="mt-2 text-base font-semibold text-[#294532]">Application shell ready</h2>
            <p className="mt-2 text-xs leading-5 text-[#7b8c7e]">Navigation is active. Climate outputs will remain empty until source data and models are verified.</p>
            <div className="mt-5 space-y-3 border-t border-[#edf1ec] pt-4 text-xs">
              <div className="flex items-center justify-between"><span className="text-[#687c6d]">Frontend routes</span><span className="font-semibold text-[#397a50]">Ready</span></div>
              <div className="flex items-center justify-between"><span className="text-[#687c6d]">Climate layers</span><span className="font-semibold text-[#a0824d]">Pending</span></div>
              <div className="flex items-center justify-between"><span className="text-[#687c6d]">Model outputs</span><span className="font-semibold text-[#a0824d]">Pending</span></div>
            </div>
          </section>
          <section className="rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5">
            <h2 className="text-sm font-semibold text-[#2f6240]">Scientific boundary</h2>
            <p className="mt-2 text-xs leading-5 text-[#607d66]">Future heat views will report land surface temperature. LST is not pedestrian air temperature.</p>
            <Link to="/methodology" className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[#32774a] hover:text-[#235c38]">
              Read methodology <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </section>
        </aside>
      </div>
    </>
  );
}
