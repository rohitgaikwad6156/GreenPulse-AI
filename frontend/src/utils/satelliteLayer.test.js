import assert from "node:assert/strict";
import test from "node:test";
import { SATELLITE_LST, validSatelliteDate, satelliteTileStatus } from "./satelliteLayer.js";

test("historical study date is valid and impossible/future dates never request imagery", () => {
  assert.equal(validSatelliteDate(SATELLITE_LST.defaultDate, "2026-09-26"), true);
  for (const date of ["", "2025-02-30", "2025-5-10", "1999-01-01", "2027-01-01"]) {
    assert.equal(validSatelliteDate(date, "2026-09-26"), false, date);
  }
  assert.equal(validSatelliteDate("2024-02-29", "2026-09-26"), true);
});

test("partial or total tile failures remain visible instead of claiming complete coverage", () => {
  assert.equal(satelliteTileStatus(4, 1).status, "error");
  assert.match(satelliteTileStatus(0, 3).message, /could not load/);
  assert.match(satelliteTileStatus(4, 0).message, /Transparent areas/);
  assert.equal(satelliteTileStatus(4, 0).status, "ready");
});
