import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, ExternalLink } from "lucide-react";
import PageIntro from "../components/PageIntro.jsx";
import { getDataReadiness } from "../services/api.js";
import {
  readinessPresentation,
  STATUS_LABELS,
} from "../utils/dataReadiness.js";

function Badge({ status }) {
  return (
    <span className={`dr-badge dr-${status}`}>
      {STATUS_LABELS[status] || "Blocked"}
    </span>
  );
}
export default function DataReadiness() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({
    loading: true,
    data: null,
    error: false,
  });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true, data: null, error: false });
    getDataReadiness(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ loading: false, data, error: false });
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setState({ loading: false, data: null, error: true });
      });
    return () => controller.abort();
  }, [attempt]);
  const view = readinessPresentation(state);
  const data = state.data;
  return (
    <div className="data-readiness">
      <PageIntro
        eyebrow="Evidence before processing"
        title="Data Readiness"
        description="Follow each source from acquisition to verification. See what the first real heat map needs, and what comes later."
      />
      <div className="dr-toolbar">
        <Link to="/methodology">Read the methodology →</Link>
        <button
          className="button-secondary"
          disabled={state.loading}
          onClick={() => setAttempt((n) => n + 1)}
        >
          Refresh evidence
        </button>
      </div>
      {view.state !== "ready" ? (
        <section
          className="dr-panel"
          role={view.state === "error" ? "alert" : "status"}
          aria-busy={view.state === "loading"}
        >
          <h2>
            {view.state === "loading"
              ? "Checking sources"
              : "Unable to check sources"}
          </h2>
          <p>{view.message}</p>
          {view.state === "error" && (
            <button
              className="button-primary"
              onClick={() => setAttempt((n) => n + 1)}
            >
              Try again
            </button>
          )}
        </section>
      ) : (
        <>
          {data.evidence_warnings?.map((warning) => (
            <p className="dr-warning" role="status" key={warning}>
              {warning}
            </p>
          ))}
          <section className="dr-panel" aria-labelledby="dr-summary">
            <p className="eyebrow">Production data readiness</p>
            <h2 id="dr-summary">Recorded source status</h2>
            <div className="dr-counts">
              {["verified", "staged", "pending", "blocked"].map((status) => (
                <div key={status}>
                  <strong>{data.summary?.[status] || 0}</strong>
                  <Badge status={status} />
                </div>
              ))}
            </div>
            <p className="dr-note">
              Counts include individual boundary outlines and their combined
              source record. Verification is recorded evidence; local
              availability and saved audits are checked separately below.
            </p>
          </section>
          <section className="dr-panel dr-gate" aria-labelledby="dr-gate">
            <div className="dr-heading">
              <div>
                <p className="eyebrow">First processing milestone</p>
                <h2 id="dr-gate">First real 30 m heat-map readiness</h2>
              </div>
              <Badge
                status={data.first_heat_map_ready ? "verified" : "blocked"}
              />
            </div>
            <p>
              <strong>
                {data.required_sources_ready}/{data.required_sources_total}{" "}
                required source groups ready
              </strong>{" "}
              · {view.blockerLabel}
            </p>
            <ul className="dr-checklist">
              {data.required_sources.map((source) => (
                <li key={source.id}>
                  {source.ready ? (
                    <CheckCircle2 size={19} aria-hidden="true" />
                  ) : (
                    <Circle size={19} aria-hidden="true" />
                  )}
                  <span>
                    {source.name}
                    <small>
                      {source.ready
                        ? "Source evidence ready"
                        : source.reason || "Evidence unavailable"}
                    </small>
                  </span>
                </li>
              ))}
            </ul>
            <p className="dr-note">
              {data.readiness_basis} Source readiness does not establish a
              trained model or accepted municipal results.
            </p>
          </section>
          <section aria-labelledby="dr-sources">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Evidence & next steps</p>
                <h2 id="dr-sources">Source inventory</h2>
              </div>
            </div>
            <div className="dr-source-grid">
              {view.sources.map((source) => (
                <article className="dr-panel dr-source" key={source.id}>
                  <div className="dr-heading">
                    <h3>{source.name}</h3>
                    <Badge status={source.status} />
                  </div>
                  <p className="dr-role">{source.role}</p>
                  <p className="dr-scope">
                    {source.scope === "first_heat_map"
                      ? "First heat-map requirement"
                      : source.scope === "boundary_component"
                        ? "Municipal boundary component"
                        : "Later-stage dependency"}
                  </p>
                  <h4>Evidence</h4>
                  <ul>
                    {source.evidence?.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  {source.audits?.map((audit) => (
                    <div className="dr-audit" key={audit.label}>
                      <strong>
                        {audit.label}:{" "}
                        {audit.status === "unavailable"
                          ? "Evidence unavailable"
                          : audit.status.toUpperCase()}
                      </strong>
                      {audit.details?.map((detail) => (
                        <span key={detail}>{detail}</span>
                      ))}
                      {audit.recorded_at && (
                        <small>
                          Recorded{" "}
                          {new Date(audit.recorded_at).toLocaleDateString(
                            "en-GB",
                            { timeZone: "UTC" },
                          )}
                        </small>
                      )}
                    </div>
                  ))}
                  {source.blocked_reason && (
                    <div className="dr-issue">
                      <h4>Why not complete</h4>
                      <p>{source.blocked_reason}</p>
                    </div>
                  )}
                  <div className="dr-next">
                    <h4>Next action</h4>
                    <p>{source.next_action}</p>
                  </div>
                  <a
                    className="dr-doc"
                    href={source.documentation_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Source documentation{" "}
                    <ExternalLink size={14} aria-hidden="true" />
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </article>
              ))}
            </div>
          </section>
          <section className="dr-panel" aria-labelledby="dr-later">
            <p className="eyebrow">Beyond the first heat map</p>
            <h2 id="dr-later">Later-stage project dependencies</h2>
            <p>
              These support reporting, research and validation. Ward GIS is not
              required for the first cell-level heat-map build.
            </p>
            <ul className="dr-later-list">
              {data.later_stage_dependencies.map((item) => (
                <li key={item.name}>
                  <div className="dr-heading">
                    <h3>{item.name}</h3>
                    <Badge status={item.status} />
                  </div>
                  <p>{item.detail}</p>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
