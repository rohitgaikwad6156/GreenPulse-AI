import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { getBackendHealth } from "../services/api.js";

const initialState = {
  kind: "loading",
  label: "Checking...",
  detail: "Contacting the FastAPI backend",
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
        setState({
          kind: "healthy",
          label: "Healthy",
          detail: "FastAPI is responding",
        });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setState({
          kind: "error",
          label: "Connection Error",
          detail: error.response
            ? `Backend returned HTTP ${error.response.status}`
            : error.message === "VITE_API_BASE_URL is not configured."
              ? error.message
              : "Cannot reach FastAPI. Check that the backend is running.",
        });
      });

    return () => controller.abort();
  }, []);

  const valueColor =
    state.kind === "healthy"
      ? "text-[#2f8050]"
      : state.kind === "error"
        ? "text-[#b05749]"
        : "text-[#9b8354]";

  return (
    <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-[#6f8274]">API connection</p>
        <Activity size={17} className="text-[#6e9b79]" strokeWidth={1.8} aria-hidden="true" />
      </div>
      <p className={`mt-4 text-lg font-semibold leading-tight ${valueColor}`} role="status" aria-live="polite">
        Backend Status: {state.label}
      </p>
      <p className="mt-3 text-xs text-[#91a092]">{state.detail}</p>
    </section>
  );
}
