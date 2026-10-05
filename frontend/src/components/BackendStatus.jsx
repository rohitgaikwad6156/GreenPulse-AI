import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { getBackendHealth } from "../services/api.js";

const initialState = {
  kind: "loading",
  label: "Checking...",
  detail: "Connecting to the research service. Startup may take about a minute.",
};

export default function BackendStatus() {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    const controller = new AbortController();

    getBackendHealth(controller.signal)
      .then((result) => {
        if (result?.status !== "ok") {
          throw new Error("The backend returned an unexpected health response.");
        }
        if (controller.signal.aborted) return;
        setState({
          kind: "healthy",
          label: "Connected",
          detail: "Research service is responding",
        });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setState({
          kind: "error",
          label: "Connection Error",
          detail: error.response
            ? `Backend returned HTTP ${error.response.status}`
            : "Cannot reach the research service. Use Refresh status to retry; it may still be starting.",
        });
      });

    return () => controller.abort();
  }, []);

  const valueColor =
    state.kind === "healthy" ? "text-[#2f8050]" : state.kind === "error" ? "text-[#b05749]" : "text-[#80652f]";
  return (
    <section className="readiness-item">
      <h3 className="flex items-center gap-2">
        <Activity size={15} aria-hidden="true" /> Service connection
      </h3>
      <p className={`readiness-value ${valueColor}`} role="status" aria-live="polite">
        {state.label}
      </p>
      <p className="readiness-detail">{state.detail}</p>
    </section>
  );
}
