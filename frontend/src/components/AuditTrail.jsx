import { useState } from "react";
import {
  auditPresentation,
  formatCelsius,
  auditDetailsLabel,
  AUDIT_DISCLAIMER,
  AUDIT_PRESERVATION,
} from "../utils/auditEvidence.js";

function AuditCard({ record }) {
  const [open, setOpen] = useState(false);
  const audit = auditPresentation(record);
  return (
    <article className="dr-panel dr-audit-card" id={`audit-${record.id}`}>
      <div className="dr-heading">
        <h3>{record.title}</h3>
        <span className={`dr-badge dr-audit-${audit.status}`}>
          {audit.display_status}
        </span>
      </div>
      <ul>
        {audit.summary.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="dr-note">{audit.interpretation}</p>
      <details onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary>
          {auditDetailsLabel(open)}
          <span className="sr-only">: {record.title}</span>
        </summary>
        <dl className="dr-audit-meta">
          <div>
            <dt>Audit type</dt>
            <dd>{record.audit_type}</dd>
          </div>
          <div>
            <dt>Source scope</dt>
            <dd>{record.scope}</dd>
          </div>
          <div>
            <dt>Recorded UTC</dt>
            <dd>
              {record.recorded_at
                ? new Date(record.recorded_at).toLocaleString("en-GB", {
                    timeZone: "UTC",
                  }) + " UTC"
                : "Date unavailable"}
            </dd>
          </div>
          <div>
            <dt>Saved audit result</dt>
            <dd>{record.audit_result || "Unavailable"}</dd>
          </div>
        </dl>
        {record.diagnostics?.map((scene) => (
          <p key={scene.date}>
            <a href={`#diagnostic-${scene.date}`}>
              {scene.date}: investigated{" "}
              {scene.extreme_label === "Absolute max"
                ? "high cluster"
                : "low clusters"}{" "}
              →
            </a>
          </p>
        ))}
        <a
          className="dr-doc"
          href={record.documentation_url}
          target="_blank"
          rel="noreferrer"
        >
          Read {record.title} documentation
          <span className="sr-only"> (opens in a new tab)</span> ↗
        </a>
      </details>
    </article>
  );
}

export default function AuditTrail({ data }) {
  const audits = Array.isArray(data.audit_trail) ? data.audit_trail : [];
  const diagnostics = audits.flatMap((audit) => audit.diagnostics || []);
  return (
    <>
      <section
        aria-labelledby="audit-trail-heading"
        className="dr-evidence-section"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">From source to scientific evidence</p>
            <h2 id="audit-trail-heading">Evidence & Audit Trail</h2>
            <p className="dr-note">
              Saved scientific audits document what has been checked, what
              passed, and what still requires source data. These audits do not
              by themselves create municipal climate results.
            </p>
          </div>
        </div>
        <div className="dr-source-grid">
          {audits.length ? (
            audits.map((audit) => <AuditCard key={audit.id} record={audit} />)
          ) : (
            <p className="dr-panel" role="status">
              Evidence unavailable. The backend has not supplied an audit trail.
            </p>
          )}
        </div>
        {Array.isArray(data.evidence_chains) && (
          <div className="dr-source-grid dr-chain-grid">
            {data.evidence_chains.map((chain) => (
              <section className="dr-panel" key={chain.title}>
                <h3>{chain.title}</h3>
                <ol className="dr-chain">
                  {chain.stages.map((stage) => (
                    <li key={stage.label}>
                      <span>{stage.label}</span>
                      <strong>{stage.status}</strong>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}
        <p className="dr-note">
          These chains describe saved source evidence and unmet prerequisites.
          REVIEWED means the diagnostic work was recorded; it does not confirm
          the cause or approve production use. Clipping and model completion
          require separate production evidence.
        </p>
      </section>
      <section className="dr-panel" aria-labelledby="diagnostics-heading">
        <p className="eyebrow">Bulk distribution vs absolute extremes</p>
        <h2 id="diagnostics-heading">Investigated Landsat diagnostics</h2>
        <div className="dr-diagnostic-note">
          <strong>{data.audit_disclaimer || AUDIT_DISCLAIMER}</strong>
          <p>{data.audit_preservation_note || AUDIT_PRESERVATION}</p>
        </div>
        <h3 className="dr-comparison-heading">
          Full-scene diagnostic distribution comparison
        </h3>
        <p className="dr-note">
          Percentiles describe the bulk distribution; an absolute extreme is a
          single endpoint. Thresholds below are diagnostic counts, never
          exclusion rules.
        </p>
        {diagnostics.length ? (
          <div className="dr-source-grid">
            {diagnostics.map((scene) => (
              <article
                className="dr-diagnostic"
                id={`diagnostic-${scene.date}`}
                key={scene.date}
              >
                <h4>
                  {scene.date} ·{" "}
                  {scene.extreme_label === "Absolute max"
                    ? "Investigated high cluster"
                    : "Investigated low clusters"}
                </h4>
                <p className="dr-product-id">{scene.product_id}</p>
                <dl className="dr-comparison">
                  <div>
                    <dt>{scene.percentile_label}</dt>
                    <dd>{formatCelsius(scene.percentile_celsius)}</dd>
                  </div>
                  <div>
                    <dt>{scene.extreme_label}</dt>
                    <dd>{formatCelsius(scene.extreme_celsius)}</dd>
                  </div>
                </dl>
                <ul className="dr-thresholds">
                  {scene.thresholds.map((range) => (
                    <li key={range.label}>
                      <strong>
                        {range.label}: {range.pixel_count} QA-valid pixels
                      </strong>
                      <span>
                        {range.cluster_count}{" "}
                        {range.cluster_count === 1
                          ? "contiguous cluster"
                          : "contiguous clusters"}{" "}
                        · largest: {range.largest_cluster_size} pixels
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="dr-note">Connectivity: 8 neighbours.</p>
                <p>{scene.finding}</p>
              </article>
            ))}
          </div>
        ) : (
          <p role="status">
            Evidence unavailable for the investigated scenes. Consult the saved
            extreme audit.
          </p>
        )}
      </section>
    </>
  );
}
