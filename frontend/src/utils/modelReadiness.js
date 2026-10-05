const LABELS = {
  landsat_lst_scenes: "Landsat 8/9",
  sentinel2_l2a_scenes: "Sentinel-2 L2A",
  esa_worldcover: "ESA WorldCover",
  osm_roads: "OSM roads",
  municipal_boundary: "Combined PMC + PCMC boundary",
};

const ARTIFACT_STATUSES = new Set(["ready", "blocked", "pending", "staged"]);
const SOURCE_STATUSES = new Set(["verified", "blocked", "pending", "staged"]);

export function friendlyRequiredSource(source, records = [], status = null) {
  const record = records.find((item) => item.id === source.id);
  return {
    id: source.id,
    name: LABELS[source.id] || source.name,
    ready: source.ready,
    status: source.ready ? "Ready" : status === "pending" ? "Pending"
      : status === "staged" ? "Staged" : "Needs review",
    reason: source.reason || "Source evidence is unavailable.",
    nextAction: typeof record?.next_action === "string" ? record.next_action : null,
  };
}

function validReadiness(data) {
  const gate = data?.first_heat_map;
  const sources = data?.required_sources;
  const blockers = data?.blockers;
  const artifacts = data?.artifacts;
  if (!gate || !Array.isArray(sources) || !Array.isArray(blockers) ||
      !artifacts || typeof artifacts !== "object" ||
      !["blocked", "source_ready"].includes(data.production_data) ||
      typeof gate.ready !== "boolean" ||
      gate.ready !== (data.production_data === "source_ready") ||
      !Number.isInteger(gate.required_sources_ready) ||
      !Number.isInteger(gate.required_sources_total) ||
      gate.required_sources_total <= 0 ||
      gate.required_sources_ready < 0 ||
      gate.required_sources_ready > gate.required_sources_total ||
      gate.required_sources_total !== sources.length ||
      gate.blocker_count !== gate.required_sources_total - gate.required_sources_ready ||
      gate.blocker_count !== blockers.length ||
      gate.ready !== (gate.blocker_count === 0) ||
      !ARTIFACT_STATUSES.has(artifacts.real_ml_grid) ||
      !ARTIFACT_STATUSES.has(artifacts.trained_xgboost_model) ||
      !data.source_status || typeof data.source_status !== "object" ||
      !Array.isArray(data.sources) ||
      !data.sources.every((item) => item && typeof item.id === "string")) return false;
  const ids = new Set();
  for (const source of sources) {
    if (!source || typeof source.id !== "string" || !source.id ||
        typeof source.name !== "string" || typeof source.ready !== "boolean" ||
        ids.has(source.id) || !SOURCE_STATUSES.has(data.source_status[source.id]) ||
        !data.sources.some((item) => item.id === source.id)) return false;
    ids.add(source.id);
  }
  if (sources.filter((source) => source.ready).length !== gate.required_sources_ready ||
      blockers.some((blocker) => !blocker || !ids.has(blocker.id) ||
        sources.find((source) => source.id === blocker.id)?.ready) ||
      new Set(blockers.map((blocker) => blocker.id)).size !== blockers.length) return false;
  return true;
}

export function modelReadinessPresentation({ loading = false, error = false, data = null } = {}) {
  if (loading) return { state: "LOADING", message: "Checking research model readiness…" };
  if (error) return { state: "UNKNOWN", reason: "network",
    message: "Could not check research model readiness. Check the connection and retry." };
  if (!validReadiness(data)) return { state: "UNKNOWN", reason: "evidence",
    message: "Research model readiness is unknown. The evidence response is incomplete; retry status." };

  const required = data.required_sources.map((source) =>
    friendlyRequiredSource(source, data.sources, data.source_status[source.id]))
    .sort((left, right) => Number(right.ready) - Number(left.ready));
  const waiting = required.filter((source) => !source.ready);
  const grid = data.artifacts.real_ml_grid;
  const model = data.artifacts.trained_xgboost_model;
  const state = !data.first_heat_map.ready ? "WAITING_FOR_SOURCES"
    : grid === "ready" && model === "ready" ? "READY" : "WAITING_FOR_BUILD";
  const pmc = data.source_status.pmc_outline;
  const pcmc = data.source_status.pcmc_outline;
  const boundaryDetail = SOURCE_STATUSES.has(pmc) && SOURCE_STATUSES.has(pcmc)
    ? `PMC outline: ${pmc}. PCMC outline: ${pcmc}. The combined boundary needs its own verification.`
    : null;
  return {
    state,
    required,
    waiting,
    readyCount: data.first_heat_map.required_sources_ready,
    totalCount: data.first_heat_map.required_sources_total,
    blockerCount: data.first_heat_map.blocker_count,
    grid,
    model,
    boundaryDetail,
    wardReportingReady: data.source_status.ward_boundaries === "verified",
    message: state === "WAITING_FOR_SOURCES"
      ? "The 30 m research model needs all required source groups before the real grid can be processed and the XGBoost model trained."
      : state === "WAITING_FOR_BUILD"
        ? "All required sources are ready. The real processing, model training and spatial validation still need to be completed."
        : "The source gate and model metadata are ready. Model outputs still require the production API's full artifact checks.",
  };
}
