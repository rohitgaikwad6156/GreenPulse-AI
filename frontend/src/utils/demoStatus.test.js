import test from "node:test";
import assert from "node:assert/strict";
import { demoStatusPresentation } from "./demoStatus.js";
const ids = ["landsat_lst_scenes", "esa_worldcover", "osm_roads", "sentinel2_l2a_scenes", "municipal_boundary"];
function fixture(count = 3, ready = false) {
  const required_sources = ids.map((id, i) => ({ id, name: id, ready: i < count }));
  return {
    production_data: count === 5 ? "source_ready" : "blocked",
    first_heat_map: {
      ready: count === 5,
      required_sources_ready: count,
      required_sources_total: 5,
      blocker_count: 5 - count,
    },
    required_sources,
    blockers: required_sources.filter((s) => !s.ready),
    sources: ids.map((id) => ({ id })),
    source_status: Object.fromEntries(ids.map((id, i) => [id, i < count ? "verified" : "pending"])),
    artifacts: {
      real_ml_grid: ready ? "ready" : "blocked",
      trained_xgboost_model: ready ? "ready" : "blocked",
      planning_evidence: "pending",
      field_validation: "pending",
    },
  };
}
test("current gate counts and waiting artifacts come from canonical evidence", () => {
  const view = demoStatusPresentation({ data: fixture() });
  assert.deepEqual(view.sourceGate, { ready: false, count: 3, total: 5 });
  assert.equal(view.modelReady, false);
  assert.equal(view.waitingEvidence.length, 6);
});
test("source completion does not promote model artifacts", () => {
  const view = demoStatusPresentation({ data: fixture(5) });
  assert.equal(view.sourceGate.ready, true);
  assert.equal(view.modelReady, false);
  assert.equal(view.waitingEvidence.length, 4);
});
test("accepted model keeps planning and field evidence separate", () => {
  const view = demoStatusPresentation({ data: fixture(5, true) });
  assert.equal(view.modelReady, true);
  assert.deepEqual(
    view.waitingEvidence.map((s) => s.id),
    ["planning_evidence", "field_validation"],
  );
  assert.ok(!view.availableEvidence.some((s) => s.id === "shap"));
});
test("malformed or failed requests show no assumed blockers; static capabilities remain", () => {
  for (const input of [{ data: {} }, { error: true, data: fixture() }, {}]) {
    const view = demoStatusPresentation(input);
    assert.equal(view.state, "unknown");
    assert.equal(view.sourceGate, null);
    assert.deepEqual(view.waitingEvidence, []);
    assert.ok(view.capabilities.length);
  }
  const data = fixture();
  data.artifacts.planning_evidence = "maybe";
  assert.equal(demoStatusPresentation({ data }).state, "unknown");
  assert.equal(demoStatusPresentation({ loading: true }).state, "loading");
});
test("supporting WorldPop and ward sources do not change first-source denominator", () => {
  const data = fixture();
  data.sources.push({ id: "worldpop" }, { id: "ward_boundaries" });
  data.source_status.worldpop = "verified";
  data.source_status.ward_boundaries = "verified";
  assert.equal(demoStatusPresentation({ data }).sourceGate.total, 5);
});
