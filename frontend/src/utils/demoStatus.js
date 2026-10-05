import { modelReadinessPresentation } from "./modelReadiness.js";

export const capabilities = [
  [
    "Interactive NASA MODIS view",
    "Historical daytime LST at approximately 1 km source resolution. Availability depends on the external imagery service.",
  ],
  [
    "Processing and model software",
    "Source validation, satellite processing, 30 m grid assembly, spatial CV, baselines, XGBoost and TreeSHAP workflows are implemented.",
  ],
  [
    "Evidence-gated scenarios and optimizer",
    "The APIs and UI withhold production outputs when required evidence is missing. Follow-up DiD requires genuine treated/control observations.",
  ],
  [
    "Provenance and reproducibility",
    "Source audits, Data and Model Cards, and future build records for Git, dependencies, source/data/model checksums and parameters.",
  ],
];

export function demoStatusPresentation(input = {}) {
  const model = modelReadinessPresentation(input);
  const unknown = model.state === "UNKNOWN" || model.state === "LOADING";
  const statuses = input.data?.artifacts;
  const valid = ["ready", "pending", "blocked", "staged"];
  if (unknown || !valid.includes(statuses?.planning_evidence) || !valid.includes(statuses?.field_validation)) {
    return {
      state: model.state === "LOADING" ? "loading" : "unknown",
      capabilities,
      artifacts: [],
      availableEvidence: [],
      waitingEvidence: [],
      sourceGate: null,
    };
  }
  const artifacts = [
    ["real_ml_grid", "Real 30 m ML grid"],
    ["trained_xgboost_model", "XGBoost model and spatial-CV metrics"],
    ["planning_evidence", "Location-specific planning evidence"],
    ["field_validation", "Field observations"],
  ].map(([id, name]) => ({ id, name, ready: statuses[id] === "ready" }));
  const evidence = [...model.required, ...artifacts];
  return {
    state: "checked",
    capabilities,
    artifacts,
    sourceGate: { ready: input.data.first_heat_map.ready, count: model.readyCount, total: model.totalCount },
    modelReady: model.state === "READY",
    boundaryDetail: model.boundaryDetail,
    availableEvidence: evidence.filter((item) => item.ready),
    waitingEvidence: evidence.filter((item) => !item.ready),
    message: model.message,
  };
}
