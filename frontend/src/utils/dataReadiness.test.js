import test from "node:test";
import assert from "node:assert/strict";
import { sourcePresentation, readinessPresentation } from "./dataReadiness.js";
for (const status of ["verified", "pending", "staged"]) {
  test(`${status} source and next action presentation`, () => {
    const result = sourcePresentation({
      status,
      next_action: "Obtain official evidence",
    });
    assert.equal(result.label.toLowerCase(), status);
    assert.equal(result.next_action, "Obtain official evidence");
  });
}
test("blocker count comes from response", () => {
  const result = readinessPresentation({
    data: {
      sources: [],
      summary: {},
      first_heat_map_ready: false,
      required_sources_ready: 0,
      required_sources_total: 2,
      required_sources: [{}, {}],
      first_heat_map_blockers: [{}, {}],
      later_stage_dependencies: [],
    },
  });
  assert.equal(result.blockerLabel, "2 blockers remaining");
});
test("loading state is explicit", () =>
  assert.equal(readinessPresentation({ loading: true }).state, "loading"));
test("backend error and malformed payload never imply readiness", () => {
  assert.equal(readinessPresentation({ error: true }).state, "error");
  assert.equal(readinessPresentation({ data: {} }).state, "error");
  assert.equal(sourcePresentation({ status: "unknown" }).label, "Blocked");
});
