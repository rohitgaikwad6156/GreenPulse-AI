"""Provenance-preserving point sensor ingestion and proximity context."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
VARIABLES = {"air_temperature_c", "relative_humidity_pct", "aqi"}
REQUIRED_COLUMNS = {"observation_id", "station_id", "timestamp_utc", "latitude", "longitude", "qa_status"}


class SensorEvidenceError(RuntimeError):
    """Sensor evidence is malformed, unverified, or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SensorEvidenceError(f"{field} must be a nonblank string")
    return value.strip()


def _sha(value: Any, field: str) -> str:
    result = _text(value, field).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise SensorEvidenceError(f"{field} must be a 64-character SHA-256")
    return result


def _utc(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SensorEvidenceError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SensorEvidenceError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name); json.dump(value, stream, indent=2); stream.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def peak_summer_scope(source_manifest: Path) -> dict:
    """Read the authoritative current Landsat period; multi-season is unsupported."""
    try:
        document = json.loads(Path(source_manifest).read_text(encoding="utf-8"))
        source = next(item for item in document["sources"] if item["id"] == "landsat_lst_scenes")
        period = source["scene_date_range"]
        start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    except (OSError, json.JSONDecodeError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise SensorEvidenceError("Cannot determine the current Landsat MVP temporal scope") from exc
    if source.get("season_group") != "peak_summer":
        raise SensorEvidenceError("The MVP source manifest must explicitly declare peak_summer")
    return {"season_group": "peak_summer", "start": start.isoformat(), "end": end.isoformat(),
            "multi_season_supported": False}


def _validate_manifest(document: dict, observations: Path) -> tuple[dict[str, dict], set[str]]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise SensorEvidenceError(f"schema_version must be {SCHEMA_VERSION}")
    for field in ("dataset_id", "dataset_version", "evidence_status", "observations_sha256"):
        _text(document.get(field), field)
    if document["evidence_status"] != "verified_point_observations":
        raise SensorEvidenceError("evidence_status must be verified_point_observations")
    if sha256_file(observations) != _sha(document["observations_sha256"], "observations_sha256"):
        raise SensorEvidenceError("Sensor observation checksum does not match the manifest")
    source = document.get("source")
    if not isinstance(source, dict):
        raise SensorEvidenceError("source provenance is required")
    for field in ("organization", "product", "url_or_identifier", "license", "access_date"):
        _text(source.get(field), f"source.{field}")
    try:
        accessed = date.fromisoformat(source["access_date"])
    except ValueError as exc:
        raise SensorEvidenceError("source.access_date must use YYYY-MM-DD") from exc
    if accessed > date.today():
        raise SensorEvidenceError("source.access_date cannot be in the future")
    variables = document.get("variables")
    if not isinstance(variables, list) or not variables or not set(variables) <= VARIABLES:
        raise SensorEvidenceError("variables must contain supported air temperature, humidity, or AQI fields")
    for field in ("freshness_threshold_hours", "temporal_match_tolerance_minutes"):
        value = document.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise SensorEvidenceError(f"{field} must be finite and nonnegative")
    minimum = document.get("minimum_station_count_for_context")
    if not isinstance(minimum, int) or minimum < 1:
        raise SensorEvidenceError("minimum_station_count_for_context must be a positive integer")
    stations = document.get("stations")
    if not isinstance(stations, list) or not stations:
        raise SensorEvidenceError("stations must be a nonempty array")
    indexed = {}
    for station in stations:
        station_id = _text(station.get("station_id"), "station_id")
        if station_id in indexed:
            raise SensorEvidenceError(f"Duplicate station_id: {station_id}")
        for field in ("provider_station_id", "instrument", "calibration_reference",
                      "measurement_height_m", "latitude", "longitude"):
            if field not in station:
                raise SensorEvidenceError(f"{station_id}: {field} is required")
        try:
            latitude = float(station["latitude"]); longitude = float(station["longitude"])
            height = float(station["measurement_height_m"])
        except (TypeError, ValueError) as exc:
            raise SensorEvidenceError(f"{station_id}: invalid coordinates or measurement height") from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and height >= 0):
            raise SensorEvidenceError(f"{station_id}: coordinates or measurement height are out of range")
        _text(station["provider_station_id"], f"{station_id}.provider_station_id")
        _text(station["instrument"], f"{station_id}.instrument")
        _text(station["calibration_reference"], f"{station_id}.calibration_reference")
        indexed[station_id] = {**station, "latitude": latitude, "longitude": longitude,
                               "measurement_height_m": height}
    return indexed, set(variables)


def import_sensor_observations(manifest_path: Path, observations_path: Path,
                               output_root: Path) -> Path:
    """Import verified point observations; never rasterize or interpolate them."""
    observations_path = Path(observations_path)
    try:
        document = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SensorEvidenceError(f"Cannot read sensor manifest: {manifest_path}") from exc
    if not observations_path.is_file():
        raise SensorEvidenceError(f"Sensor observations are missing: {observations_path}")
    stations, variables = _validate_manifest(document, observations_path)
    seen = set(); rows = []; latest = None
    with observations_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = sorted((REQUIRED_COLUMNS | variables) - set(reader.fieldnames or []))
        if missing:
            raise SensorEvidenceError(f"Sensor CSV is missing columns: {', '.join(missing)}")
        for line, raw in enumerate(reader, start=2):
            observation_id = _text(raw.get("observation_id"), f"row {line}.observation_id")
            if observation_id in seen:
                raise SensorEvidenceError(f"Duplicate observation_id: {observation_id}")
            station_id = raw.get("station_id")
            if station_id not in stations:
                raise SensorEvidenceError(f"row {line}: unknown station_id {station_id}")
            if raw.get("qa_status") != "valid":
                raise SensorEvidenceError(f"{observation_id}: only QA-valid observations may be imported")
            timestamp = _utc(raw.get("timestamp_utc"), f"{observation_id}.timestamp_utc")
            try:
                latitude = float(raw["latitude"]); longitude = float(raw["longitude"])
            except (TypeError, ValueError) as exc:
                raise SensorEvidenceError(f"{observation_id}: invalid coordinates") from exc
            station = stations[station_id]
            if abs(latitude - station["latitude"]) > 1e-6 or abs(longitude - station["longitude"]) > 1e-6:
                raise SensorEvidenceError(f"{observation_id}: coordinates do not match station provenance")
            values = {}
            for variable in variables:
                try:
                    value = float(raw[variable])
                except (TypeError, ValueError) as exc:
                    raise SensorEvidenceError(f"{observation_id}: {variable} must be numeric") from exc
                if not math.isfinite(value):
                    raise SensorEvidenceError(f"{observation_id}: {variable} must be finite")
                if variable == "relative_humidity_pct" and not 0 <= value <= 100:
                    raise SensorEvidenceError(f"{observation_id}: humidity must be within 0–100%")
                if variable == "air_temperature_c" and not -80 <= value <= 70:
                    raise SensorEvidenceError(f"{observation_id}: air temperature is outside the ingestion guard")
                if variable == "aqi" and value < 0:
                    raise SensorEvidenceError(f"{observation_id}: AQI must be nonnegative")
                values[variable] = value
            rows.append({"observation_id": observation_id, "station_id": station_id,
                         "timestamp_utc": timestamp.isoformat(), "latitude": latitude,
                         "longitude": longitude, **values})
            seen.add(observation_id); latest = timestamp if latest is None or timestamp > latest else latest
    if not rows:
        raise SensorEvidenceError("Sensor CSV contains no observations")
    dataset_id = document["dataset_id"]
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in dataset_id):
        raise SensorEvidenceError("dataset_id contains unsupported characters")
    destination = Path(output_root) / dataset_id
    if (destination / "manifest.json").is_file():
        existing = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        if (existing.get("dataset_version") == document["dataset_version"]
                and existing.get("observations_sha256") == document["observations_sha256"]):
            return destination
        raise SensorEvidenceError(f"Dataset ID {dataset_id} already exists with different evidence")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(observations_path, destination / "observations.csv")
    imported = {**document, "imported_at": datetime.now(timezone.utc).isoformat(),
                "observation_count": len(rows), "station_count": len(stations),
                "latest_observation_utc": latest.isoformat(),
                "spatial_representation": "verified_points_only_no_interpolation"}
    _atomic_json(destination / "manifest.json", imported)
    return destination


def _datasets(root: Path) -> list[tuple[dict, list[dict]]]:
    found = []
    if not Path(root).is_dir():
        return found
    for manifest_path in sorted(Path(root).glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            observations_path = manifest_path.with_name("observations.csv")
            if sha256_file(observations_path) != manifest["observations_sha256"]:
                continue
            rows = []
            with observations_path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    rows.append(row)
            found.append((manifest, rows))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return found


def sensor_status(root: Path, source_manifest: Path, *, reference_time: datetime | None = None) -> dict:
    scope = peak_summer_scope(source_manifest)
    datasets = _datasets(root)
    if not datasets:
        return {"status": "missing", "datasets": [], "station_count": 0,
                "observation_count": 0, "mvp_temporal_scope": scope,
                "wall_to_wall_interpolation": False,
                "message": "No verified point-sensor dataset is locally available."}
    now = (reference_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    summaries = []; statuses = []
    for manifest, rows in datasets:
        timestamps = [_utc(row["timestamp_utc"], "timestamp_utc") for row in rows]
        latest = max(timestamps); age_hours = (now - latest).total_seconds() / 3600
        scope_start = date.fromisoformat(scope["start"]); scope_end = date.fromisoformat(scope["end"])
        matched = sum(scope_start <= stamp.date() <= scope_end for stamp in timestamps)
        sparse = int(manifest["station_count"]) < int(manifest["minimum_station_count_for_context"])
        stale = age_hours > float(manifest["freshness_threshold_hours"])
        mismatch = matched == 0
        status = "temporally_mismatched" if mismatch else "stale" if stale else "sparse" if sparse else "available"
        statuses.append(status)
        summaries.append({"dataset_id": manifest["dataset_id"], "dataset_version": manifest["dataset_version"],
                          "status": status, "station_count": manifest["station_count"],
                          "observation_count": manifest["observation_count"],
                          "latest_observation_utc": latest.isoformat(), "age_hours": age_hours,
                          "observations_in_mvp_scope": matched, "variables": manifest["variables"],
                          "source": manifest["source"], "spatial_representation": manifest["spatial_representation"]})
    precedence = ("temporally_mismatched", "stale", "sparse", "available")
    overall = next(item for item in precedence if item in statuses)
    return {"status": overall, "datasets": summaries,
            "station_count": sum(item[0]["station_count"] for item in datasets),
            "observation_count": sum(item[0]["observation_count"] for item in datasets),
            "mvp_temporal_scope": scope, "wall_to_wall_interpolation": False,
            "message": "Point context only; observations are not interpolated or treated as wall-to-wall LST."}


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1; dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def nearby_sensor_context(root: Path, latitude: float, longitude: float,
                          timestamp_utc: datetime) -> dict:
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("latitude/longitude are out of range")
    candidates = []
    for manifest, rows in _datasets(root):
        tolerance = float(manifest["temporal_match_tolerance_minutes"])
        for row in rows:
            stamp = _utc(row["timestamp_utc"], "timestamp_utc")
            delta_minutes = abs((stamp - timestamp_utc.astimezone(timezone.utc)).total_seconds()) / 60
            candidates.append({"dataset_id": manifest["dataset_id"], "station_id": row["station_id"],
                               "timestamp_utc": stamp.isoformat(),
                               "distance_m": _distance_m(latitude, longitude, float(row["latitude"]), float(row["longitude"])),
                               "temporal_difference_minutes": delta_minutes,
                               "within_declared_temporal_tolerance": delta_minutes <= tolerance,
                               "values": {name: float(row[name]) for name in manifest["variables"]},
                               "source": manifest["source"]})
    if not candidates:
        return {"status": "missing", "nearest": None,
                "confidence": "unavailable_no_verified_point_observations",
                "interpretation": "No air-temperature, humidity, or AQI point context is available."}
    nearest = min(candidates, key=lambda item: (item["distance_m"], item["temporal_difference_minutes"]))
    return {"status": "matched" if nearest["within_declared_temporal_tolerance"] else "temporally_mismatched",
            "nearest": nearest, "confidence": "point_proximity_only_not_calibrated_for_lst",
            "interpretation": "Distance and time offset describe proximity only; they are not a calibrated LST confidence interval or citywide estimate."}
