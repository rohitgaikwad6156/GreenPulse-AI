import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell.jsx";
import PageLoading from "./components/PageLoading.jsx";
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
        <Route path="/heat-map" element={<Suspense fallback={<PageLoading label="Loading heat map…" />}><HeatMap /></Suspense>} />
        <Route path="/root-cause" element={<Suspense fallback={<PageLoading label="Loading explanation…" />}><RootCauseAnalysis /></Suspense>} />
        <Route path="/scenario-simulator" element={<Suspense fallback={<PageLoading label="Loading simulator…" />}><ScenarioSimulator /></Suspense>} />
        <Route path="/climate-action-optimizer" element={<Suspense fallback={<PageLoading label="Loading optimizer…" />}><ClimateActionOptimizer /></Suspense>} />
        <Route path="/validation" element={<Suspense fallback={<PageLoading label="Loading validation…" />}><Validation /></Suspense>} />
        <Route path="/research-layers" element={<Suspense fallback={<PageLoading label="Loading research layers…" />}><ResearchLayers /></Suspense>} />
        <Route path="/methodology" element={<Suspense fallback={<PageLoading label="Loading methodology…" />}><Methodology /></Suspense>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
