import assert from "node:assert/strict";
import test from "node:test";
import { researchWorkflow } from "./researchWorkflow.js";

test("a connection failure does not claim inputs are missing", () => {
  assert.ok(researchWorkflow(null).every((stage) => stage.state === "Not checked"));
});
test("an empty catalog is not a usable optimizer location", () => {
  const stages = researchWorkflow({ intervention_catalog_available: true, optimizer_location_available: false });
  assert.equal(stages[3].state, "Inputs needed");
});
test("map, SHAP and scenarios require both grid and model", () => {
  for (const status of [{ real_ml_grid_available: true }, { trained_model_available: true }]) {
    assert.ok(researchWorkflow(status).slice(0, 3).every((stage) => stage.state === "Inputs needed"));
  }
  assert.ok(researchWorkflow({ real_ml_grid_available: true, trained_model_available: true })
    .slice(0, 3).every((stage) => stage.state === "Inputs present"));
});
test("field evidence is independent of model availability", () => {
  const stages = researchWorkflow({ real_ml_grid_available: true, trained_model_available: true });
  assert.equal(stages[4].state, "Inputs needed");
});
