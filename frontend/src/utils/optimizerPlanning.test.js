import assert from "node:assert/strict";
import test from "node:test";
import { buildOptimizerPayload } from "./optimizerPlanning.js";

const location = { location_id: "ARTIFICIAL-AREA", planning_available: true };
const weights = { cooling: 1, green_cover: 0.5, co_benefit: 0.2 };

test("builds a request only from a loaded evidence-complete location", () => {
  const payload = buildOptimizerPayload({
    locationId: location.location_id, budget: "250", maintenance: "15",
    weights, loadedLocations: [location],
  });
  assert.deepEqual(payload, {
    location_id: "ARTIFICIAL-AREA", budget_inr: 250,
    maintenance_cap_inr_per_year: 15, priority_weights: weights,
  });
  assert.equal("available_ground_m2" in payload, false);
  assert.equal("available_roof_m2" in payload, false);
});

test("rejects free-text, unavailable locations, and invalid financial inputs", () => {
  assert.throws(() => buildOptimizerPayload({
    locationId: "UNVERIFIED", budget: 1, maintenance: 1, weights,
    loadedLocations: [location],
  }), /evidence-complete/);
  assert.throws(() => buildOptimizerPayload({
    locationId: location.location_id, budget: -1, maintenance: 1, weights,
    loadedLocations: [location],
  }), /Capital budget/);
});
