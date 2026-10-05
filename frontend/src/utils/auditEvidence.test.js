import test from "node:test";
import assert from "node:assert/strict";
import {
  auditPresentation,
  formatCelsius,
  auditDetailsLabel,
  AUDIT_DISCLAIMER,
  AUDIT_PRESERVATION,
} from "./auditEvidence.js";
for (const status of ["pass", "pending", "review"]) {
  test(`audit ${status} badge and backend evidence`, () => {
    const view = auditPresentation({
      status,
      summary: ["2/3 fixture scenes"],
      audit_result: "FAIL",
    });
    assert.equal(view.display_status, status.toUpperCase());
    assert.deepEqual(view.summary, ["2/3 fixture scenes"]);
  });
}
test("disclosure labels support expansion and collapse", () => {
  assert.equal(auditDetailsLabel(false), "View details");
  assert.equal(auditDetailsLabel(true), "Hide details");
});
test("bulk and extreme values format without clipping or replacing", () => {
  assert.equal(formatCelsius(95.1234), "95.12 °C");
  assert.equal(formatCelsius(-5.129), "-5.13 °C");
  assert.equal(formatCelsius(null), "Unavailable");
  assert.equal(formatCelsius(Infinity), "Unavailable");
});
test("scientific disclaimer and unchanged QA remain explicit", () => {
  assert.match(AUDIT_DISCLAIMER, /not Pune\/PMC\/PCMC temperature results/);
  assert.match(
    AUDIT_PRESERVATION,
    /did not change production QA rules or alter source pixels/,
  );
});
test("missing or unknown audit never implies a pass", () => {
  for (const value of [undefined, {}, { status: "invented", summary: [] }]) {
    assert.equal(auditPresentation(value).status, "unavailable");
  }
});
