export const AUDIT_DISCLAIMER = "These are full-scene diagnostics, not Pune/PMC/PCMC temperature results.";
export const AUDIT_PRESERVATION = "The extreme audit did not change production QA rules or alter source pixels.";
const labels = {
  pass: "PASS",
  pending: "PENDING",
  review: "REVIEW",
  unavailable: "UNAVAILABLE",
};
export function auditPresentation(audit) {
  if (!audit || !Object.hasOwn(labels, audit.status) || !Array.isArray(audit.summary)) {
    return {
      status: "unavailable",
      display_status: labels.unavailable,
      summary: [],
      interpretation: "Evidence unavailable.",
    };
  }
  return { ...audit, display_status: labels[audit.status] };
}
export function formatCelsius(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)} °C` : "Unavailable";
}
export function auditDetailsLabel(open) {
  return open ? "Hide details" : "View details";
}
