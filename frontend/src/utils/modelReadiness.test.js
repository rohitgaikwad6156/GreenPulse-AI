import assert from "node:assert/strict";
import test from "node:test";
import { modelReadinessPresentation } from "./modelReadiness.js";

const ids = ["landsat_lst_scenes", "esa_worldcover", "osm_roads",
  "sentinel2_l2a_scenes", "municipal_boundary"];

function fixture(readyCount = 3, grid = "blocked", model = "blocked") {
  const required_sources = ids.map((id, index) => ({
    id, name: id, ready: index < readyCount,
    reason: index < readyCount ? null : "Source verification is pending.",
  }));
  return {
    production_data: readyCount === ids.length ? "source_ready" : "blocked",
    first_heat_map: { ready: readyCount === ids.length,
      required_sources_ready: readyCount, required_sources_total: ids.length,
      blocker_count: ids.length - readyCount },
    required_sources,
    blockers: required_sources.filter((source) => !source.ready)
      .map(({ id, name }) => ({ id, name, reason: "Pending" })),
    sources: ids.map((id) => ({ id, next_action: `Prepare ${id}` })),
    source_status: Object.fromEntries([
      ...ids.map((id, index) => [id, index < readyCount ? "verified" : "pending"]),
      ["ward_boundaries", "pending"], ["worldpop", "verified"],
      ["pmc_outline", "pending"], ["pcmc_outline", "staged"],
    ]),
    artifacts: { real_ml_grid: grid, trained_xgboost_model: model },
  };
}

test("current-like evidence displays exactly the five backend requirements", () => {
  const view = modelReadinessPresentation({ data: fixture() });
  assert.equal(view.state, "WAITING_FOR_SOURCES");
  assert.deepEqual([view.readyCount, view.totalCount, view.blockerCount], [3, 5, 2]);
  assert.equal(view.required.filter((item) => item.ready).length, 3);
  assert.equal(view.waiting.length, 2);
  assert.equal(view.required.find((item) => item.id === "sentinel2_l2a_scenes").name, "Sentinel-2 L2A");
  assert.equal(view.required.find((item) => item.id === "municipal_boundary").name, "Combined PMC + PCMC boundary");
  assert.match(view.boundaryDetail, /PMC outline: pending.*PCMC outline: staged/);
  assert.equal(view.wardReportingReady, false);
  assert.ok(!view.required.some((item) => item.id === "worldpop" || item.id === "ward_boundaries"));
});

test("four of five and five of five update without changing UI membership", () => {
  const four = modelReadinessPresentation({ data: fixture(4) });
  assert.equal(four.state, "WAITING_FOR_SOURCES");
  assert.equal(four.blockerCount, 1);
  const five = modelReadinessPresentation({ data: fixture(5) });
  assert.equal(five.state, "WAITING_FOR_BUILD");
  assert.equal(five.blockerCount, 0);
  assert.match(five.message, /processing, model training and spatial validation/);
});

test("grid readiness cannot promote a blocked model; both accepted artifacts enable model view", () => {
  assert.equal(modelReadinessPresentation({ data: fixture(5, "ready", "blocked") }).state,
    "WAITING_FOR_BUILD");
  const ready = fixture(5, "ready", "ready");
  assert.equal(modelReadinessPresentation({ data: ready }).state, "READY");
  ready.source_status.ward_boundaries = "pending";
  assert.equal(modelReadinessPresentation({ data: ready }).wardReportingReady, false);
});

test("malformed and disconnected readiness are unknown, without presumed blockers", () => {
  assert.equal(modelReadinessPresentation({ loading: true }).state, "LOADING");
  const network = modelReadinessPresentation({ error: true });
  assert.equal(network.state, "UNKNOWN");
  assert.equal(network.reason, "network");
  assert.match(network.message, /retry/i);
  assert.equal(modelReadinessPresentation({ data: {} }).state, "UNKNOWN");
  const malformed = fixture();
  malformed.first_heat_map.required_sources_ready = 4;
  assert.equal(modelReadinessPresentation({ data: malformed }).state, "UNKNOWN");
  const badArtifact = fixture();
  badArtifact.artifacts.trained_xgboost_model = "ready-ish";
  assert.equal(modelReadinessPresentation({ data: badArtifact }).state, "UNKNOWN");
});
