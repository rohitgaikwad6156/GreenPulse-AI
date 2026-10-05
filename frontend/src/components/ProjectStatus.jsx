import { Link } from "react-router-dom";

const steps = [
  [
    "/heat-map",
    "Open Heat Map",
    "Select NASA MODIS for independent historical satellite observations, then Research Model to inspect its current evidence gate.",
  ],
  ["/data-readiness", "View Data Readiness", "Inspect source provenance, audit evidence, blockers and next actions."],
  [
    "#model",
    "Explain the research method",
    "Discuss the 30 m analysis grid, continuous LST target and spatial block validation.",
  ],
  [
    "/scenario-simulator",
    "Show Scenario Simulator",
    "Demonstrate the model and calibration requirements before any intervention estimate.",
  ],
  [
    "/climate-action-optimizer",
    "Show the Optimizer",
    "Inspect the separate requirement for evidence-complete planning locations.",
  ],
  [
    "#project-status",
    "Return to Project Status",
    "Explain the remaining evidence and processing steps before a real model can be used.",
  ],
];

export default function ProjectStatus({ view, retry }) {
  return (
    <section id="project-status" className="project-status scroll-mt-24" aria-labelledby="project-status-title">
      <p className="eyebrow">Project status</p>
      <h2 id="project-status-title">How to demo GreenPulse today</h2>
      <p>
        GreenPulse separates implemented software from verified climate evidence. Explore the research workflow,
        independent satellite context, provenance and evidence gates.
      </p>
      {view.state === "loading" ? (
        <p role="status">Checking current project evidence…</p>
      ) : view.state === "unknown" ? (
        <div className="demo-notice">
          <strong>Not checked</strong>
          <p>Current project evidence could not be checked.</p>
          <button type="button" onClick={retry}>
            Retry status
          </button>{" "}
          <a href="#model">View methodology</a>
        </div>
      ) : (
        <div className="demo-notice">
          <strong>
            First model source gate: {view.sourceGate.count} / {view.sourceGate.total} ready
          </strong>
          <p>{view.message}</p>
          {!view.modelReady && <p>Real Pune/PCMC 30 m ML predictions are not available yet.</p>}
          <div className="demo-badges">
            {view.artifacts.map((item) => (
              <span key={item.id} className={item.ready ? "demo-verified" : "demo-waiting"}>
                {item.name}: {item.ready ? "Verified evidence" : "Waiting for evidence"}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="demo-columns">
        <article>
          <h3>What works now</h3>
          <p className="demo-label">Implemented software</p>
          <ul>
            {view.capabilities.map(([title, detail]) => (
              <li key={title}>
                <strong>{title}</strong>
                <p>{detail}</p>
              </li>
            ))}
          </ul>
          {view.availableEvidence.length > 0 && (
            <>
              <p className="demo-label">Verified evidence</p>
              <ul>
                {view.availableEvidence.map((item) => (
                  <li key={item.id}>{item.name}</li>
                ))}
              </ul>
            </>
          )}
        </article>
        <article>
          <h3>What waits for evidence</h3>
          {view.state !== "checked" ? (
            <p>Dynamic source and artifact status: Not checked.</p>
          ) : (
            <>
              <ul>
                {view.waitingEvidence.map((item) => (
                  <li key={item.id}>{item.name} — waiting for evidence</li>
                ))}
              </ul>
              {view.boundaryDetail && <p>{view.boundaryDetail}</p>}
              <p>
                {view.modelReady
                  ? "TreeSHAP software can use an accepted model; this summary does not verify a generated explanation."
                  : "Real TreeSHAP results wait for an accepted model."}
              </p>
              <p>
                Intervention estimates need model and calibration evidence. Field observations alone do not establish
                validated cooling.
              </p>
            </>
          )}
          <Link to="/data-readiness">View full Data Readiness →</Link>
        </article>
      </div>
      <article className="demo-path">
        <h3>Suggested demo path</h3>
        <ol>
          {steps.map(([to, title, detail]) => (
            <li key={title}>
              {to.startsWith("#") ? <a href={to}>{title}</a> : <Link to={to}>{title}</Link>}
              <p>{detail}</p>
            </li>
          ))}
        </ol>
      </article>
      <p className="demo-notice">
        MODIS is an independent observation layer for demonstration and context; it does not substitute for the
        GreenPulse 30 m research model.
      </p>
      <details>
        <summary>Evidence and claim boundaries</summary>
        <p>
          Only claim model accuracy, real SHAP drivers, intervention estimates or action plans when their own evidence
          gates are established. Scenario estimates are not measured cooling. LST is not pedestrian air temperature;
          Heat Hazard Score is not health-risk probability. GreenPulse does not substitute demo climate values for
          missing production evidence.
        </p>
      </details>
      <div className="demo-actions">
        <Link to="/heat-map">Explore satellite heat map →</Link>
        <Link to="/data-readiness">View Data Readiness →</Link>
        <a href="https://github.com/rohitgaikwad6156/GreenPulse-AI/blob/main/docs/data_card.md">Data documentation ↗</a>
        <a href="https://github.com/rohitgaikwad6156/GreenPulse-AI/blob/main/docs/model_card.md">
          Model documentation ↗
        </a>
      </div>
    </section>
  );
}
