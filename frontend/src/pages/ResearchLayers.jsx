import { useEffect, useState } from "react";
import { AlertCircle, Database, LocateFixed, ShieldAlert, Thermometer } from "lucide-react";
import PageIntro from "../components/PageIntro.jsx";
import { getNearbySensorContext, getResearchStatus } from "../services/api.js";
import { sensorStatusMessage } from "../utils/researchStatus.js";

const statusStyle = (status) => status === "available"
  ? "border-[#cfe2d2] bg-[#f1f8f1] text-[#356445]"
  : "border-[#eadfca] bg-[#fcf8f0] text-[#856834]";

export default function ResearchLayers() {
  const [state, setState] = useState({ status: "loading", data: null, message: "" });
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [timestamp, setTimestamp] = useState("");
  const [nearby, setNearby] = useState(null);
  const [nearbyError, setNearbyError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getResearchStatus(controller.signal)
      .then((data) => setState({ status: "ready", data, message: "" }))
      .catch((error) => {
        if (error.name !== "CanceledError") setState({ status: "error", data: null, message: error.message || "Research evidence status could not be loaded." });
      });
    return () => controller.abort();
  }, []);

  async function findNearby(event) {
    event.preventDefault(); setNearby(null); setNearbyError("");
    if (![latitude, longitude].every((value) => value !== "" && Number.isFinite(Number(value))) || !timestamp) {
      setNearbyError("Enter latitude, longitude, and a timezone-aware observation timestamp."); return;
    }
    try {
      setNearby(await getNearbySensorContext({ latitude: Number(latitude), longitude: Number(longitude), timestamp_utc: timestamp }));
    } catch (error) {
      const detail = error.response?.data?.detail;
      setNearbyError(typeof detail === "string" ? detail : error.message || "Nearby point context could not be loaded.");
    }
  }

  return <>
    <PageIntro eyebrow="Optional research evidence" title="Sensors, exposure, and vulnerability"
      description="Inspect verified point observations and separate contextual layers without converting them into wall-to-wall LST or an unsupported risk score." />
    {state.status === "loading" && <section role="status" className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#617566]">Loading research evidence status…</section>}
    {state.status === "error" && <section role="alert" className="flex gap-3 rounded-2xl border border-[#eadfca] bg-[#fcf8f0] p-5 text-sm text-[#856834]"><AlertCircle size={18} aria-hidden="true" />{state.message}</section>}
    {state.data && <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-3">
        <section className={`rounded-2xl border p-5 ${statusStyle(state.data.sensors.status)}`}>
          <Thermometer size={21} aria-hidden="true" /><h2 className="mt-3 text-sm font-semibold">Point observations · {state.data.sensors.status.replaceAll("_", " ")}</h2>
          <p className="mt-2 text-xs leading-5">{sensorStatusMessage(state.data.sensors.status)}</p>
          <p className="mt-2 text-xs">{state.data.sensors.station_count} stations · {state.data.sensors.observation_count} observations</p>
          <p className="mt-2 text-xs font-medium">No citywide interpolation is performed.</p>
        </section>
        {state.data.context_layers.exposure_layers.map((layer) => <section key={layer.layer_id} className={`rounded-2xl border p-5 ${statusStyle(layer.status)}`}>
          <Database size={21} aria-hidden="true" /><h2 className="mt-3 text-sm font-semibold">Exposure · {layer.status}</h2><p className="mt-2 text-xs leading-5">{layer.blocker}</p><p className="mt-2 text-xs">{layer.interpretation}</p>
        </section>)}
        {state.data.context_layers.vulnerability_layers.map((layer) => <section key={layer.layer_id} className={`rounded-2xl border p-5 ${statusStyle(layer.status)}`}>
          <ShieldAlert size={21} aria-hidden="true" /><h2 className="mt-3 text-sm font-semibold">Vulnerability · {layer.status}</h2><p className="mt-2 text-xs leading-5">{layer.blocker}</p><p className="mt-2 text-xs">{layer.interpretation}</p>
        </section>)}
      </div>
      <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
        <h2 className="text-sm font-semibold text-[#294532]">Temporal scope</h2>
        <p className="mt-2 text-sm text-[#617566]">The LST MVP is explicitly limited to peak summer: {state.data.sensors.mvp_temporal_scope.start} through {state.data.sensors.mvp_temporal_scope.end}. Multi-season comparison is not implemented.</p>
        <p className="mt-2 text-xs text-[#718276]">Air temperature, humidity, and AQI are separate point measurements. Even a temporally matched station does not become a 30 m surface-temperature observation.</p>
      </section>
      <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
        <div className="flex items-center gap-2"><LocateFixed size={18} className="text-[#397a50]" aria-hidden="true" /><h2 className="text-sm font-semibold text-[#294532]">Optional point proximity</h2></div>
        <form onSubmit={findNearby} className="mt-4 grid gap-3 sm:grid-cols-4">
          <label className="text-xs text-[#526957]">Latitude<input type="number" step="any" min="-90" max="90" value={latitude} onChange={(event) => setLatitude(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-3 py-2 text-sm" /></label>
          <label className="text-xs text-[#526957]">Longitude<input type="number" step="any" min="-180" max="180" value={longitude} onChange={(event) => setLongitude(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-3 py-2 text-sm" /></label>
          <label className="text-xs text-[#526957]">Timestamp with timezone<input type="text" placeholder="2025-04-01T10:30:00+05:30" value={timestamp} onChange={(event) => setTimestamp(event.target.value)} className="mt-1.5 w-full rounded-lg border border-[#dce7dc] px-3 py-2 text-sm" /></label>
          <button className="self-end rounded-lg bg-[#397a50] px-4 py-2 text-sm font-semibold text-white">Find nearest point</button>
        </form>
        {nearbyError && <p role="alert" className="mt-3 text-xs text-[#a55345]">{nearbyError}</p>}
        {nearby && <div className={`mt-4 rounded-xl border p-4 text-xs leading-5 ${statusStyle(nearby.status === "matched" ? "available" : nearby.status)}`}>
          <p className="font-semibold">{nearby.status.replaceAll("_", " ")}</p><p>{nearby.interpretation}</p>
          {nearby.nearest && <p className="mt-1">Station {nearby.nearest.station_id}: {nearby.nearest.distance_m.toFixed(0)} m away; {nearby.nearest.temporal_difference_minutes.toFixed(1)} minutes from the requested time.</p>}
        </div>}
      </section>
      <section className="rounded-2xl border border-[#eadfca] bg-[#fcf8f0] p-5 text-xs leading-5 text-[#856834]">
        <h2 className="text-sm font-semibold">No composite climate-risk score</h2>
        <p className="mt-2">Heat Hazard Score remains a separate LST normalization. {state.data.context_layers.composite_risk_reason}</p>
      </section>
      <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 text-xs leading-5 text-[#617566]">
        <h2 className="text-sm font-semibold text-[#294532]">Future scope</h2>
        <ul className="mt-2 list-disc space-y-1 pl-4">{state.data.context_layers.future_scope.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>
    </div>}
  </>;
}
