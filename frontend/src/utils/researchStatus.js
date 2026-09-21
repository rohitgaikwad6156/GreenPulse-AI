export const sensorStatusCopy = {
  missing: "No verified point observations are available.",
  sparse: "Verified observations exist, but station coverage is below the declared context threshold.",
  stale: "The latest verified observation exceeds the dataset freshness threshold.",
  temporally_mismatched: "Verified observations do not overlap the current peak-summer LST scope.",
  available: "Verified point observations are available as local context only.",
};

export function sensorStatusMessage(status) {
  return sensorStatusCopy[status] || "Sensor evidence status is unavailable.";
}
