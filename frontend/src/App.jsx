import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell.jsx";
import Overview from "./pages/Overview.jsx";

const HeatMap = lazy(() => import("./pages/HeatMap.jsx"));
const RootCauseAnalysis = lazy(() => import("./pages/RootCauseAnalysis.jsx"));
const ScenarioSimulator = lazy(() => import("./pages/ScenarioSimulator.jsx"));
const ClimateActionOptimizer = lazy(() => import("./pages/ClimateActionOptimizer.jsx"));
const Validation = lazy(() => import("./pages/Validation.jsx"));
const ResearchLayers = lazy(() => import("./pages/ResearchLayers.jsx"));
const Methodology = lazy(() => import("./pages/Methodology.jsx"));

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Overview />} />
        <Route path="/heat-map" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading heat map…</div>}><HeatMap /></Suspense>} />
        <Route path="/root-cause" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading explanation…</div>}><RootCauseAnalysis /></Suspense>} />
        <Route path="/scenario-simulator" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading simulator…</div>}><ScenarioSimulator /></Suspense>} />
        <Route path="/climate-action-optimizer" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading optimizer…</div>}><ClimateActionOptimizer /></Suspense>} />
        <Route path="/validation" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading validation…</div>}><Validation /></Suspense>} />
        <Route path="/research-layers" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading research layers…</div>}><ResearchLayers /></Suspense>} />
        <Route path="/methodology" element={<Suspense fallback={<div className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#6f8274]">Loading methodology…</div>}><Methodology /></Suspense>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
