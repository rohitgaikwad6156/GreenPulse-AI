"""Versioned, evidence-gated intervention catalogs for named planning areas."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
ALLOWED_EVIDENCE = {
    "municipal_tender", "schedule_of_rates", "published_study",
    "audited_user_input", "validated_model", "verified_spatial_capacity",
}
REQUIRED_SOURCE_FIELDS = {
    "source_id", "organization", "title", "url_or_identifier", "license",
    "access_date", "evidence_type", "checksum_sha256", "local_path",
}
REQUIRED_ACTION_FIELDS = {
    "location_id", "intervention_id", "name", "unit_type", "block_size",
    "capital_cost_inr", "annual_maintenance_inr", "ground_area_required_m2",
    "roof_area_required_m2", "maximum_feasible_units",
    "modeled_marginal_cooling_c", "green_cover_gain_m2",
    "co_benefit_score_0_5", "horizon", "uncertainty", "source_ids",
    "field_source_ids",
    "evidence_status", "model_dataset_version", "model_checksum_sha256",
}


class CatalogEvidenceError(RuntimeError):
    """A catalog cannot support a defensible planning run."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: Any, field: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CatalogEvidenceError(f"{field} must be a finite number") from exc
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        qualifier = "positive" if positive else "nonnegative"
        raise CatalogEvidenceError(f"{field} must be a finite {qualifier} number")
    return result


def _integer(value: Any, field: str, *, positive: bool = False) -> int:
    result = _number(value, field, positive=positive)
    if not result.is_integer():
        raise CatalogEvidenceError(f"{field} must be an integer")
    return int(result)


def _iso_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise CatalogEvidenceError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogEvidenceError(f"{field} must be a nonblank string")
    return value.strip()


def _validate_source(source: dict, *, root: Path, today: date) -> dict:
    missing = sorted(REQUIRED_SOURCE_FIELDS - set(source))
    if missing:
        raise CatalogEvidenceError(f"source is missing fields: {', '.join(missing)}")
    source_id = _text(source["source_id"], "source.source_id")
    if source["evidence_type"] not in ALLOWED_EVIDENCE:
        raise CatalogEvidenceError(f"{source_id}: unsupported evidence_type")
    for field in ("organization", "title", "url_or_identifier", "license"):
        _text(source[field], f"{source_id}.{field}")
    access_date = _iso_date(source["access_date"], f"{source_id}.access_date")
    if access_date > today:
        raise CatalogEvidenceError(f"{source_id}: access_date cannot be in the future")
    valid_until = source.get("valid_until")
    if not valid_until:
        raise CatalogEvidenceError(f"{source_id}: valid_until is required for stale-evidence checks")
    if _iso_date(valid_until, f"{source_id}.valid_until") < today:
        raise CatalogEvidenceError(f"{source_id}: evidence expired on {valid_until}")
    checksum = _text(source["checksum_sha256"], f"{source_id}.checksum_sha256").lower()
    if len(checksum) != 64 or any(ch not in "0123456789abcdef" for ch in checksum):
        raise CatalogEvidenceError(f"{source_id}: checksum_sha256 must contain 64 lowercase hex characters")
    local_path = _text(source["local_path"], f"{source_id}.local_path")
    candidate = (root / local_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise CatalogEvidenceError(f"{source_id}: local_path escapes the project root") from exc
    if not candidate.is_file():
        raise CatalogEvidenceError(f"{source_id}: evidence file is missing: {local_path}")
    if sha256_file(candidate) != checksum:
        raise CatalogEvidenceError(f"{source_id}: evidence checksum does not match {local_path}")
    return {**source, "source_id": source_id, "checksum_sha256": checksum,
            "local_path": local_path}


def _validate_action(action: dict, *, location_id: str, sources: dict[str, dict],
                     catalog_model_version: str | None,
                     catalog_model_checksum: str | None) -> dict | None:
    status = action.get("availability")
    if status == "unavailable":
        _text(action.get("intervention_id"), "unavailable intervention_id")
        _text(action.get("unavailable_reason"), "unavailable_reason")
        return None
    if status != "available":
        raise CatalogEvidenceError("Each action must set availability to available or unavailable")
    missing = sorted(REQUIRED_ACTION_FIELDS - set(action))
    if missing:
        raise CatalogEvidenceError(f"available action is missing fields: {', '.join(missing)}")
    action_id = _text(action["intervention_id"], "action.intervention_id")
    if action.get("location_id") != location_id:
        raise CatalogEvidenceError(f"{action_id}: mixed-location row; expected {location_id}")
    evidence_status = action.get("evidence_status")
    if evidence_status not in {"verified", "audited"}:
        raise CatalogEvidenceError(f"{action_id}: evidence_status must be verified or audited")
    source_ids = action.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids or any(item not in sources for item in source_ids):
        raise CatalogEvidenceError(f"{action_id}: every source_id must reference a verified catalog source")
    field_sources = action.get("field_source_ids")
    required_mappings = {
        "capital_cost", "annual_maintenance", "block_and_area", "maximum_feasible_units",
        "modeled_marginal_cooling", "green_cover_gain", "co_benefit", "horizon", "uncertainty",
    }
    if not isinstance(field_sources, dict) or set(field_sources) != required_mappings:
        raise CatalogEvidenceError(f"{action_id}: field_source_ids must map every evidence-bearing field")
    for field, identifiers in field_sources.items():
        if (not isinstance(identifiers, list) or not identifiers
                or any(identifier not in source_ids for identifier in identifiers)):
            raise CatalogEvidenceError(f"{action_id}: {field} must reference listed verified sources")
    cost_types = {sources[item]["evidence_type"] for field in
                  ("capital_cost", "annual_maintenance") for item in field_sources[field]}
    if not ({"municipal_tender", "schedule_of_rates", "published_study", "audited_user_input"} & cost_types):
        raise CatalogEvidenceError(f"{action_id}: cost evidence must be a tender, schedule of rates, or audited user input")
    capacity_types = {sources[item]["evidence_type"] for field in
                      ("block_and_area", "maximum_feasible_units") for item in field_sources[field]}
    if "verified_spatial_capacity" not in capacity_types:
        raise CatalogEvidenceError(f"{action_id}: verified spatial-capacity evidence is required")
    cooling_types = {sources[item]["evidence_type"]
                     for item in field_sources["modeled_marginal_cooling"]}
    if not ({"validated_model", "published_study"} & cooling_types):
        raise CatalogEvidenceError(f"{action_id}: modeled cooling needs validated-model or published-study evidence")
    clean = {**action}
    for field in ("name", "unit_type", "horizon"):
        clean[field] = _text(action[field], f"{action_id}.{field}")
    clean["block_size"] = _number(action["block_size"], f"{action_id}.block_size", positive=True)
    for field in ("capital_cost_inr", "annual_maintenance_inr"):
        clean[field] = _integer(action[field], f"{action_id}.{field}", positive=field == "capital_cost_inr")
    for field in ("ground_area_required_m2", "roof_area_required_m2",
                  "modeled_marginal_cooling_c", "green_cover_gain_m2"):
        clean[field] = _number(action[field], f"{action_id}.{field}")
    if clean["ground_area_required_m2"] + clean["roof_area_required_m2"] <= 0:
        raise CatalogEvidenceError(f"{action_id}: each block must use verified ground or roof area")
    clean["maximum_feasible_units"] = _integer(
        action["maximum_feasible_units"], f"{action_id}.maximum_feasible_units")
    clean["co_benefit_score_0_5"] = _number(
        action["co_benefit_score_0_5"], f"{action_id}.co_benefit_score_0_5")
    if clean["co_benefit_score_0_5"] > 5:
        raise CatalogEvidenceError(f"{action_id}: co-benefit score must be within 0–5")
    uncertainty = action["uncertainty"]
    if not isinstance(uncertainty, dict) or uncertainty.get("status") not in {
            "empirically_validated", "uncalibrated_proxy"}:
        raise CatalogEvidenceError(f"{action_id}: uncertainty status is missing or unsupported")
    _text(uncertainty.get("description"), f"{action_id}.uncertainty.description")
    if action_id in {"street_trees", "cool_roofs"}:
        if not catalog_model_version or not catalog_model_checksum:
            raise CatalogEvidenceError(f"{action_id}: catalog model identity is required")
        if (action["model_dataset_version"] != catalog_model_version
                or action["model_checksum_sha256"] != catalog_model_checksum):
            raise CatalogEvidenceError(f"{action_id}: stale or mismatched scenario-model provenance")
        model_sources = [sources[item] for item in field_sources["modeled_marginal_cooling"]
                         if sources[item]["evidence_type"] == "validated_model"]
        if model_sources and all(item["checksum_sha256"] != catalog_model_checksum
                                 for item in model_sources):
            raise CatalogEvidenceError(f"{action_id}: validated model source checksum is stale or mismatched")
    return clean


def load_location_catalog(path: Path, *, project_root: Path | None = None,
                          today: date | None = None) -> dict:
    """Load and verify a location catalog, including local evidence hashes."""
    path = Path(path)
    if not path.is_file():
        raise CatalogEvidenceError(f"Location intervention catalog is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogEvidenceError(f"Cannot read location intervention catalog: {path}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise CatalogEvidenceError(f"Catalog schema_version must be {SCHEMA_VERSION}")
    _text(document.get("catalog_version"), "catalog_version")
    try:
        datetime.fromisoformat(str(document.get("generated_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogEvidenceError("generated_at must be an ISO timestamp") from exc
    root = Path(project_root) if project_root else path.resolve().parents[2]
    check_date = today or date.today()
    raw_sources = document.get("sources")
    raw_locations = document.get("locations")
    if not isinstance(raw_sources, list) or not isinstance(raw_locations, list):
        raise CatalogEvidenceError("Catalog sources and locations must be arrays")
    sources: dict[str, dict] = {}
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise CatalogEvidenceError("Each source must be an object")
        clean = _validate_source(raw, root=root, today=check_date)
        if clean["source_id"] in sources:
            raise CatalogEvidenceError(f"Duplicate source_id: {clean['source_id']}")
        sources[clean["source_id"]] = clean
    locations = []
    location_ids = set()
    for raw in raw_locations:
        if not isinstance(raw, dict):
            raise CatalogEvidenceError("Each location must be an object")
        location_id = _text(raw.get("location_id"), "location.location_id")
        if location_id in location_ids:
            raise CatalogEvidenceError(f"Duplicate location_id: {location_id}")
        location_ids.add(location_id)
        name = _text(raw.get("name"), f"{location_id}.name")
        if raw.get("crs") != "EPSG:32643":
            raise CatalogEvidenceError(f"{location_id}: crs must be EPSG:32643")
        source_ids = raw.get("capacity_source_ids")
        if (not isinstance(source_ids, list) or not source_ids
                or any(item not in sources for item in source_ids)
                or any(sources[item]["evidence_type"] != "verified_spatial_capacity"
                       for item in source_ids)):
            raise CatalogEvidenceError(f"{location_id}: verified capacity_source_ids are required")
        capacity = raw.get("capacity")
        if not isinstance(capacity, dict) or capacity.get("status") != "verified_spatial_inputs":
            raise CatalogEvidenceError(f"{location_id}: capacity must come from verified spatial inputs")
        ground = _number(capacity.get("eligible_ground_m2"), f"{location_id}.eligible_ground_m2")
        roof = _number(capacity.get("eligible_roof_m2"), f"{location_id}.eligible_roof_m2")
        actions = raw.get("actions")
        if not isinstance(actions, list):
            raise CatalogEvidenceError(f"{location_id}: actions must be an array")
        enabled = []
        action_ids = set()
        for action in actions:
            if not isinstance(action, dict):
                raise CatalogEvidenceError(f"{location_id}: each action must be an object")
            action_id = _text(action.get("intervention_id"), "action.intervention_id")
            if action_id in action_ids:
                raise CatalogEvidenceError(f"{location_id}: duplicate intervention_id {action_id}")
            action_ids.add(action_id)
            clean = _validate_action(
                action, location_id=location_id, sources=sources,
                catalog_model_version=document.get("model_dataset_version"),
                catalog_model_checksum=document.get("model_checksum_sha256"))
            if clean is not None:
                capacity_limits = []
                if clean["ground_area_required_m2"] > 0:
                    capacity_limits.append(math.floor(ground / clean["ground_area_required_m2"]))
                if clean["roof_area_required_m2"] > 0:
                    capacity_limits.append(math.floor(roof / clean["roof_area_required_m2"]))
                if (capacity_limits and clean["maximum_feasible_units"] > min(capacity_limits)):
                    raise CatalogEvidenceError(
                        f"{action_id}: maximum_feasible_units exceeds verified spatial capacity")
                enabled.append(clean)
        locations.append({**raw, "location_id": location_id, "name": name,
                          "capacity": {**capacity, "eligible_ground_m2": ground,
                                       "eligible_roof_m2": roof},
                          "enabled_actions": enabled,
                          "planning_available": bool(enabled)})
    return {**document, "verified_sources": sources, "verified_locations": locations}


def list_planning_locations(path: Path, *, project_root: Path | None = None) -> dict:
    document = load_location_catalog(path, project_root=project_root)
    locations = [{
        "location_id": item["location_id"], "name": item["name"], "crs": item["crs"],
        "eligible_ground_m2": item["capacity"]["eligible_ground_m2"],
        "eligible_roof_m2": item["capacity"]["eligible_roof_m2"],
        "available_interventions": len(item["enabled_actions"]),
        "planning_available": item["planning_available"],
        "capacity_status": item["capacity"]["status"],
    } for item in document["verified_locations"] if item["planning_available"]]
    return {"catalog_version": document["catalog_version"], "locations": locations,
            "total": len(locations), "blockers": document.get("blockers", [])}


def actions_for_location(path: Path, location_id: str,
                         *, project_root: Path | None = None) -> tuple[dict, list[dict]]:
    document = load_location_catalog(path, project_root=project_root)
    location = next((item for item in document["verified_locations"]
                     if item["location_id"] == location_id), None)
    if location is None or not location["planning_available"]:
        raise CatalogEvidenceError(
            f"No evidence-complete intervention catalog is available for location: {location_id}")
    return location, location["enabled_actions"]
