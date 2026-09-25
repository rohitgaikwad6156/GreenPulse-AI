export function researchWorkflow(status) {
  const grid = status?.real_ml_grid_available;
  const model = status?.trained_model_available;
  const stages = [
    { title: "1. Inspect surface heat", to: "/heat-map", present: grid && model,
      detail: "Inspect the Pune / PCMC 30 m analysis grid and select a cell.",
      missing: "Requires verified ward boundaries, the satellite ML grid and a matching trained model." },
    { title: "2. Explain the prediction", to: "/root-cause", present: grid && model,
      detail: "Use TreeSHAP to inspect warming and cooling contributions in °C.",
      missing: "Requires the real grid and trained XGBoost model; contributions are not causal effects." },
    { title: "3. Compare interventions", to: "/scenario-simulator", present: grid && model,
      detail: "Compare tree canopy and cool roofs with model uncertainty and space constraints.",
      missing: "Requires the grid, model, spatial validation error and intervention assumptions." },
    { title: "4. Optimize the budget", to: "/climate-action-optimizer", present: status?.optimizer_location_available,
      detail: "Allocate integer intervention blocks within capital, maintenance and land limits.",
      missing: "Requires a location with verified capacity, costs and model-supported benefits." },
    { title: "5. Validate outcomes", to: "/validation", present: status?.real_validation_dataset_available,
      detail: "Compare treated and control observations using Difference-in-Differences.",
      missing: "Requires genuine comparable pre/post observations and control-site evidence." },
  ];
  return stages.map(({ present, ...stage }) => ({ ...stage,
    // Presence is not a claim of validation; the destination performs full checks.
    state: !status ? "Not checked" : present ? "Inputs present" : "Inputs needed",
  }));
}
