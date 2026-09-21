import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL?.trim();

export const api = axios.create({
  baseURL: baseURL || undefined,
  timeout: 8000,
  headers: { Accept: "application/json" },
});

export async function getBackendHealth(signal) {
  if (!baseURL) {
    throw new Error("VITE_API_BASE_URL is not configured.");
  }

  const response = await api.get("/api/health", { signal });
  return response.data;
}

export async function getTreeCanopyConfig(signal) {
  if (!baseURL) throw new Error("VITE_API_BASE_URL is not configured.");
  const response = await api.get("/api/simulation/tree-canopy/config", { signal });
  return response.data;
}

export async function getCoolRoofConfig(signal) {
  if (!baseURL) throw new Error("VITE_API_BASE_URL is not configured.");
  const response = await api.get("/api/simulation/cool-roof/config", { signal });
  return response.data;
}

function requireApiBaseUrl() {
  if (!baseURL) throw new Error("VITE_API_BASE_URL is not configured.");
}

export async function getMapWards(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/map/wards", { signal });
  return response.data;
}

export async function getWardHeat(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/map/heat/wards", { signal });
  return response.data;
}

export async function getVisibleCellHeat(bounds, signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/map/heat/cells", { params: bounds, signal, timeout: 30000 });
  return response.data;
}

export async function getMapCellDetail(gridId, signal) {
  requireApiBaseUrl();
  const response = await api.get(`/api/map/cell/${encodeURIComponent(gridId)}`, { signal, timeout: 30000 });
  return response.data;
}

export async function getMapWardDetail(wardId, signal) {
  requireApiBaseUrl();
  const response = await api.get(`/api/map/ward/${encodeURIComponent(wardId)}`, { signal, timeout: 30000 });
  return response.data;
}

export async function explainGridCell(gridId, signal) {
  requireApiBaseUrl();
  const response = await api.post("/api/explain", { grid_id: gridId, sample_size: 2000 },
    { signal, timeout: 120000 });
  return response.data;
}

export async function simulateScenario(payload, signal) {
  requireApiBaseUrl();
  const response = await api.post("/api/simulate", payload, { signal, timeout: 30000 });
  return response.data;
}

export async function getOptimizerConfig(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/optimizer/config", { signal });
  return response.data;
}

export async function getOptimizerLocations(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/optimizer/locations", { signal });
  return response.data;
}

export async function optimizePortfolio(payload, signal) {
  requireApiBaseUrl();
  const response = await api.post("/api/optimize", payload, { signal, timeout: 30000 });
  return response.data;
}

export async function getValidationDemo(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/validation/demo", { signal });
  return response.data;
}

export async function getValidationDatasets(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/validation/datasets", { signal });
  return response.data;
}

export async function analyzeValidationDataset(datasetId, signal) {
  requireApiBaseUrl();
  const response = await api.post(`/api/validation/analyze/${encodeURIComponent(datasetId)}`, {},
    { signal, timeout: 120000 });
  return response.data;
}

export async function calculateValidation(payload, signal) {
  requireApiBaseUrl();
  const response = await api.post("/api/validation/did", payload, { signal, timeout: 30000 });
  return response.data;
}

export async function getMethodology(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/methodology", { signal });
  return response.data;
}

export async function getResearchStatus(signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/research/status", { signal });
  return response.data;
}

export async function getNearbySensorContext(params, signal) {
  requireApiBaseUrl();
  const response = await api.get("/api/research/sensors/nearby", { params, signal });
  return response.data;
}
