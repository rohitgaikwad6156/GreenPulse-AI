const artifactStatuses = new Set(["ready", "blocked", "pending", "staged"]);

export function validOverviewReadiness(data) {
  const artifacts = data?.artifacts;
  const gate = data?.first_heat_map;
  return !!(
    artifacts && gate &&
    ["real_ml_grid", "trained_xgboost_model", "planning_evidence", "field_validation"]
      .every((key) => artifactStatuses.has(artifacts[key])) &&
    ["source_ready", "blocked", "unknown"].includes(data.production_data) &&
    Array.isArray(data.blockers) &&
    (data.production_data === "unknown"
      ? gate.ready === null && gate.blocker_count === null
      : gate.ready === (data.production_data === "source_ready") &&
        Number.isInteger(gate.required_sources_ready) &&
        Number.isInteger(gate.required_sources_total) &&
        gate.required_sources_ready >= 0 &&
        gate.required_sources_ready <= gate.required_sources_total &&
        gate.blocker_count === data.blockers.length &&
        gate.blocker_count === gate.required_sources_total - gate.required_sources_ready)
  );
}

export function artifactLabel(status) {
  return ({ ready: "Evidence present", staged: "Evidence staged",
    pending: "Awaiting evidence", blocked: "Inputs needed" })[status] || "Not checked";
}

export function sourceGateMessage(data) {
  if (!data) return "Source readiness could not be checked.";
  const gate = data.first_heat_map;
  if (data.production_data === "unknown") return "Source readiness is unknown. Review the evidence warnings.";
  if (gate.ready) return `${gate.required_sources_ready}/${gate.required_sources_total} required source groups ready. Production preflight is still required.`;
  const count = gate.blocker_count;
  return `${gate.required_sources_ready}/${gate.required_sources_total} required source groups ready · ${count} ${count === 1 ? "blocker" : "blockers"} remaining.`;
}
