"""Portable, read-only provenance for a completed real model build.

The build pipeline owns publication. This module only observes Git, the runtime,
the verified manifest records, and already-created staged artifact bytes.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from backend.app.ml.spatial_cv import sha256_file

SCHEMA_VERSION = "1.0"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SCIENTIFIC_PACKAGES = (
    "numpy", "pandas", "pyarrow", "rasterio", "pyproj", "shapely",
    "scipy", "scikit-learn", "xgboost", "optuna", "joblib", "matplotlib",
)
ESSENTIAL_PACKAGES = set(SCIENTIFIC_PACKAGES) - {"pandas"}


def hash_file(path: Path) -> str:
    """Use the same sha256-prefixed file identity as spatial CV and baselines."""
    if not path.is_file():
        raise ValueError(f"Required reproducibility file is missing: {path.name}")
    return sha256_file(path)


def _git(root: Path, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", *args], cwd=root, capture_output=True,
            check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def get_git_state(root: Path) -> dict:
    """Capture commit plus a content fingerprint of tracked and untracked changes.

    Ignored build outputs are excluded by Git. No file names, diff content, Git
    remotes, environment variables, or host-specific paths enter the snapshot.
    """
    commit_bytes = _git(root, "rev-parse", "--verify", "HEAD")
    if commit_bytes is None:
        return {"commit": None, "dirty": None, "state": "unavailable",
                "status_summary": "Git identity unavailable", "working_tree_fingerprint": None}
    commit = commit_bytes.decode("ascii", errors="replace").strip().lower()
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("Git returned a malformed commit SHA; refusing reproducibility capture")
    top_bytes = _git(root, "rev-parse", "--show-toplevel")
    if top_bytes is None or Path(os.fsdecode(top_bytes.strip())).resolve() != root.resolve():
        raise ValueError("Build root is not the Git repository root")
    tracked = _git(root, "diff", "HEAD", "--binary", "--no-ext-diff", "--ignore-submodules=all")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or untracked is None:
        raise ValueError("Cannot inspect Git working-tree changes")
    names = [name for name in untracked.split(b"\0") if name]
    fingerprint = hashlib.sha256()
    fingerprint.update(len(tracked).to_bytes(8, "big"))
    fingerprint.update(tracked)
    for name in names:
        fingerprint.update(len(name).to_bytes(8, "big"))
        fingerprint.update(name)
        path = root / os.fsdecode(name)
        if path.is_symlink():
            fingerprint.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            fingerprint.update(hash_file(path).encode("ascii"))
        else:
            raise ValueError("Untracked working-tree entry changed during Git capture")
    dirty = bool(tracked or names)
    return {"commit": commit, "dirty": dirty, "state": "available",
            "status_summary": "tracked changes and/or untracked files" if dirty else "clean",
            "working_tree_fingerprint": fingerprint.hexdigest()}


def assert_git_unchanged(start: dict, end: dict) -> None:
    """Reject a different commit or working-tree content before publication."""
    if start["state"] != end["state"]:
        raise ValueError("Git availability changed during processing; nothing published")
    if start["state"] == "unavailable":
        return  # Explicitly incomplete identity; never invent a commit.
    if start["commit"] != end["commit"]:
        raise ValueError("Git commit changed during processing; nothing published")
    if (start["dirty"] != end["dirty"] or
            start["working_tree_fingerprint"] != end["working_tree_fingerprint"]):
        raise ValueError("Git working-tree content changed during processing; nothing published")


def repository_path(root: Path, path: Path) -> str:
    """Return a normalized portable path, refusing files outside the repository."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Reproducibility path must be inside the repository") from exc
    return relative.as_posix()


def build_pipeline_record(root: Path, manifest: Path, year: int, trials: int,
                          jobs: int) -> dict:
    """Describe effective parameters, including defaults omitted by the caller."""
    manifest_path = repository_path(root, manifest)
    parameters = {"year": year, "trials": trials, "jobs": jobs,
                  "manifest": manifest_path}
    command = ("python scripts/build_heat_map_pipeline.py"
               f" --year {year} --trials {trials} --jobs {jobs}"
               f" --manifest {json.dumps(manifest_path)}")
    return {"script": "scripts/build_heat_map_pipeline.py",
            "resolved_parameters": parameters, "command": command,
            "command_kind": "normalized effective invocation from repository root"}


def _requirement_chain(root: Path, path: Path, seen: set[Path]) -> None:
    path = path.resolve()
    repository_path(root, path)
    if path in seen:
        return
    if not path.is_file():
        raise ValueError(f"Required Python dependency file is missing: {path.name}")
    seen.add(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*-r\s+([^\s#]+)", line)
        if match:
            _requirement_chain(root, path.parent / match.group(1), seen)


def collect_dependency_files(root: Path) -> dict:
    """Hash the actual -r chain for XGBoost and the optional UI lockfile."""
    seen: set[Path] = set()
    _requirement_chain(root, root / "backend" / "requirements-xgboost.txt", seen)
    requirements = [{"path": repository_path(root, path), "sha256": hash_file(path)}
                    for path in sorted(seen)]
    lock = root / "frontend" / "package-lock.json"
    lock_record = {"path": "frontend/package-lock.json",
                   "sha256": hash_file(lock) if lock.is_file() else None,
                   "status": "available" if lock.is_file() else "not_available"}
    return {"python_requirement_files": requirements,
            "frontend_package_lock": lock_record}


def collect_runtime_versions() -> dict:
    """Collect relevant installed packages, not a noisy or secret-bearing env dump."""
    packages = {}
    for package in SCIENTIFIC_PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    node = shutil.which("node")
    node_version = None
    if node:
        try:
            result = subprocess.run([node, "--version"], capture_output=True, text=True,
                                    check=False, timeout=10)
            if result.returncode == 0 and re.fullmatch(r"v?\d+\.\d+\.\d+", result.stdout.strip()):
                node_version = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "node_version": node_version,
            "node_status": "available" if node_version else "not_available",
            "platform": {"system": platform.system(), "release": platform.release(),
                         "machine": platform.machine()},
            "scientific_packages": packages}


def source_records(sources: dict, model_source_ids: set[str]) -> dict:
    """Project the already-validated manifest evidence without rehashing raw data."""
    def safe_identifier(source: dict) -> str | None:
        identifier = source.get("dataset_identifier")
        if not isinstance(identifier, str):
            return None
        # A future manifest might contain a signed URL or credential. Its
        # verified checksum remains sufficient without copying that URL.
        if ("://" in identifier or Path(identifier).is_absolute()
                or PureWindowsPath(identifier).is_absolute()
                or re.search(r"(?i:token|secret|password|api[_-]?key)\s*[=:]", identifier)):
            return None
        return identifier

    records = []
    for source_id in sorted(model_source_ids):
        source = sources[source_id]
        checksum = source.get("checksum")
        if source.get("verification_status") != "verified" or not isinstance(checksum, str) or not SHA256_RE.fullmatch(checksum):
            raise ValueError(f"{source_id}: verified checksum required for snapshot")
        records.append({"source_id": source_id,
                        "dataset_identifier": safe_identifier(source),
                        "checksum": checksum,
                        "verification_status": source["verification_status"]})
    ward = None
    if "ward_boundaries" in sources:
        source = sources["ward_boundaries"]
        checksum = source.get("checksum")
        if source.get("verification_status") != "verified" or not isinstance(checksum, str) or not SHA256_RE.fullmatch(checksum):
            raise ValueError("Verified ward reporting source lacks a checksum")
        ward = {"source_id": "ward_boundaries", "role": "reporting_dependency",
                "dataset_identifier": safe_identifier(source),
                "checksum": checksum, "verification_status": "verified"}
    return {"model_sources": records, "reporting_dependency": ward}


def build_reproducibility_snapshot(root: Path, stage: Path, manifest: Path,
                                   git_state: dict, pipeline: dict, sources: dict,
                                   model_source_ids: set[str], artifact_paths: dict[str, str],
                                   model_report: dict, runtime: dict | None = None,
                                   dependency_identity: dict | None = None) -> dict:
    """Hash finalized staged bytes; model metadata itself is deliberately excluded."""
    artifacts = {key: {"path": relative, "sha256": hash_file(stage / relative)}
                 for key, relative in artifact_paths.items()}
    if model_report.get("dataset_version") != artifacts["ml_grid"]["sha256"]:
        raise ValueError("Model dataset checksum differs from staged grid")
    if model_report.get("model_artifact_sha256") != artifacts["model"]["sha256"]:
        raise ValueError("Model checksum differs from staged artifact")
    if (model_report.get("git_commit") != git_state["commit"]
            or model_report.get("git_dirty") != git_state["dirty"]):
        raise ValueError("Model metadata Git state differs from pipeline start")
    dependencies = dict(dependency_identity if dependency_identity is not None
                        else collect_dependency_files(root))
    dependencies["source_manifest"] = {"path": repository_path(root, manifest),
                                       "sha256": hash_file(manifest)}
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_timestamp_utc": model_report["training_date_utc"],
        "reproducibility_status": ("git_unavailable" if git_state["state"] == "unavailable"
                                   else "working_tree_modified" if git_state["dirty"] else "complete"),
        "git": git_state,
        "runtime": runtime if runtime is not None else collect_runtime_versions(),
        "pipeline": pipeline,
        "dependency_identity": dependencies,
        "sources": source_records(sources, model_source_ids),
        "randomness": {"model_seed": model_report["reproducibility_seed"],
                       "optuna_outer_seed_policy": "model_seed + outer fold number",
                       "optuna_final_seed_policy": "model_seed + 100"},
        "artifacts": artifacts,
    }
    validate_reproducibility_snapshot(snapshot)
    return snapshot


def validate_reproducibility_snapshot(snapshot: dict) -> None:
    """Fail before publication when essential identity is absent or malformed."""
    def portable(path: object) -> bool:
        return (isinstance(path, str) and bool(path) and not Path(path).is_absolute()
                and "\\" not in path and not PureWindowsPath(path).is_absolute()
                and ".." not in Path(path).parts
                and ".." not in PureWindowsPath(path).parts)

    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported reproducibility snapshot schema")
    git = snapshot.get("git", {})
    if git.get("state") == "available":
        if not isinstance(git.get("commit"), str) or not COMMIT_RE.fullmatch(git["commit"]):
            raise ValueError("Snapshot has an invalid Git commit")
        if not isinstance(git.get("dirty"), bool):
            raise ValueError("Snapshot lacks Git dirty state")
        if not re.fullmatch(r"[0-9a-f]{64}", str(git.get("working_tree_fingerprint"))):
            raise ValueError("Snapshot lacks Git working-tree fingerprint")
    elif (git.get("state") != "unavailable" or git.get("commit") is not None
          or git.get("dirty") is not None):
        raise ValueError("Snapshot must state unavailable Git identity explicitly")
    status = ("git_unavailable" if git["state"] == "unavailable" else
              "working_tree_modified" if git["dirty"] else "complete")
    if snapshot.get("reproducibility_status") != status:
        raise ValueError("Snapshot reproducibility status contradicts Git state")
    for timestamp in ("created_at_utc", "training_timestamp_utc"):
        if not isinstance(snapshot.get(timestamp), str) or not snapshot[timestamp]:
            raise ValueError(f"Snapshot lacks {timestamp}")
    runtime = snapshot.get("runtime", {})
    if not runtime.get("python_version") or not runtime.get("python_implementation"):
        raise ValueError("Snapshot lacks Python runtime identity")
    packages = runtime.get("scientific_packages", {})
    if any(not packages.get(package) for package in ESSENTIAL_PACKAGES):
        raise ValueError("Snapshot lacks an essential scientific package version")
    pipeline = snapshot.get("pipeline", {})
    if (not pipeline.get("command") or not portable(pipeline.get("script"))
            or not pipeline.get("resolved_parameters")
            or not portable(pipeline["resolved_parameters"].get("manifest"))):
        raise ValueError("Snapshot lacks resolved pipeline invocation")
    dependencies = snapshot.get("dependency_identity", {})
    for record in [*dependencies.get("python_requirement_files", []),
                   dependencies.get("source_manifest", {})]:
        if not portable(record.get("path")) or not SHA256_RE.fullmatch(str(record.get("sha256"))):
            raise ValueError("Snapshot lacks a dependency file identity")
    if not dependencies.get("python_requirement_files"):
        raise ValueError("Snapshot has no Python requirement-file identity")
    lock = dependencies.get("frontend_package_lock", {})
    if not portable(lock.get("path")):
        raise ValueError("Snapshot lacks a portable frontend lockfile path")
    if lock.get("status") == "available" and not SHA256_RE.fullmatch(str(lock.get("sha256"))):
        raise ValueError("Snapshot has an invalid frontend lockfile hash")
    if lock.get("status") not in {"available", "not_available"}:
        raise ValueError("Snapshot lacks frontend lockfile availability")
    sources = snapshot.get("sources", {}).get("model_sources", [])
    if not sources or any(source.get("verification_status") != "verified" or
                          not SHA256_RE.fullmatch(str(source.get("checksum"))) for source in sources):
        raise ValueError("Snapshot lacks verified model source checksums")
    for required in ("ml_grid", "grid_metadata", "spatial_cv_blocks",
                     "spatial_cv_metadata", "baseline_metrics", "model"):
        record = snapshot.get("artifacts", {}).get(required, {})
        path = record.get("path")
        if not portable(path) or not SHA256_RE.fullmatch(str(record.get("sha256"))):
            raise ValueError(f"Snapshot lacks a portable {required} checksum")
