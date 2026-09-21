const LIMIT = 1_000_000_000_000;

function numeric(value, label) {
  if (value === "" || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > LIMIT) {
    throw new Error(`${label} must be between 0 and 1,000,000,000,000.`);
  }
  return Number(value);
}

export function buildOptimizerPayload({ locationId, budget, maintenance, weights, loadedLocations }) {
  const location = loadedLocations?.find((item) => item.location_id === locationId);
  if (!location || !location.planning_available) {
    throw new Error("Select an evidence-complete ward or planning area.");
  }
  if (!weights || weights.cooling + weights.green_cover + weights.co_benefit <= 0) {
    throw new Error("At least one policy priority must be above zero.");
  }
  return {
    location_id: location.location_id,
    budget_inr: numeric(budget, "Capital budget (INR)"),
    maintenance_cap_inr_per_year: numeric(maintenance, "Annual maintenance limit (INR)"),
    priority_weights: { ...weights },
  };
}
