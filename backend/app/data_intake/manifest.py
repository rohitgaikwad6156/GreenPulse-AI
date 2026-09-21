"""Validate the GreenPulse source manifest before any real-data processing.

The manifest is evidence, not a downloader.  A source is usable only when its
metadata is complete, its local content matches the recorded SHA-256 digest,
and its declared geospatial/temporal properties agree with the local files.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pyproj import CRS


CONTRACT_VERSION = "1.0"
REQUIRED_SOURCE_IDS = {
    "municipal_boundary",
    "ward_boundaries",
    "landsat_lst_scenes",
    "sentinel2_l2a_scenes",
    "esa_worldcover",
    "osm_roads",
    "osm_green_spaces",
    "worldpop",
    "periurban_lst_reference",
}
OPTIONAL_SOURCE_IDS = {"osm_buildings", "measured_albedo"}
FUTURE_SOURCE_IDS = {"municipal_sensor_observations"}
ALL_SOURCE_IDS = REQUIRED_SOURCE_IDS | OPTIONAL_SOURCE_IDS | FUTURE_SOURCE_IDS
VALID_SCOPES = {"required_mvp", "optional_mvp", "future_scope"}
VALID_STATUSES = {"pending", "verified", "rejected"}
SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
SEASON_RE = re.compile(r"^(\d{4})-03-01/(\d{4})-05-31$")


@dataclass
class ValidationReport:
    """Machine- and human-readable validation result."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified_sources: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verified_sources": self.verified_sources,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _error(report: ValidationReport, source_id: str, field_name: str, message: str) -> None:
    report.errors.append(f"{source_id}.{field_name}: {message}")


def _parse_date(value: Any, source_id: str, field_name: str, report: ValidationReport) -> date | None:
    if not isinstance(value, str):
        _error(report, source_id, field_name, "must be an ISO date (YYYY-MM-DD)")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        _error(report, source_id, field_name, f"invalid ISO date: {value!r}")
        return None


def sha256_path(path: Path) -> str:
    """Hash a file, or a directory tree including relative names and content.

    Directory hashing is deterministic and intentionally excludes no files.
    Re-extracted or changed source content therefore requires re-verification.
    """
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    elif path.is_dir():
        files = sorted(item for item in path.rglob("*") if item.is_file())
        if not files:
            raise ValueError("directory is empty")
        for item in files:
            relative = item.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            with item.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    else:
        raise ValueError("path does not exist")
    return f"sha256:{digest.hexdigest()}"


def _safe_local_path(root: Path, value: Any, source_id: str, report: ValidationReport) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        _error(report, source_id, "local_path", "must be a non-empty repository-relative path")
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        _error(report, source_id, "local_path", "must be repository-relative, not absolute")
        return None
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        _error(report, source_id, "local_path", "must not escape the repository root")
        return None
    return resolved


def _check_crs(value: Any, source_id: str, report: ValidationReport) -> CRS | None:
    if not isinstance(value, str) or not value.strip():
        _error(report, source_id, "crs", "is required (for example EPSG:4326)")
        return None
    if value == "SOURCE_NATIVE_MIXED":
        return None
    try:
        return CRS.from_user_input(value)
    except Exception:
        _error(report, source_id, "crs", f"is not a recognized CRS: {value!r}")
        return None


def _check_resolution(value: Any, source_id: str, report: ValidationReport) -> tuple[float, str] | None:
    if not isinstance(value, dict):
        _error(report, source_id, "resolution", "must be an object with value and unit")
        return None
    number, unit = value.get("value"), value.get("unit")
    if not isinstance(number, (int, float)) or isinstance(number, bool) or number <= 0:
        _error(report, source_id, "resolution.value", "must be a positive number")
        return None
    if unit not in {"m", "vector", "point", "native"}:
        _error(report, source_id, "resolution.unit", "must be m, vector, point, or native")
        return None
    return float(number), unit


def _check_raster(path: Path, declared_crs: CRS | None, resolution: tuple[float, str] | None,
                  source_id: str, report: ValidationReport) -> None:
    try:
        import rasterio
        with rasterio.open(path) as dataset:
            if dataset.crs is None:
                _error(report, source_id, "crs", "local raster has no CRS")
            elif declared_crs is not None and CRS.from_user_input(dataset.crs) != declared_crs:
                _error(report, source_id, "crs", f"manifest {declared_crs.to_string()} != local raster {dataset.crs}")
            if resolution and resolution[1] == "m" and declared_crs and declared_crs.is_projected:
                expected = resolution[0]
                actual = tuple(abs(float(item)) for item in dataset.res)
                if any(abs(item - expected) > max(1e-6, expected * 0.001) for item in actual):
                    _error(report, source_id, "resolution", f"manifest {expected} m != local raster {actual} m")
    except (OSError, ValueError) as exc:
        _error(report, source_id, "local_path", f"cannot inspect raster: {exc}")


def _check_geojson(path: Path, source_id: str, report: ValidationReport) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _error(report, source_id, "local_path", f"cannot read GeoJSON: {exc}")
        return
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        _error(report, source_id, "local_path", "GeoJSON must be a non-empty FeatureCollection")


def _check_product_specific(source: dict[str, Any], path: Path, start: date | None,
                            end: date | None, declared_crs: CRS | None,
                            resolution: tuple[float, str] | None,
                            report: ValidationReport) -> None:
    source_id = source["id"]
    kind = source.get("format")
    if kind == "raster":
        _check_raster(path, declared_crs, resolution, source_id, report)
    elif kind == "raster_directory":
        rasters = sorted(path.rglob("*.tif")) + sorted(path.rglob("*.TIF"))
        if not rasters:
            _error(report, source_id, "local_path", "contains no GeoTIFF files")
        else:
            for raster in rasters:
                _check_raster(raster, declared_crs, resolution, source_id, report)
        if source_id == "esa_worldcover":
            try:
                from backend.app.geospatial.urban_morphology import discover_worldcover_tiles
                discover_worldcover_tiles(path)
            except ValueError as exc:
                _error(report, source_id, "local_path", str(exc))
    elif kind == "geojson":
        _check_geojson(path, source_id, report)
        if source_id == "municipal_boundary":
            try:
                from backend.app.geospatial.landsat_lst import load_municipal_boundary
                load_municipal_boundary(path)
            except ValueError as exc:
                _error(report, source_id, "local_path", str(exc))
        elif source_id == "ward_boundaries":
            try:
                from backend.app.geospatial.ml_dataset import load_wards
                load_wards(path)
            except (ImportError, ValueError) as exc:
                _error(report, source_id, "local_path", str(exc))
        elif source_id.startswith("osm_"):
            kind_name = {"osm_roads": "roads", "osm_green_spaces": "green", "osm_buildings": "buildings"}[source_id]
            try:
                from backend.app.geospatial.urban_morphology import load_osm_geometries
                load_osm_geometries(path, kind_name)
            except ValueError as exc:
                _error(report, source_id, "local_path", str(exc))
    elif kind == "landsat_l2sp_directory" and start and end:
        from backend.app.geospatial.landsat_lst import discover_scenes
        if start.year != end.year:
            _error(report, source_id, "scene_date_range", "Landsat MVP season must be within one year")
        else:
            try:
                scenes = discover_scenes(path, start.year)
                outside = [scene.product_id for scene in scenes if not start <= scene.acquisition_date <= end]
                if outside:
                    _error(report, source_id, "scene_date_range", f"scenes fall outside declared range: {outside}")
            except ValueError as exc:
                _error(report, source_id, "local_path", str(exc))
    elif kind == "sentinel2_safe_directory" and start and end:
        from backend.app.geospatial.sentinel2_indices import discover_granules
        if start.year != end.year:
            _error(report, source_id, "scene_date_range", "Sentinel-2 MVP season must be within one year")
        else:
            try:
                granules = discover_granules(path, start.year)
                outside = [item.product_id for item in granules if not start <= item.acquisition_date <= end]
                if outside:
                    _error(report, source_id, "scene_date_range", f"scenes fall outside declared range: {outside}")
            except ValueError as exc:
                _error(report, source_id, "local_path", str(exc))
    elif kind == "parquet" and source_id == "periurban_lst_reference" and start and end:
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(path, columns=["grid_id", "lst_c"])
            if table.num_rows == 0:
                _error(report, source_id, "local_path", "peri-urban Parquet has no rows")
        except (ImportError, OSError, KeyError) as exc:
            _error(report, source_id, "local_path", f"Parquet must contain grid_id and lst_c columns: {exc}")
        provenance_entries = [item for item in source.get("companion_files", [])
                              if isinstance(item, dict) and item.get("role") == "provenance"]
        if len(provenance_entries) != 1:
            _error(report, source_id, "companion_files", "exactly one provenance companion is required")
        else:
            provenance_path = (path.parents[2] / provenance_entries[0].get("local_path", "")).resolve()
            try:
                provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
                required = ("source_organization", "source_product", "source_scene_or_composite",
                            "periurban_area_definition", "area_boundary_source", "qa_mask_method")
                if any(not isinstance(provenance.get(key), str) or not provenance[key].strip() for key in required):
                    raise ValueError("required provenance text is missing")
                if provenance.get("date_range") != f"{start.isoformat()}/{end.isoformat()}":
                    raise ValueError("date_range does not match the manifest peak-summer season")
                if provenance.get("temperature_variable") != "land_surface_temperature" or provenance.get("units") != "degC":
                    raise ValueError("temperature_variable must be land_surface_temperature and units must be degC")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                _error(report, source_id, "companion_files", f"invalid peri-urban provenance JSON: {exc}")


def _check_companions(source: dict[str, Any], root: Path, report: ValidationReport) -> None:
    source_id = source["id"]
    companions = source.get("companion_files", [])
    if not isinstance(companions, list):
        _error(report, source_id, "companion_files", "must be an array")
        return
    for index, companion in enumerate(companions):
        prefix = f"companion_files[{index}]"
        if not isinstance(companion, dict):
            _error(report, source_id, prefix, "must be an object")
            continue
        role = companion.get("role")
        if not isinstance(role, str) or not role.strip():
            _error(report, source_id, f"{prefix}.role", "must be non-empty")
        raw_path = companion.get("local_path")
        local = _safe_local_path(root, raw_path, source_id, report)
        expected = companion.get("checksum")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            _error(report, source_id, f"{prefix}.checksum", "must be sha256:<64 lowercase hex characters>")
        if local and not local.is_file():
            _error(report, source_id, f"{prefix}.local_path", f"required companion file is missing: {raw_path}")
        elif local and isinstance(expected, str) and SHA256_RE.fullmatch(expected):
            actual = sha256_path(local)
            if actual != expected:
                _error(report, source_id, f"{prefix}.checksum", f"mismatch; manifest={expected}, actual={actual}")


def _validate_source(source: Any, root: Path, report: ValidationReport,
                     allow_synthetic: bool) -> tuple[str | None, date | None, date | None]:
    if not isinstance(source, dict):
        report.errors.append("sources: every entry must be an object")
        return None, None, None
    source_id = source.get("id")
    if not isinstance(source_id, str) or not source_id:
        report.errors.append("sources[].id: must be a non-empty string")
        return None, None, None
    for key in ("scope", "source_organization", "product", "dataset_identifier", "license",
                "access_date", "scene_date_range", "geographic_coverage", "crs", "resolution",
                "checksum", "local_path", "verification_status", "data_classification", "format"):
        if key not in source:
            _error(report, source_id, key, "field is required")
    scope = source.get("scope")
    if scope not in VALID_SCOPES:
        _error(report, source_id, "scope", f"must be one of {sorted(VALID_SCOPES)}")
    expected_scope = ("required_mvp" if source_id in REQUIRED_SOURCE_IDS else
                      "optional_mvp" if source_id in OPTIONAL_SOURCE_IDS else
                      "future_scope" if source_id in FUTURE_SOURCE_IDS else None)
    if expected_scope and scope != expected_scope:
        _error(report, source_id, "scope", f"authoritative inventory requires {expected_scope}")
    status = source.get("verification_status")
    strict = scope == "required_mvp" or status == "verified"
    for key in ("source_organization", "product", "dataset_identifier", "license", "geographic_coverage"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            message = f"{source_id}.{key}: must be a non-empty provenance value"
            (report.errors if strict else report.warnings).append(message)
    access = None
    if source.get("access_date") is None and not strict:
        report.warnings.append(f"{source_id}.access_date: record when this optional/future source is obtained")
    else:
        access = _parse_date(source.get("access_date"), source_id, "access_date", report)
    if access and access > date.today():
        _error(report, source_id, "access_date", "cannot be in the future")
    date_range = source.get("scene_date_range")
    start = end = None
    if not isinstance(date_range, dict):
        message = f"{source_id}.scene_date_range: must contain start and end ISO dates"
        (report.errors if strict else report.warnings).append(message)
    else:
        start = _parse_date(date_range.get("start"), source_id, "scene_date_range.start", report)
        end = _parse_date(date_range.get("end"), source_id, "scene_date_range.end", report)
        if start and end and start > end:
            _error(report, source_id, "scene_date_range", "start must be on or before end")
    declared_crs = None
    if source.get("crs") is None and not strict:
        report.warnings.append(f"{source_id}.crs: record the optional/future source CRS when obtained")
    else:
        declared_crs = _check_crs(source.get("crs"), source_id, report)
    resolution = None
    if source.get("resolution") is None and not strict:
        report.warnings.append(f"{source_id}.resolution: record the optional/future source resolution when obtained")
    else:
        resolution = _check_resolution(source.get("resolution"), source_id, report)
    if status not in VALID_STATUSES:
        _error(report, source_id, "verification_status", f"must be one of {sorted(VALID_STATUSES)}")
    classification = source.get("data_classification")
    if classification not in {"real", "synthetic_test_fixture"}:
        _error(report, source_id, "data_classification", "must be real or synthetic_test_fixture")
    elif classification == "synthetic_test_fixture" and not allow_synthetic:
        _error(report, source_id, "data_classification", "synthetic data is forbidden for production validation; use --allow-synthetic only in tests")

    local_path = _safe_local_path(root, source.get("local_path"), source_id, report)
    checksum = source.get("checksum")
    match = SHA256_RE.fullmatch(checksum) if isinstance(checksum, str) else None
    if not match:
        message = f"{source_id}.checksum: must be sha256:<64 lowercase hex characters>"
        (report.errors if strict else report.warnings).append(message)

    should_exist = scope == "required_mvp" or status == "verified"
    if local_path and not local_path.exists():
        message = f"missing {source.get('format', 'input')} at {source.get('local_path')}; obtain it and update provenance/checksum"
        if should_exist:
            _error(report, source_id, "local_path", message)
        else:
            report.warnings.append(f"{source_id}.local_path: optional/future input is absent at {source.get('local_path')}")
    elif local_path and local_path.exists():
        if match:
            try:
                actual = sha256_path(local_path)
                if actual != checksum:
                    _error(report, source_id, "checksum", f"mismatch; manifest={checksum}, actual={actual}")
            except (OSError, ValueError) as exc:
                _error(report, source_id, "checksum", f"cannot hash local content: {exc}")
        if status == "verified":
            _check_product_specific(source, local_path, start, end, declared_crs, resolution, report)
    if strict and source.get("companion_files"):
        _check_companions(source, root, report)
    if status != "verified" and scope == "required_mvp":
        _error(report, source_id, "verification_status", "required MVP source must be verified before processing")
    return source_id, start, end


def validate_manifest(manifest_path: Path, root: Path | None = None, *,
                      allow_synthetic: bool = False,
                      enforce_inventory: bool = True) -> ValidationReport:
    """Validate structure, provenance, files, checksums, CRS and season alignment."""
    report = ValidationReport()
    root = (root or manifest_path.resolve().parents[1]).resolve()
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.errors.append(f"manifest: file is missing: {manifest_path}")
        return report
    except (OSError, json.JSONDecodeError) as exc:
        report.errors.append(f"manifest: cannot parse JSON: {exc}")
        return report
    if not isinstance(document, dict):
        report.errors.append("manifest: top level must be an object")
        return report
    if document.get("manifest_version") != CONTRACT_VERSION:
        report.errors.append(f"manifest_version: must equal {CONTRACT_VERSION!r}")
    sources = document.get("sources")
    if not isinstance(sources, list):
        report.errors.append("sources: must be an array")
        return report
    seen: set[str] = set()
    seasons: dict[str, tuple[date | None, date | None]] = {}
    errors_before: dict[str, int] = {}
    for source in sources:
        candidate_id = source.get("id") if isinstance(source, dict) else "sources[]"
        errors_before[candidate_id] = len(report.errors)
        source_id, start, end = _validate_source(source, root, report, allow_synthetic)
        if source_id is None:
            continue
        if source_id in seen:
            _error(report, source_id, "id", "duplicate source id")
        seen.add(source_id)
        if source.get("season_group") == "peak_summer":
            seasons[source_id] = (start, end)
        if len(report.errors) == errors_before[candidate_id] and source.get("verification_status") == "verified":
            report.verified_sources.append(source_id)
    if enforce_inventory:
        missing = ALL_SOURCE_IDS - seen
        extra = seen - ALL_SOURCE_IDS
        for source_id in sorted(missing):
            report.errors.append(f"sources: authoritative inventory entry is missing: {source_id}")
        for source_id in sorted(extra):
            report.errors.append(f"sources: unknown source id (update the contract explicitly): {source_id}")
    usable_seasons = {value for value in seasons.values() if all(value)}
    if len(usable_seasons) > 1:
        details = ", ".join(f"{key}={value[0]}/{value[1]}" for key, value in sorted(seasons.items()))
        report.errors.append(f"season_group.peak_summer: date ranges must match exactly; {details}")
    for source_id, (start, end) in seasons.items():
        if start and end and not (start.month == 3 and start.day == 1 and end.month == 5 and end.day == 31 and start.year == end.year):
            _error(report, source_id, "scene_date_range", "peak_summer must be exactly YYYY-03-01 through YYYY-05-31")
    report.verified_sources.sort()
    return report
