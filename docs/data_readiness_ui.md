# Data Readiness

## Purpose and routes

The **Data Readiness** navigation item opens `/data-readiness`. The page reads
`GET /api/data-readiness` and presents recorded source status, supporting audits,
local availability, blockers and next actions. It also links from Overview and to
Methodology and the existing source documentation. It performs no processing,
verification, downloads, training or source writes.

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
same files are deployed alongside the API. Local checks read small file headers
and reject empty files and Git LFS pointers. They do not rehash sources, decode
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
information. Loading and connection failures have explicit states and retry
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
