import assert from "node:assert/strict";
import test from "node:test";
import { sensorStatusMessage } from "./researchStatus.js";

for (const status of ["missing", "sparse", "stale", "temporally_mismatched"]) {
  test(`renders an explicit ${status} sensor state`, () => {
    assert.notEqual(sensorStatusMessage(status), "Sensor evidence status is unavailable.");
  });
}
