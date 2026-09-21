export function calibrationEvidenceMessage(report) {
  if (!report?.report_schema_version) return null;
  if (report.validation_status !== "READY_FOR_HUMAN_REVIEW" || !report.calibration_proposal) {
    return "No parameter update proposed because evidence or diagnostics are blocked.";
  }
  return "PROPOSED, NOT ADOPTED — explicit human approval is required.";
}
