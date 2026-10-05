import { useEffect, useState } from "react";
import { ArrowRight, BookOpenText, MapPinned, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import BackendStatus from "../components/BackendStatus.jsx";
import PageIntro from "../components/PageIntro.jsx";
import { getMethodology } from "../services/api.js";
import { researchWorkflow } from "../utils/researchWorkflow.js";

export default function Overview() {
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState({
    loading: true,
    data: null,
    error: "",
  });
  useEffect(() => {
    const controller = new AbortController();
    setStatus({ loading: true, data: null, error: "" });
    getMethodology(controller.signal)
      .then((data) => {
        if (!data?.data_status)
          throw new Error(
            "The backend returned an incomplete research status.",
          );
        if (!controller.signal.aborted)
          setStatus({ loading: false, data: data.data_status, error: "" });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setStatus({
            loading: false,
            data: null,
            error: error.response
              ? `The backend returned HTTP ${error.response.status}. Retry after the service is available.`
              : "Cannot check research inputs. The backend may be starting; retry the connection.",
          });
      });
    return () => controller.abort();
  }, [attempt]);
  const stages = researchWorkflow(status.data);
  const cards = [
    [
      "Satellite ML grid",
      status.data?.real_ml_grid_available,
      "Observed Landsat LST and aligned features",
    ],
    [
      "Trained XGBoost model",
      status.data?.trained_model_available,
      "Saved model and metadata; results require validation",
    ],
    [
      "Planning evidence",
      status.data?.optimizer_location_available,
      "At least one location with verified planning inputs",
    ],
  ];

  return (
    <>
      <section className="overview-hero">
        <PageIntro
          eyebrow="Pune / PCMC · Research workspace"
          title="Better climate decisions start with evidence."
          description="Explore surface heat, understand model predictions, and compare the interventions that could make a difference."
        />
        <div className="hero-actions">
          <Link to="/heat-map" className="button-primary">
            <MapPinned size={18} aria-hidden="true" /> Explore the heat map{" "}
            <ArrowRight size={17} aria-hidden="true" />
          </Link>
          <Link to="/methodology" className="button-secondary">
            How the research works <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>
      <section className="readiness-panel" aria-labelledby="readiness-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Before you begin</p>
            <h2 id="readiness-heading">Research readiness</h2>
          </div>
          <button
            type="button"
            disabled={status.loading}
            onClick={() => setAttempt((value) => value + 1)}
            className="button-secondary"
          >
            <RefreshCw
              size={15}
              className={status.loading ? "animate-spin" : ""}
              aria-hidden="true"
            />{" "}
            Refresh status
          </button>
        </div>
        <div className="readiness-grid">
          <BackendStatus key={attempt} />
          {cards.map(([label, present, detail]) => (
            <section key={label} className="readiness-item">
              <h3>{label}</h3>
              <p
                className={`readiness-value ${status.data && !present ? "needs-input" : ""}`}
              >
                {status.loading
                  ? "Checking…"
                  : !status.data
                    ? "Not checked"
                    : present
                      ? "Inputs present"
                      : "Inputs needed"}
              </p>
              <p className="readiness-detail">{detail}</p>
            </section>
          ))}
        </div>
        <div className="readiness-summary">
          <p role="status">
            {status.loading
              ? "Checking research inputs. A sleeping service may take about a minute to start."
              : status.error ||
                (status.data.real_ml_grid_available &&
                status.data.trained_model_available
                  ? "Grid and model files are present. Each research stage checks evidence and compatibility before producing results."
                  : "Climate predictions are not ready yet. The real satellite grid and trained model are not both available.")}
          </p>
          <p>
            Input availability does not establish model accuracy. Missing
            measurements are never replaced with demonstration values.
          </p>
        </div>
      </section>
      <div className="overview-bottom">
        <section className="workflow-panel" aria-labelledby="workflow-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">From observation to action</p>
              <h2 id="workflow-heading">Your research workflow</h2>
            </div>
            <span className="text-sm text-[#63736a]">5 stages</span>
          </div>
          <ol className="workflow-list">
            {stages.map((stage, index) => (
              <li key={stage.to}>
                <span className="stage-number" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <div className="workflow-title">
                    <Link to={stage.to}>
                      {stage.title.replace(/^\d+\. /, "")}
                      <ArrowRight size={16} aria-hidden="true" />
                    </Link>
                    <span className="status-tag">
                      {status.loading ? "Checking…" : stage.state}
                    </span>
                  </div>
                  <p>{stage.detail}</p>
                  <p className="stage-requirement">{stage.missing}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <aside className="interpretation-note">
          <BookOpenText size={26} strokeWidth={1.5} aria-hidden="true" />
          <p className="eyebrow">A note on interpretation</p>
          <h2>Surface heat is one part of the story.</h2>
          <p>
            Landsat surface temperature is not pedestrian air temperature. Model
            explanations describe predictions; scenario cooling remains an
            estimate.
          </p>
          <p>
            Heat Hazard Score is a relative display index, not a health-risk
            probability.
          </p>
          <Link to="/methodology">
            Read the methods & limitations{" "}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </aside>
      </div>
    </>
  );
}
