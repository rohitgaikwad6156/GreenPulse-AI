import assert from "node:assert/strict";
import test from "node:test";
import { artifactLabel, sourceGateMessage, validOverviewReadiness } from "./overviewReadiness.js";

const blocked = {
  production_data: "blocked",
  blockers: [{ id: "a" }, { id: "b" }],
  first_heat_map: { ready: false, required_sources_ready: 3, required_sources_total: 5, blocker_count: 2 },
  artifacts: {
    real_ml_grid: "blocked",
    trained_xgboost_model: "blocked",
    planning_evidence: "pending",
    field_validation: "pending",
  },
};

test("canonical readiness reports dynamic source counts separately from artifacts", () => {
  assert.ok(validOverviewReadiness(blocked));
  assert.match(sourceGateMessage(blocked), /3\/5.*2 blockers/);
  assert.equal(artifactLabel(blocked.artifacts.real_ml_grid), "Inputs needed");
  assert.equal(artifactLabel(blocked.artifacts.trained_xgboost_model), "Inputs needed");
  assert.equal(artifactLabel("staged"), "Evidence staged");
  const one = {
    ...blocked,
    blockers: [{}],
    first_heat_map: { ...blocked.first_heat_map, required_sources_ready: 4, blocker_count: 1 },
  };
  assert.ok(validOverviewReadiness(one));
  assert.match(sourceGateMessage(one), /1 blocker remaining/);
});

test("loading, connection failure and malformed payload cannot claim readiness", () => {
  assert.equal(sourceGateMessage(null), "Source readiness could not be checked.");
  assert.equal(validOverviewReadiness(null), false);
  assert.equal(validOverviewReadiness({ ...blocked, blockers: [] }), false);
  assert.equal(
    validOverviewReadiness({ ...blocked, artifacts: { ...blocked.artifacts, trained_xgboost_model: "ready-ish" } }),
    false,
  );
  assert.equal(validOverviewReadiness({ ...blocked, production_data: "source_ready" }), false);
});
