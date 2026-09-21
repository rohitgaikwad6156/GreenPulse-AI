import assert from "node:assert/strict";
import test from "node:test";
import { calibrationEvidenceMessage } from "./validationEvidence.js";

test("blocked evidence never appears adoptable", () => {
  assert.match(calibrationEvidenceMessage({
    report_schema_version: "1.0", validation_status: "BLOCKED", calibration_proposal: null,
  }), /blocked/);
});

test("review-ready proposals still require explicit human approval", () => {
  assert.match(calibrationEvidenceMessage({
    report_schema_version: "1.0", validation_status: "READY_FOR_HUMAN_REVIEW",
    calibration_proposal: { status: "PROPOSED_NOT_ADOPTED" },
  }), /NOT ADOPTED.*human approval/);
});
