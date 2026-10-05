import { AlertCircle, ArrowRight, CheckCircle2, Circle, RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";

function Artifact({ name, status }) {
  return (
    <li className="model-readiness-artifact">
      {status === "ready" ? <CheckCircle2 size={17} aria-hidden="true" /> : <Circle size={17} aria-hidden="true" />}
      <span>{name}</span>
      <strong>{status === "ready" ? "Ready" : status === "staged" ? "Staged" : "Blocked"}</strong>
    </li>
  );
}

export default function ModelReadinessPanel({ presentation, onRetry, onSatellite }) {
  const { state } = presentation;
  if (state === "LOADING")
    return (
      <section className="model-readiness-card" aria-busy="true">
        <p role="status">{presentation.message}</p>
      </section>
    );
  if (state === "UNKNOWN")
    return (
      <section className="model-readiness-card" aria-labelledby="model-readiness-title">
        <div className="model-readiness-heading">
          <AlertCircle size={21} aria-hidden="true" />
          <div>
            <p className="eyebrow">Research model</p>
            <h2 id="model-readiness-title">Could not check research model readiness</h2>
          </div>
        </div>
        <p className="model-readiness-copy">{presentation.message}</p>
        <div className="model-readiness-actions">
          <button type="button" className="button-primary" onClick={onRetry}>
            Retry readiness status
          </button>
          <button type="button" className="button-secondary" onClick={onSatellite}>
            View NASA MODIS instead
          </button>
        </div>
        <p className="model-readiness-footnote">
          NASA MODIS is an independent historical satellite observation layer, not the GreenPulse 30 m model.
        </p>
      </section>
    );

  return (
    <section className="model-readiness-card" aria-labelledby="model-readiness-title">
      <div className="model-readiness-heading">
        <Circle size={21} aria-hidden="true" />
        <div>
          <p className="eyebrow">Research model · 30 m analysis grid</p>
          <h2 id="model-readiness-title">Research model not available yet</h2>
        </div>
      </div>
      <p className="model-readiness-copy">{presentation.message}</p>
      <div className="model-readiness-layout">
        <div>
          <h3>Data preparation</h3>
          <p className="model-readiness-count">
            <strong>
              {presentation.readyCount} / {presentation.totalCount}
            </strong>{" "}
            required source groups ready
          </p>
          <ul className="model-readiness-sources">
            {presentation.required.map((source) => (
              <li key={source.id}>
                {source.ready ? <CheckCircle2 size={17} aria-hidden="true" /> : <Circle size={17} aria-hidden="true" />}
                <span>{source.name}</span>
                <strong>{source.status}</strong>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3>{state === "WAITING_FOR_BUILD" ? "Next: build and validate" : "Remaining data blockers"}</h3>
          {presentation.waiting.length ? (
            <ul className="model-readiness-next">
              {presentation.waiting.map((source) => (
                <li key={source.id}>
                  <strong>{source.name}</strong>
                  <span>{source.nextAction || source.reason}</span>
                  {source.id === "municipal_boundary" && presentation.boundaryDetail && (
                    <small>{presentation.boundaryDetail}</small>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="model-readiness-copy">
              The source gate is ready. Process the real grid, train the model and review spatial validation.
            </p>
          )}
          <h3 className="model-readiness-subheading">Pipeline artifacts</h3>
          <ul className="model-readiness-artifacts">
            <Artifact name="Real 30 m ML grid" status={presentation.grid} />
            <Artifact name="Trained XGBoost model" status={presentation.model} />
          </ul>
        </div>
      </div>
      <p className="model-readiness-footnote">
        Source readiness does not establish model accuracy. The 30 m analysis grid does not increase native Landsat
        thermal resolution.
      </p>
      <div className="model-readiness-actions">
        <Link className="button-primary" to="/data-readiness">
          View full Data Readiness <ArrowRight size={16} aria-hidden="true" />
        </Link>
        <button type="button" className="button-secondary" onClick={onSatellite}>
          View NASA MODIS instead
        </button>
        <button type="button" className="model-readiness-retry" onClick={onRetry}>
          <RotateCcw size={14} aria-hidden="true" /> Refresh status
        </button>
      </div>
      <p className="model-readiness-footnote">
        NASA MODIS remains available as an independent historical satellite observation layer. It is not the GreenPulse
        30 m model.
      </p>
    </section>
  );
}
