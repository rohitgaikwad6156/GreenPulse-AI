# Reproducing a future real GreenPulse model run

**Status (2026-10-05): contract implemented; no accepted real model or production reproducibility snapshot exists yet.** The current grid/model files are legacy demo artifacts. This document describes evidence that a *successful future real* [`build_heat_map_pipeline.py`](../scripts/build_heat_map_pipeline.py) run will stage and publish with the model.

## Evidence written after a successful real build

The pipeline writes `models/reproducibility_snapshot.json` using schema version `1.0`. It participates in the same staged publication and backup/rollback operation as the dataset and model. A failed source check, changed Git state, invalid hash, or failed publication does not create a successful new snapshot.

| Snapshot section | Recorded identity | Why it matters |
| --- | --- | --- |
| `git` | Local `git rev-parse --verify HEAD` 40-character commit, dirty state, compact status and content fingerprint | A commit identifies tracked code history. A dirty checkout cannot be reconstructed from its commit alone. The fingerprint detects changes to tracked and non-ignored untracked content during the run without exposing file names or diffs. |
| `pipeline` | Repository-relative script, normalized command, resolved `year`, `trials`, `jobs`, and manifest path | Captures effective defaults even if the literal invocation omitted them. Run the command from the repository root. |
| `runtime` | Exact Python patch version and implementation; OS, release and machine architecture; selected installed scientific-package versions; optional Node version | Installed transitive package versions and platform can affect results. No hostname, username, environment dump or credentials are stored. |
| `dependency_identity` | SHA-256 of the actual `-r` chain rooted at `backend/requirements-xgboost.txt`, the source manifest, and optional `frontend/package-lock.json` | The Python chain currently includes base, data, ML and XGBoost requirements. SHAP/optimizer/test requirements are outside this training chain. The frontend lock identifies the UI environment used to display results, not model mathematics. |
| `sources` | Verified manifest dataset identifiers and recorded `sha256:` checksums for the five first-build source IDs; optional ward GIS under `reporting_dependency` | The manifest and existing preflight remain authoritative. The snapshot copies the identities preflight accepted; it does not substitute for source-file validation or recompute enormous raw source hashes a third time. |
| `artifacts` | SHA-256 of final staged ML Parquet, grid metadata, spatial-fold map and metadata, baseline report, and saved model | Connects the model to the exact training rows, fold allocation, and baseline comparison. The model hash matches `model_artifact_sha256`; the Parquet hash matches `dataset_version`. |
| `randomness` and timestamps | Model seed, Optuna outer/final sampler-seed policy, model training timestamp, snapshot creation time | Distinguishes the saved model run from later runs. |

The snapshot deliberately does **not** hash `models/model_metadata.json` inside itself, avoiding a recursive checksum. New real `models/model_metadata.json` exposes `git_commit`, `git_dirty`, `git_state`, a dirty/unavailable note, `pipeline_command`, resolved `pipeline_parameters`, and `reproducibility_snapshot`, alongside its existing dataset/model hashes, fold metrics, tuning and software fields. Standalone `train_xgboost_lst.py` remains usable and records Git identity or an explicit unavailable state; the consolidated snapshot belongs to the full real pipeline.

## Publication policy

The pipeline captures Git at the beginning of the build and compares commit and working-tree content immediately before publication. Existing dirty state is permitted and labelled `working_tree_modified`; the snapshot explicitly warns that the commit alone cannot reconstruct those modifications. A changed commit, tracked content, or non-ignored untracked content during execution stops publication. Ignored output directories such as `data/interim/`, `data/processed/`, and `models/` do not falsely count as source-code changes. Git absence is represented by `commit: null`, `state: unavailable`, and `reproducibility_status: git_unavailable`; the build may complete, but commit-level reproducibility is explicitly incomplete. A malformed SHA fails closed.

The required scientific environment, Python requirement files, verified source checksums, dataset and model hashes, resolved invocation, and schema must be present for a snapshot to validate. Node is optional for Python model generation. The frontend lockfile is recorded when present and labelled `not_available` otherwise. A custom manifest for the full build must be inside the repository so the recorded path and command remain portable. No Git reset, checkout, stash, commit, network call, package install, or source modification is performed by snapshot collection.

## Future verification procedure

1. Read the model metadata and snapshot only after the real source gate and artifact acceptance pass. Confirm schema version, `git_commit`, `git_dirty`, `dataset_version`, `model_artifact_sha256`, and snapshot status agree. An incomplete Git identity or dirty checkout needs its additional working-tree changes preserved separately.
2. Check out the recorded commit in an isolated repository. Verify the recorded hashes of the pinned Python requirement files and source manifest. For UI reproduction, verify the frontend package-lock hash too.
3. Build a Python environment matching the recorded Python patch version and installed scientific-package versions. Record any OS/architecture differences. Node is needed only for reproducing the frontend environment.
4. Obtain the same authorized real source files. Confirm each of the five manifest source IDs, checksum and verification status; inspect any separate verified ward reporting dependency. Run the existing source preflight.
5. Run the recorded normalized command with the resolved parameters from the repository root. Inspect the new source checks, real grid metadata, spatial block map, baseline report, held-out model metrics and artifact reload result.
6. Compare input and output identities: Parquet, metadata, spatial-fold artifacts, baseline report and model. Investigate differing hashes and metrics in light of library, platform, source-byte, and dirty-working-tree differences.

Matching source/code/dependency records supports reconstruction but does not guarantee bit-for-bit identical XGBoost artifacts across operating systems, architectures, library builds or parallel execution. Distinguish environment reconstruction and scientific agreement of held-out results from byte-identical model serialization. See the [Data Card](data_card.md), [Model Card](model_card.md), [real pipeline](real_heat_map_pipeline.md), and [XGBoost workflow](xgboost_lst_pipeline.md).
