import test from "node:test";
import assert from "node:assert/strict";
import { isChunkLoadError } from "./routeError.js";

test("recognizes browser and bundler lazy-chunk failures", () => {
  assert.equal(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: /assets/HeatMap.js")), true);
  assert.equal(isChunkLoadError(new Error("Importing a module script failed.")), true);
  assert.equal(isChunkLoadError(new Error("Loading chunk 42 failed.")), true);
  assert.equal(isChunkLoadError(Object.assign(new Error("chunk unavailable"), { name: "ChunkLoadError" })), true);
});

test("ordinary render and API errors use a local route retry", () => {
  assert.equal(isChunkLoadError(new Error("Cannot read properties of undefined")), false);
  assert.equal(isChunkLoadError(new Error("Request failed with status code 503")), false);
  assert.equal(isChunkLoadError(null), false);
});
