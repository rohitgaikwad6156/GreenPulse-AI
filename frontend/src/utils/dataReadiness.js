export const STATUS_LABELS = {
  verified: "Verified",
  staged: "Staged",
  pending: "Pending",
  blocked: "Blocked",
  optional: "Optional",
};
export function sourcePresentation(source) {
  const status = Object.hasOwn(STATUS_LABELS, source.status)
    ? source.status
    : "blocked";
  return {
    ...source,
    status,
    label: STATUS_LABELS[status],
    next_action:
      source.next_action || "Review the source evidence before proceeding.",
  };
}
export function readinessPresentation({ loading, error, data }) {
  if (loading)
    return { state: "loading", message: "Checking repository evidence…" };
  if (
    error ||
    !data ||
    typeof data.first_heat_map_ready !== "boolean" ||
    !Number.isInteger(data.required_sources_ready) ||
    !Number.isInteger(data.required_sources_total) ||
    data.required_sources_ready < 0 ||
    data.required_sources_ready > data.required_sources_total ||
    !data.summary ||
    !Array.isArray(data.sources) ||
    !data.sources.every(
      (source) =>
        source &&
        typeof source.name === "string" &&
        Array.isArray(source.evidence) &&
        Array.isArray(source.audits),
    ) ||
    !Array.isArray(data.required_sources) ||
    !Array.isArray(data.first_heat_map_blockers) ||
    !Array.isArray(data.later_stage_dependencies) ||
    data.required_sources_total !== data.required_sources.length ||
    data.required_sources_ready + data.first_heat_map_blockers.length !==
      data.required_sources_total
  )
    return {
      state: "error",
      message:
        "Data readiness is unavailable. The backend may be starting. Retry to check the source evidence.",
    };
  const count = data.first_heat_map_blockers.length;
  return {
    state: "ready",
    blockerLabel: `${count} ${count === 1 ? "blocker" : "blockers"} remaining`,
    sources: data.sources.map(sourcePresentation),
  };
}
