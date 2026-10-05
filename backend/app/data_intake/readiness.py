"""Read-only evidence summary; never validates large rasters or changes source state."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from scripts.build_heat_map_pipeline import SOURCE_IDS
from .audit_viewer import audit_template, decorate_audit, evidence_chains, DISCLAIMER, UNCHANGED

ROOT = Path(__file__).resolve().parents[3]
DOCS = "https://github.com/rohitgaikwad6156/GreenPulse-AI/blob/main/docs/"
# Labels/actions describe the contract; statuses and counts come from JSON.
CATALOG = {
    "landsat_lst_scenes": ("Landsat 8/9 L2SP", "Observed LST target", "Review the source audits and investigate unusual full-scene clusters before accepting municipal results.", "landsat_quality_audit.md"),
    "sentinel2_l2a_scenes": ("Sentinel-2 L2A", "NDVI and NDBI features", "Download and extract the exact selected SAFE products, run the manual intake audit, then verify provenance and checksums.", "sentinel_quality_audit.md"),
    "municipal_boundary": ("Combined PMC/PCMC boundary", "Municipal clipping and analysis extent", "Obtain official PMC and PCMC outlines with authority, version and reuse evidence; import and verify their combined boundary.", "real_data_acquisition.md"),
    "esa_worldcover": ("ESA WorldCover", "Tree-cover and built-up fractions", "Retain the recorded land-cover vintage when interpreting results.", "real_heat_map_pipeline.md"),
    "osm_roads": ("OSM roads", "Road density", "Retain the extraction date and ODbL attribution.", "real_heat_map_pipeline.md"),
    "worldpop": ("WorldPop", "Population exposure; outside the first heat-map profile", "Align population exposure only after the real municipal reference grid is available.", "urban_morphology_pipeline.md"),
    "ward_boundaries": ("Verified ward GIS", "Reporting and ward UI only", "Obtain verified ward polygons and provenance for both corporations. Cell-level training does not require ward GIS.", "real_data_acquisition.md"),
    "osm_green_spaces": ("OSM green spaces", "Broader morphology and green-space distance", "Acquire a documented green-space extract with exterior coverage and provenance.", "urban_morphology_pipeline.md"),
    "periurban_lst_reference": ("Peri-urban LST reference", "Later Heat Hazard Score calibration", "Source an independent reference boundary and same-season QA-valid observations outside both municipalities.", "heat_hazard_score.md"),
}


def _json(root: Path, relative: str) -> dict | None:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _local(root: Path, relative) -> Path | None:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        return None
    try:
        if Path(relative).is_absolute():
            return None
        path = (root / relative).resolve()
        return path if path.is_relative_to(root.resolve()) and path != root.resolve() else None
    except (OSError, ValueError):
        return None


def _available(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        files = [path] if path.is_file() else list(path.rglob("*")) if path.is_dir() else []
        files = [p for p in files if p.is_file() and not p.name.startswith(".")]
        if not files:
            return False
        for file in files:
            size = file.stat().st_size
            if not size:
                return False
            # Never open source rasters. Tiny raster files cannot be real scenes.
            if file.suffix.lower() in {".tif", ".tiff", ".jp2"}:
                if size <= 1024:
                    return False
            elif size <= 1024:
                with file.open("rb") as stream:
                    if stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1"):
                        return False
        return True
    except OSError:
        return False


def _counts(document: dict, keys: tuple[str, ...]) -> bool:
    return all(type(document.get(k)) is int and document[k] >= 0 for k in keys)


def _audit(root: Path, filename: str, label: str, kind: str) -> dict:
    raw = _json(root, "data/provenance/" + filename)
    result = {**audit_template(kind), "label": label, "status": "unavailable", "recorded_at": None, "details": []}
    if not raw:
        return result
    data = raw.get("summary") if kind == "quality" else raw
    keys = {
        "quality": ("scenes_expected", "scenes_found", "required_files_expected", "required_files_found", "scenes_passed", "scenes_failed"),
        "processing": ("expected_scene_count", "scenes_processed", "scenes_passed", "scenes_failed"),
        "extreme": ("scenes_expected", "scenes_passed", "scenes_failed"),
        "sentinel": ("expected_product_count", "safe_directories_found", "minimum_required_files_expected", "required_file_slots_found", "products_passed", "products_failed"),
    }[kind]
    if not isinstance(data, dict) or not _counts(data, keys) or data.get("overall_status") not in ("PASS", "FAIL"):
        return result
    pairs = {
        "quality": [("scenes_found", "scenes_expected", "selected scenes"), ("required_files_found", "required_files_expected", "required files")],
        "processing": [("scenes_processed", "expected_scene_count", "scenes processed")],
        "extreme": [],
        "sentinel": [("safe_directories_found", "expected_product_count", "SAFE products present at audit"), ("required_file_slots_found", "minimum_required_files_expected", "required files")],
    }[kind]
    expected = data[keys[0]]
    passed, failed = data[keys[-2]], data[keys[-1]]
    if expected <= 0 or passed + failed != expected or any(data[a] > data[b] for a, b, _ in pairs):
        return result
    if data["overall_status"] == "PASS" and (passed != expected or failed or any(data[a] != data[b] for a, b, _ in pairs)):
        return result
    if data["overall_status"] == "FAIL" and failed == 0:
        return result
    if pairs and passed > data[pairs[0][0]]:
        return result
    if kind == "quality" and (data["required_files_expected"] != expected * 4 or not passed * 4 <= data["required_files_found"] <= data["scenes_found"] * 4):
        return result
    if kind == "sentinel" and (data["minimum_required_files_expected"] != expected * 5 or not passed * 5 <= data["required_file_slots_found"] <= data["safe_directories_found"] * 5):
        return result
    # Older count-only summaries are supported, but any supplied row evidence
    # must agree with the totals rather than silently contradicting a PASS.
    row_key = "products" if kind == "sentinel" else "scenes"
    status_key = "processing_status" if kind == "processing" else "status"
    if row_key in raw:
        records = raw[row_key]
        if not isinstance(records, list) or len(records) != expected:
            return result
        if not all(isinstance(r, dict) and r.get(status_key) in ("PASS", "FAIL") for r in records):
            return result
        if sum(r[status_key] == "PASS" for r in records) != passed:
            return result
    result.update(status=data["overall_status"].lower(), details=[f"{data[a]}/{data[b]} {label}" for a, b, label in pairs])
    stamp = raw.get("audited_at_utc")
    if isinstance(stamp, str):
        try:
            parsed = datetime.fromisoformat(stamp)
            if parsed.tzinfo is not None:
                result["recorded_at"] = parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    decorate_audit(result, raw, kind)
    return result


def readiness(root: Path | None = None) -> dict:
    root = root or ROOT
    manifest = _json(root, "data/source_manifest.json")
    records = manifest.get("sources") if manifest else None
    valid = isinstance(records, list) and all(isinstance(s, dict) and isinstance(s.get("id"), str) for s in records)
    valid = valid and len({s["id"] for s in records}) == len(records)
    by_id = {s["id"]: s for s in records} if valid else {}
    rows = []
    for source_id, (name, role, action, doc) in CATALOG.items():
        source = by_id.get(source_id, {})
        state = source.get("verification_status")
        recorded = state if isinstance(state, str) and state in {"verified", "pending", "rejected"} else None
        evidence = [f"Manifest verification: {recorded.upper()}."] if recorded else ["Evidence unavailable: manifest entry is missing or invalid."]
        verified = recorded == "verified" and source.get("data_classification") == "real" and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", str(source.get("checksum", ""))))
        present = _available(_local(root, source.get("local_path")))
        status = "verified" if verified else "pending" if recorded == "pending" else "blocked"
        reason = None if verified and present else "Source files are unavailable on this server (or only LFS pointers are present)." if verified else "Source verification is pending." if recorded == "pending" else "Evidence is unavailable, rejected, or inconsistent; readiness cannot be established."
        if verified:
            evidence.append("Source SHA-256 recorded; not recomputed by this page.")
        evidence.append("Local content present (lightweight check only)." if present else "Local content unavailable; saved audit counts may describe another checkout.")
        rows.append(dict(id=source_id, name=name, role=role, status=status, manifest_status=recorded,
                         local_available=present, evidence=evidence, audits=[], blocked_reason=reason,
                         next_action=action if not verified or present else "Place the verified source files on this server and rerun production preflight.",
                         scope="first_heat_map" if source_id in SOURCE_IDS else "later_stage",
                         documentation_url=DOCS + doc))
    by_row = {s["id"]: s for s in rows}
    for source_id, filename, label, kind in [
        ("landsat_lst_scenes", "landsat_quality_audit_2025.json", "Source audit", "quality"),
        ("landsat_lst_scenes", "landsat_processing_audit_2025.json", "Processing audit", "processing"),
        ("landsat_lst_scenes", "landsat_extreme_audit_2025.json", "Extreme diagnostics", "extreme"),
        ("sentinel2_l2a_scenes", "sentinel_quality_audit_2025.json", "Manual intake audit", "sentinel"),
    ]:
        audit = _audit(root, filename, label, kind)
        row = by_row[source_id]
        row["audits"].append(audit)
        if audit["status"] != "pass" and row["status"] == "verified":
            row["blocked_reason"] = "Recorded verification needs review: supporting audit is failed or unavailable."
            row["next_action"] = "Rerun the relevant source audit and review evidence before production preflight."
    combined = by_row["municipal_boundary"]
    # Individual outlines are staged evidence, never independent manifest verification.
    for municipality in ("PMC", "PCMC"):
        record = _json(root, f"data/provenance/acquisition_{municipality.lower()}_boundary.json")
        file = record.get("file") if record else None
        staged = isinstance(file, dict) and isinstance(record.get("source_organization"), str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", str(file.get("checksum", "")))) and _local(root, file.get("path")) is not None
        available = _available(_local(root, file.get("path"))) if staged else False
        status = "verified" if combined["status"] == "verified" else "staged" if staged else "pending"
        rows.append(dict(id=f"{municipality.lower()}_outline", name=f"{municipality} municipal boundary",
                         status=status, manifest_status=combined["manifest_status"], local_available=combined["local_available"] if status == "verified" else available,
                         scope="boundary_component", role="Component of the combined municipal clipping boundary",
                         evidence=["Covered by the verified combined-boundary manifest record."] if status == "verified" else ["Official acquisition provenance and source checksum recorded.", "Staged file present on this server." if available else "Staged file unavailable on this server."] if staged else ["Evidence unavailable: no official outline acquisition record is available."],
                         audits=[], blocked_reason=combined["blocked_reason"] if status == "verified" else "Individual staging does not verify the combined boundary.",
                         next_action="Use the verified combined boundary; rerun preflight before processing." if status == "verified" else "Confirm authority, effective date and reuse terms, then import and verify the combined PMC/PCMC outline." if staged else f"Obtain the official {municipality} outline with provenance and reuse terms.", documentation_url=DOCS + "real_data_acquisition.md"))
    required = []
    for source_id in sorted(SOURCE_IDS):
        row = by_row.get(source_id)
        required.append({"id": source_id, "name": row["name"] if row else source_id,
                         "ready": bool(row and row["status"] == "verified" and row["local_available"] and not row["blocked_reason"]),
                         "reason": row["blocked_reason"] if row else "Evidence unavailable: requirement has no readiness mapping."})
    blockers = [s for s in required if not s["ready"]]
    later = [{"name": r["name"], "status": r["status"], "detail": r["next_action"]} for r in rows if r["scope"] == "later_stage"]
    catalog = _json(root, "data/interventions/location_catalog.json")
    locations = catalog.get("locations") if catalog else None
    later.append({"name": "Intervention evidence", "status": "pending" if isinstance(locations, list) and not locations else "blocked",
                  "detail": "No planning locations recorded; verified capacity, costs and model-supported benefits are required." if isinstance(locations, list) and not locations else "Review the intervention catalog in the optimizer; presence alone does not validate planning evidence."})
    # Reuse the existing registered-evidence gate, without loading models or running analysis.
    from backend.app.validation.workflow import list_imported_datasets
    try:
        count = list_imported_datasets(root / "data/validation/imported")["total"]
        detail = f"{count} genuine imported datasets registered; statistical review and approval remain separate."
    except (OSError, ValueError, TypeError, KeyError):
        count, detail = 0, "Evidence unavailable: field-validation registry could not be read."
    later.append({"name": "Field validation", "status": "staged" if count else "pending", "detail": detail})
    audits = [a for row in rows for a in row["audits"]]
    trail = [{**a, "status": a["display_status"].lower()} for a in audits]
    chains = evidence_chains(rows, audits, _json(root, "data/provenance/discovery_2025.json") or {}, blockers)
    return {"audit_trail": trail, "evidence_chains": chains,
            "audit_disclaimer": DISCLAIMER, "audit_preservation_note": UNCHANGED,
            "overall_status": "blocked" if blockers else "verified", "first_heat_map_ready": not blockers,
            "required_sources_ready": len(required) - len(blockers), "required_sources_total": len(required),
            "required_sources": required, "first_heat_map_blockers": blockers, "sources": rows,
            "summary": dict(Counter(s["status"] for s in rows)), "later_stage_dependencies": later,
            "evidence_warnings": [] if valid else ["Evidence unavailable: source manifest is missing or malformed."],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "readiness_basis": "Manifest records, saved 2025 audits and lightweight local presence checks. This is not a checksum, raster, coverage or production preflight validation."}
