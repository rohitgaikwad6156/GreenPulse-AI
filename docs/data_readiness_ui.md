# Data Readiness

## Purpose and routes

The **Data Readiness** navigation item opens `/data-readiness`. Both it and Overview
read `GET /api/readiness`, which presents recorded source status, supporting audits,
local availability, blockers and next actions. It also links from Overview and to
Methodology and the existing source documentation. It performs no processing,
verification, downloads, training or source writes.

`GET /api/data-readiness` remains a deprecated compatibility alias with the same
response contract. `backend.app.data_intake.readiness.readiness()` remains the
single source/evidence readiness calculation. The API adds `software` (backend
runtime only, never a CI claim), `production_data` (`source_ready`, `blocked`, or
`unknown`), `first_heat_map` counts, `source_status`, `artifacts`, and `blockers`.
The detailed inventory, audits, evidence chains, and later-stage dependencies
remain available in the same response. `/api/methodology` still provides the
research description; its legacy artifact booleans derive from this readiness
projection.

The artifact summary checks the accepted real-grid Parquet schema and metadata,
then the model-metrics contract and matching model metadata. It checks verified
planning locations and registered field evidence separately. This request does
not hash the grid or model or deserialize the model; production endpoints perform
those full validations before use. Missing real sources block the production
source gate, while the runtime API can still be healthy. Local software test
status belongs to `scripts/project_health.ps1`, not this HTTP response.

## Source of truth

- `data/source_manifest.json`: recorded verification state, real-data classification,
  checksum presence and repository-relative source location.
- `data/provenance/landsat_quality_audit_2025.json`: scene and required-file counts.
- `data/provenance/landsat_processing_audit_2025.json`: processing audit outcome.
- `data/provenance/landsat_extreme_audit_2025.json`: diagnostic audit outcome. PASS
  does not mean the unusual full-scene temperature clusters are accepted for production.
- `data/provenance/sentinel_quality_audit_2025.json`: saved manual intake counts.
- `data/provenance/acquisition_pcmc_boundary.json`: individual outline staging evidence.
  An equivalent PMC acquisition record is supported when available.
- Intervention catalog and the existing imported field-validation registry: later-stage evidence.

Only selected fields are returned. Absolute paths and raw provenance documents are
never sent to the browser. Evidence links point to repository documentation.
Audit counts are explicitly historical evidence; they do not prove that all the
same files are deployed alongside the API. Local checks use file metadata and only tiny non-raster headers; they reject empty files and typical Git LFS pointers. They do not rehash sources, decode
rasters, validate GIS geometry, or check spatial coverage.

## Vocabulary

| Status | Meaning |
| --- | --- |
| Verified | Manifest records verification with real-data classification and a SHA-256 record. |
| Staged | An individual outline has acquisition provenance and a recorded checksum, or field evidence is registered; acceptance is still separate. |
| Pending | Recorded verification or acquisition remains pending. |
| Blocked | Evidence is unavailable, rejected or inconsistent; also used for the first source gate. |
| Optional | Neutral presentation vocabulary, reserved for explicitly optional future inputs. |

Verification is never inferred from a PASS audit alone. A missing audit does not
erase a manifest verification record: the card retains the recorded status,
shows **Evidence unavailable**, and blocks its first-build readiness. Counts include
the combined municipal record and the two individual outline cards, as labelled.
A verified combined record covers its municipal components; independent staged
outlines cannot verify the combined record.

## First build versus later dependencies

The five required source IDs are imported directly from
`scripts/build_heat_map_pipeline.py::SOURCE_IDS`. A group is ready only when its
recorded evidence is verified, local content is available, and its supporting
audits (where applicable) pass. `first_heat_map_ready` and `overall_status` refer
only to this source gate. Production preflight must still validate checksums,
coverage, source contracts and reference grids before processing.

At implementation time this checkout reports **3/5** groups ready: Landsat,
WorldCover and OSM roads. Sentinel and the combined municipal boundary are the
two blockers. The recorded summary is four verified, one staged and six pending
inventory entries. PCMC staging is not combined-boundary verification.

WorldPop, ward GIS, green spaces, the peri-urban reference, intervention evidence
and field validation appear separately. Ward GIS supports reporting/UI and does
not block the first cell-level build. Source readiness never implies model,
optimizer or municipal-temperature acceptance.

## Fallback behavior

Missing/malformed audit JSON, invalid counts, missing manifest records and LFS
pointers fail closed. The API still returns the inventory with clear missing
information. Malformed manifest evidence makes `production_data` unknown rather
than implying a known blocker count. Loading and connection failures have explicit states and retry
controls; they never fall back to demo data. Missing scientific evidence cannot
be replaced by simulated evidence without misrepresenting production readiness.

## Validation

Synthetic backend fixtures test recorded Landsat/Sentinel states, PCMC staging,
PMC absence, exact first-build blockers, ward independence, missing/malformed
audits, malformed manifests, LFS availability and read-only API behavior.
Frontend presentation tests cover verified/pending/staged labels, next actions,
blocker counts, loading, errors and invalid responses.

Run:

```text
python -m pytest tests/test_data_readiness.py -q
cd frontend
npm test
npm run build
```

The implementation was also checked against the full Python suite and in a local
browser at desktop and mobile widths. The API must have access to repository
evidence files in deployment; missing deployment sources are shown as unavailable,
even when a saved audit from the acquisition workstation passed.

## Evidence / Audit Viewer

The existing `/api/data-readiness` response now includes `audit_trail`,
`evidence_chains`, `audit_disclaimer` and `audit_preservation_note`. The same
validated audit projections also remain attached to their source cards. No new
endpoint or separate readiness system is introduced. Source cards link to their
supporting audits; native keyboard-accessible disclosures reveal audit type,
UTC timestamp, saved result, scope and documentation.

The four cards use the existing structured source, processing, extreme and
Sentinel intake JSON files. Summary counts and diagnostic numbers come from
these files, never frontend result constants. Dates without a valid timezone
are shown as unavailable. Markdown is linked for context, not parsed as data.

### Audit status semantics

- **PASS**: saved checks passed; this is not production or municipal acceptance.
- **PENDING**: Sentinel intake explicitly records PENDING and the saved counts
  show missing SAFE products or required file slots. The underlying **FAIL** is
  preserved and explained as missing-source acquisition work. Existing files may
  still have validation problems; a complete but failing intake is **REVIEW**.
- **REVIEW**: an audit failed checks, or the extreme diagnostic work passed but
  the causes of the investigated values remain unresolved.
- **UNAVAILABLE**: missing JSON, invalid schema, impossible counts, invalid
  result state, nonfinite diagnostic values or inconsistent cluster evidence.

The manifest remains authoritative. Audits cannot promote pending sources to
verified. Evidence-chain completion is not invented from available inputs:
municipal clipping and model-dataset completion require separate execution
records. `NOT ESTABLISHED` is used when prerequisites alone are available.
Sentinel selection is derived from valid unique product IDs in discovery JSON.

### Scientific interpretation

The March 10 comparison shows P99 versus the absolute maximum, threshold counts,
8-neighbour cluster counts and the repeated maximum DN. The April 3 comparison
shows P1 versus the minimum, cold threshold clusters and the recorded count of
QA-invalid neighbours. A possible saturation/capping signal or QA-edge effect
is described conditionally from the saved scalar evidence. Causes are not
established; values are not labelled wrong, clipped or excluded.

**These are full-scene diagnostics, not Pune/PMC/PCMC temperature results.**
The extreme audit did not change production QA rules or alter source pixels.
Raw neighbourhoods, QA arrays, coordinates and arbitrary JSON strings are not
returned. The viewer only emits allowlisted numbers and controlled descriptions.

### Lightweight, read-only behavior

The earlier header check was narrowed: TIFF/JP2 sources are never opened by this
API. Local presence uses filesystem metadata; raster files at most 1 KiB are
unavailable (including typical LFS pointers). Only tiny non-raster metadata files
are checked for LFS headers. Large files are not read or hashed. Saved audit JSON
is parsed without rerunning audits or scientific processing. This is an evidence
viewer, not a replacement for production checksum and raster preflight.

Synthetic tests cover count consistency, missing and malformed reports,
Sentinel pending/review distinctions, extreme field allowlisting, disclaimers,
nonfinite values, read-only behavior and forbidden raster reads. Frontend tests
cover audit statuses, disclosure labels, diagnostic formatting and unavailable
fallbacks. Existing readiness tests still cover backend connection errors.
