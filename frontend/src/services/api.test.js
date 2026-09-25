import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { api, getBackendHealth, getMethodology, simulateScenario } from "./api.js";

const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });

test("missing build-time API URL uses same-origin GET and POST endpoints", async () => {
  const requests = [];
  const original = api.defaults.adapter;
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return response(config, { status: "ok", data_status: {} });
  };
  try {
    assert.equal((await getBackendHealth()).status, "ok");
    await getMethodology();
    await simulateScenario({ grid_id: "test-cell" });
    assert.ok(requests.every((request) => !request.baseURL));
    assert.deepEqual(requests.map((request) => request.url), ["/api/health", "/api/methodology", "/api/simulate"]);
    assert.equal(requests[2].method, "post");
    assert.equal(JSON.parse(requests[2].data).grid_id, "test-cell");
  } finally { api.defaults.adapter = original; }
});

test("an HTML SPA fallback cannot masquerade as a healthy API", async () => {
  const original = api.defaults.adapter;
  api.defaults.adapter = async (config) => response(config, "<!doctype html><html></html>");
  try { await assert.rejects(getBackendHealth(), /non-JSON/); }
  finally { api.defaults.adapter = original; }
});

test("the production API proxy precedes the frontend deep-link fallback", () => {
  const { rewrites } = JSON.parse(readFileSync(new URL("../../vercel.json", import.meta.url), "utf8"));
  assert.equal(rewrites[0].source, "/api/:path*");
  assert.equal(rewrites[0].destination, "https://greenpulse-ai-v0gz.onrender.com/api/:path*");
  assert.equal(rewrites.at(-1).destination, "/index.html");
});
