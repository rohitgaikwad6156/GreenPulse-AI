export const SATELLITE_LST = Object.freeze({
  serviceUrl: "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
  layer: "MODIS_Terra_Land_Surface_Temp_Day",
  legendUrl: "https://gibs.earthdata.nasa.gov/legends/MODIS_Land_Surface_Temp_H.png",
  metadataUrl: "https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/MODIS_Terra_Land_Surface_Temp_Day.json",
  defaultDate: "2025-05-10",
  firstDate: "2000-02-24",
});

export function validSatelliteDate(value, today = new Date().toISOString().slice(0, 10)) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
    && value >= SATELLITE_LST.firstDate && value <= today;
}

export function satelliteTileStatus(loaded, failed) {
  if (failed) return { status: "error", message: loaded
    ? "Some NASA tiles could not load. Refresh to retry the missing tiles."
    : "NASA imagery could not load. Check your connection and refresh to retry." };
  return { status: "ready", message: "NASA tiles loaded. Transparent areas can be clouds, missing swaths or no retrieval; they are not cool areas." };
}
