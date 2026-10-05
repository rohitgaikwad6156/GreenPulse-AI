import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell.jsx";
import PageLoading from "./components/PageLoading.jsx";
import RouteErrorBoundary from "./components/RouteErrorBoundary.jsx";
import Overview from "./pages/Overview.jsx";

const DataReadiness = lazy(() => import("./pages/DataReadiness.jsx"));
const HeatMap = lazy(() => import("./pages/HeatMap.jsx"));
const RootCauseAnalysis = lazy(() => import("./pages/RootCauseAnalysis.jsx"));
const ScenarioSimulator = lazy(() => import("./pages/ScenarioSimulator.jsx"));
const ClimateActionOptimizer = lazy(() => import("./pages/ClimateActionOptimizer.jsx"));
const Validation = lazy(() => import("./pages/Validation.jsx"));
const ResearchLayers = lazy(() => import("./pages/ResearchLayers.jsx"));
const Methodology = lazy(() => import("./pages/Methodology.jsx"));

function RoutePage({ children, loadingLabel }) {
  const { pathname } = useLocation();
  return (
    <RouteErrorBoundary key={pathname} pathname={pathname}>
      <Suspense fallback={<PageLoading label={loadingLabel} />}>{children}</Suspense>
    </RouteErrorBoundary>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          path="/"
          element={
            <RoutePage loadingLabel="Loading overview…">
              <Overview />
            </RoutePage>
          }
        />
        <Route
          path="/heat-map"
          element={
            <RoutePage loadingLabel="Loading heat map…">
              <HeatMap />
            </RoutePage>
          }
        />
        <Route
          path="/root-cause"
          element={
            <RoutePage loadingLabel="Loading explanation…">
              <RootCauseAnalysis />
            </RoutePage>
          }
        />
        <Route
          path="/scenario-simulator"
          element={
            <RoutePage loadingLabel="Loading simulator…">
              <ScenarioSimulator />
            </RoutePage>
          }
        />
        <Route
          path="/climate-action-optimizer"
          element={
            <RoutePage loadingLabel="Loading optimizer…">
              <ClimateActionOptimizer />
            </RoutePage>
          }
        />
        <Route
          path="/validation"
          element={
            <RoutePage loadingLabel="Loading validation…">
              <Validation />
            </RoutePage>
          }
        />
        <Route
          path="/research-layers"
          element={
            <RoutePage loadingLabel="Loading research layers…">
              <ResearchLayers />
            </RoutePage>
          }
        />
        <Route
          path="/data-readiness"
          element={
            <RoutePage loadingLabel="Loading source evidence…">
              <DataReadiness />
            </RoutePage>
          }
        />
        <Route
          path="/methodology"
          element={
            <RoutePage loadingLabel="Loading methodology…">
              <Methodology />
            </RoutePage>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
