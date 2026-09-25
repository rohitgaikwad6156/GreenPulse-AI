import axios from "axios";

const baseURL = import.meta.env?.VITE_API_BASE_URL?.trim();

export const api = axios.create({
  baseURL: baseURL || undefined,
  timeout: 65000,
  headers: { Accept: "application/json" },
});

// A missing override intentionally uses /api on the current origin. Vite and
// Vercel forward that path to FastAPI. Reject an SPA fallback or proxy HTML.
api.interceptors.response.use((response) => {
  if (typeof response.data !== "object" || response.data === null) {
    throw new Error("The API returned a non-JSON response. Check the /api proxy configuration.");
  }
  return response;
});

export async function getBackendHealth(signal) {
  const response = await api.get("/api/health", { signal });
  return response.data;
}

export async function getTreeCanopyConfig(signal) {
  const response = await api.get("/api/simulation/tree-canopy/config", { signal });
  return response.data;
}

export async function getCoolRoofConfig(signal) {
  const response = await api.get("/api/simulation/cool-roof/config", { signal });
  return response.data;
}

export async function getMapWards(signal) {
  const response = await api.get("/api/map/wards", { signal });
  return response.data;
}

export async function getWardHeat(signal) {
  const response = await api.get("/api/map/heat/wards", { signal });
  return response.data;
}

export async function getVisibleCellHeat(bounds, signal) {
  const response = await api.get("/api/map/heat/cells", { params: bounds, signal, timeout: 30000 });
  return response.data;
}

export async function getMapCellDetail(gridId, signal) {
  const response = await api.get(`/api/map/cell/${encodeURIComponent(gridId)}`, { signal, timeout: 30000 });
  return response.data;
}

export async function getMapWardDetail(wardId, signal) {
  const response = await api.get(`/api/map/ward/${encodeURIComponent(wardId)}`, { signal, timeout: 30000 });
  return response.data;
}

export async function explainGridCell(gridId, signal) {
  const response = await api.post("/api/explain", { grid_id: gridId, sample_size: 2000 },
    { signal, timeout: 120000 });
  return response.data;
}

export async function simulateScenario(payload, signal) {
  const response = await api.post("/api/simulate", payload, { signal, timeout: 30000 });
  return response.data;
}

export async function getOptimizerConfig(signal) {
  const response = await api.get("/api/optimizer/config", { signal });
  return response.data;
}

export async function getOptimizerLocations(signal) {
  const response = await api.get("/api/optimizer/locations", { signal });
  return response.data;
}

export async function optimizePortfolio(payload, signal) {
  const response = await api.post("/api/optimize", payload, { signal, timeout: 30000 });
  return response.data;
}

export async function getValidationDemo(signal) {
  const response = await api.get("/api/validation/demo", { signal });
  return response.data;
}

export async function getValidationDatasets(signal) {
  const response = await api.get("/api/validation/datasets", { signal });
  return response.data;
}

export async function analyzeValidationDataset(datasetId, signal) {
  const response = await api.post(`/api/validation/analyze/${encodeURIComponent(datasetId)}`, {},
    { signal, timeout: 120000 });
  return response.data;
}

export async function calculateValidation(payload, signal) {
  const response = await api.post("/api/validation/did", payload, { signal, timeout: 30000 });
  return response.data;
}

export async function getMethodology(signal) {
  const response = await api.get("/api/methodology", { signal });
  return response.data;
}

export async function getResearchStatus(signal) {
  const response = await api.get("/api/research/status", { signal });
  return response.data;
}

export async function getNearbySensorContext(params, signal) {
  const response = await api.get("/api/research/sensors/nearby", { params, signal });
  return response.data;
}
