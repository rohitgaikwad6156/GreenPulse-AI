export const STATUS_LABELS = {
  verified: "Verified",
  staged: "Staged",
  pending: "Pending",
  blocked: "Blocked",
  unknown: "Unknown",
  optional: "Optional",
};
export function sourcePresentation(source) {
  const status = Object.hasOwn(STATUS_LABELS, source.status) ? source.status : "blocked";
  return {
    ...source,
    status,
    label: STATUS_LABELS[status],
    next_action: source.next_action || "Review the source evidence before proceeding.",
  };
}
export function readinessPresentation({ loading, error, data }) {
  if (loading) return { state: "loading", message: "Checking repository evidence…" };
  if (
    error ||
    !data ||
    !data.first_heat_map ||
    !["source_ready", "blocked", "unknown"].includes(data.production_data) ||
    !data.artifacts ||
    typeof data.artifacts !== "object" ||
    Array.isArray(data.artifacts) ||
    !Array.isArray(data.blockers) ||
    !Array.isArray(data.evidence_warnings) ||
    typeof data.first_heat_map_ready !== "boolean" ||
    !Number.isInteger(data.required_sources_ready) ||
    !Number.isInteger(data.required_sources_total) ||
    data.required_sources_ready < 0 ||
    data.required_sources_ready > data.required_sources_total ||
    !data.summary ||
    !Array.isArray(data.sources) ||
    !data.sources.every(
      (source) =>
        source && typeof source.name === "string" && Array.isArray(source.evidence) && Array.isArray(source.audits),
    ) ||
    !Array.isArray(data.required_sources) ||
    !Array.isArray(data.first_heat_map_blockers) ||
    !Array.isArray(data.later_stage_dependencies) ||
    data.required_sources_total !== data.required_sources.length ||
    data.required_sources_ready + data.first_heat_map_blockers.length !== data.required_sources_total ||
    (data.production_data !== "unknown" &&
      (data.first_heat_map.ready !== data.first_heat_map_ready ||
        data.first_heat_map.required_sources_ready !== data.required_sources_ready ||
        data.first_heat_map.required_sources_total !== data.required_sources_total ||
        data.first_heat_map.blocker_count !== data.first_heat_map_blockers.length ||
        data.blockers.length !== data.first_heat_map_blockers.length ||
        data.production_data !== (data.first_heat_map_ready ? "source_ready" : "blocked"))) ||
    (data.production_data === "unknown" &&
      (data.first_heat_map.ready !== null ||
        data.first_heat_map.blocker_count !== null ||
        !data.evidence_warnings.length))
  )
    return {
      state: "error",
      message: "Data readiness is unavailable. The backend may be starting. Retry to check the source evidence.",
    };
  const count = data.first_heat_map.blocker_count;
  return {
    state: "ready",
    gateKnown: data.production_data !== "unknown",
    blockerLabel:
      count === null ? "Blocker count unavailable" : `${count} ${count === 1 ? "blocker" : "blockers"} remaining`,
    sources: data.sources.map(sourcePresentation),
  };
}
