import { useMemo, useRef } from "react";
import { WMSTileLayer } from "react-leaflet";
import { SATELLITE_LST, satelliteTileStatus } from "../utils/satelliteLayer.js";

// The parent keys this component by date/retry so old tile events cannot update
// the current layer. This is published imagery, never input to the ML pipeline.
export default function SatelliteHeatLayer({ date, opacity, onStatus }) {
  const counts = useRef({ loaded: 0, failed: 0 });
  const events = useMemo(() => ({
    loading: () => {
      counts.current = { loaded: 0, failed: 0 };
      onStatus({ status: "loading", message: "Loading NASA satellite imagery…" });
    },
    tileload: () => { counts.current.loaded += 1; },
    tileerror: () => { counts.current.failed += 1; },
    load: () => onStatus(satelliteTileStatus(counts.current.loaded, counts.current.failed)),
  }), [onStatus]);
  return <WMSTileLayer url={SATELLITE_LST.serviceUrl} layers={SATELLITE_LST.layer}
    format="image/png" transparent version="1.1.1" time={date}
    opacity={opacity} maxNativeZoom={9} maxZoom={19} eventHandlers={events}
    attribution='Surface temperature: <a href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs">NASA GIBS / Terra MODIS</a>' />;
}
