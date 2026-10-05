"""Audit only the local March-May 2025 Landsat source files; produce no LST."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

import rasterio


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "landsat"
PROVENANCE = ROOT / "data" / "provenance"
REPORT = ROOT / "docs" / "landsat_quality_audit.md"
EXPECTED_IDS = (
    "LC08_L2SP_147047_20250302_20250311_02_T1",
    "LC09_L2SP_147047_20250310_20250311_02_T1",
    "LC08_L2SP_147047_20250318_20250327_02_T1",
    "LC09_L2SP_147047_20250326_20250327_02_T1",
    "LC08_L2SP_147047_20250403_20250411_02_T1",
    "LC09_L2SP_147047_20250411_20250412_02_T1",
    "LC08_L2SP_147047_20250419_20250425_02_T1",
    "LC09_L2SP_147047_20250427_20250428_02_T1",
    "LC08_L2SP_147047_20250505_20250512_02_T1",
)
SUFFIXES = ("MTL.txt", "ST_B10.TIF", "QA_PIXEL.TIF", "QA_RADSAT.TIF")
PRODUCT_PATTERN = re.compile(r"^(LC0[89])_(L2SP)_(\d{3})(\d{3})_(\d{8})_(\d{8})_(\d{2})_(T1)$")
FIELD_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_mtl(path: Path) -> dict[str, str]:
    """Keep first values because the MTL also embeds Level-1 product fields."""
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = FIELD_PATTERN.match(line)
        if match:
            fields.setdefault(match.group(1), match.group(2).strip('"'))
    return fields


def number(fields: dict[str, str], key: str, errors: list[str], *, positive: bool = False) -> float | None:
    raw = fields.get(key)
    try:
        value = float(raw) if raw is not None else math.nan
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or (positive and value <= 0):
        errors.append(f"Missing or invalid {key}: {raw!r}")
        return None
    return value


def audit_scene(directory: Path) -> dict:
    product_id = directory.name
    errors: list[str] = []
    match = PRODUCT_PATTERN.fullmatch(product_id)
    if not match:
        errors.append("Directory name is not a Landsat 8/9 L2SP Path 147 Row 047 Collection 02 Tier 1 product ID")
    if product_id not in EXPECTED_IDS:
        errors.append("Product ID is not among the nine selected scenes")

    files: dict[str, dict] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            errors.append(f"Unexpected nested directory: {path.name}")
            continue
        entry = {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": None}
        try:
            entry["sha256"] = sha256_file(path)
        except OSError as exc:
            errors.append(f"Cannot hash {path.name}: {exc}")
        files[path.name] = entry

    required = {suffix: f"{product_id}_{suffix}" in files for suffix in SUFFIXES}
    for suffix, present in required.items():
        if not present:
            errors.append(f"Missing required file: {product_id}_{suffix}")

    fields: dict[str, str] = {}
    if required["MTL.txt"]:
        try:
            fields = parse_mtl(directory / f"{product_id}_MTL.txt")
        except (OSError, UnicodeError) as exc:
            errors.append(f"Cannot read MTL: {exc}")

    for key, expected in (
        ("LANDSAT_PRODUCT_ID", product_id),
        ("PROCESSING_LEVEL", "L2SP"),
        ("COLLECTION_NUMBER", "02"),
        ("COLLECTION_CATEGORY", "T1"),
        ("WRS_PATH", "147"),
        ("WRS_ROW", "47"),
    ):
        if fields.get(key) != expected:
            errors.append(f"{key} is {fields.get(key)!r}; expected {expected!r}")

    satellite = {"LC08": "Landsat 8", "LC09": "Landsat 9"}.get(match.group(1)) if match else None
    spacecraft = {"LC08": "LANDSAT_8", "LC09": "LANDSAT_9"}.get(match.group(1)) if match else None
    if fields.get("SPACECRAFT_ID") != spacecraft:
        errors.append(f"SPACECRAFT_ID is {fields.get('SPACECRAFT_ID')!r}; expected {spacecraft!r}")

    acquisition_date = fields.get("DATE_ACQUIRED")
    try:
        parsed_date = date.fromisoformat(acquisition_date or "")
        if not date(2025, 3, 1) <= parsed_date <= date(2025, 5, 31):
            errors.append(f"DATE_ACQUIRED outside March-May 2025: {acquisition_date}")
        if match and parsed_date.strftime("%Y%m%d") != match.group(5):
            errors.append("DATE_ACQUIRED differs from product ID")
    except ValueError:
        errors.append(f"Missing or invalid DATE_ACQUIRED: {acquisition_date!r}")

    multiplier = number(fields, "TEMPERATURE_MULT_BAND_ST_B10", errors, positive=True)
    offset = number(fields, "TEMPERATURE_ADD_BAND_ST_B10", errors)
    cloud_cover = number(fields, "CLOUD_COVER", errors)
    if cloud_cover is not None and not 0 <= cloud_cover <= 100:
        errors.append(f"CLOUD_COVER outside 0-100%: {cloud_cover}")
    if cloud_cover is not None and cloud_cover > 10:
        errors.append(f"CLOUD_COVER exceeds selected-scene 10% ceiling: {cloud_cover}")

    rasters: dict[str, dict] = {}
    for suffix in SUFFIXES[1:]:
        if not required[suffix]:
            continue
        path = directory / f"{product_id}_{suffix}"
        try:
            with rasterio.open(path) as src:
                if src.driver != "GTiff":
                    errors.append(f"{suffix}: driver is {src.driver}, expected GTiff")
                if src.count != 1:
                    errors.append(f"{suffix}: band count is {src.count}, expected 1")
                if not src.crs:
                    errors.append(f"{suffix}: CRS missing")
                elif not src.crs.is_projected or src.crs.linear_units.lower() not in ("metre", "meter", "metres", "meters"):
                    errors.append(f"{suffix}: CRS is not projected in metres: {src.crs}")
                resolution = [abs(src.transform.a), abs(src.transform.e)]
                if not all(math.isclose(value, 30, abs_tol=1e-6) for value in resolution) or not math.isclose(src.transform.b, 0, abs_tol=1e-9) or not math.isclose(src.transform.d, 0, abs_tol=1e-9):
                    errors.append(f"{suffix}: pixel resolution/grid is not north-up 30 m: {resolution}")
                if src.width <= 0 or src.height <= 0:
                    errors.append(f"{suffix}: empty raster")
                # Decode every block so a valid header cannot mask damaged pixel data.
                for _, window in src.block_windows(1):
                    src.read(1, window=window)
                rasters[suffix] = {
                    "driver": src.driver, "crs": str(src.crs) if src.crs else None,
                    "resolution_m": resolution, "width": src.width, "height": src.height,
                    "transform": list(src.transform)[:6], "dtype": src.dtypes[0],
                }
        except Exception as exc:  # GDAL may raise several raster read/decode error types.
            errors.append(f"{suffix}: GeoTIFF unreadable: {exc}")

    if len(rasters) == 3:
        reference = rasters["ST_B10.TIF"]
        for suffix in SUFFIXES[2:]:
            raster = rasters[suffix]
            for key in ("width", "height", "crs", "transform"):
                if raster[key] != reference[key]:
                    errors.append(f"{suffix}: {key} differs from ST_B10.TIF")

    return {
        "product_id": product_id, "acquisition_date": acquisition_date,
        "satellite": satellite, "processing_level": fields.get("PROCESSING_LEVEL"),
        "collection_number": fields.get("COLLECTION_NUMBER"),
        "collection_category": fields.get("COLLECTION_CATEGORY"),
        "wrs_path": fields.get("WRS_PATH"), "wrs_row": fields.get("WRS_ROW"),
        "temperature_multiplier": multiplier, "temperature_offset": offset,
        "cloud_cover_percent": cloud_cover, "required_files": required,
        "files": files, "rasters": rasters, "status": "PASS" if not errors else "FAIL", "errors": errors,
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# Landsat source-quality audit: March-May 2025", "",
        "This report checks local source identity, required files, MTL calibration, GeoTIFF readability and grids, and SHA-256 integrity. It does not calculate municipal temperature or establish municipal coverage.", "",
        "| Date | Product ID | Satellite | Cloud Cover % | CRS | Resolution | Required Files | Validation Status |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for scene in result["scenes"]:
        rasters = scene["rasters"]
        st = rasters.get("ST_B10.TIF", {})
        crs = st.get("crs") or "Unavailable"
        resolution = st.get("resolution_m")
        resolution_text = f"{resolution[0]:g} × {resolution[1]:g} m" if resolution else "Unavailable"
        count = sum(scene["required_files"].values())
        cloud = scene["cloud_cover_percent"]
        cloud_text = f"{cloud:g}" if cloud is not None else "Unavailable"
        lines.append(f"| {scene['acquisition_date'] or 'Unavailable'} | `{scene['product_id']}` | {scene['satellite'] or 'Unavailable'} | {cloud_text} | {crs} | {resolution_text} | {count}/4 | {scene['status']} |")
    summary = result["summary"]
    lines += ["", "## Totals", ""]
    for label, key in (
        ("Total scenes expected", "scenes_expected"), ("Total scenes found", "scenes_found"),
        ("Total required files expected", "required_files_expected"),
        ("Total required files found", "required_files_found"),
        ("Scenes passed", "scenes_passed"), ("Scenes failed", "scenes_failed"),
        ("Overall", "overall_status"),
    ):
        lines.append(f"- {label}: **{summary[key]}**")
    failures = [scene for scene in result["scenes"] if scene["errors"]]
    if result["missing_product_ids"] or failures:
        lines += ["", "## Findings", ""]
        for product_id in result["missing_product_ids"]:
            lines.append(f"- Missing selected scene: `{product_id}`")
        for scene in failures:
            for error in scene["errors"]:
                lines.append(f"- `{scene['product_id']}`: {error}")
    lines += ["", "Per-file SHA-256 values and raster dimensions are in the JSON and CSV reports. Scene cloud cover is an MTL scene-wide value; pixel QA and municipal coverage still require evaluation during the real pipeline.", ""]
    return "\n".join(lines)


def main() -> int:
    if not SOURCE.is_dir():
        raise SystemExit(f"Landsat source directory missing: {SOURCE}")
    directories = sorted(path for path in SOURCE.iterdir() if path.is_dir())
    scenes = sorted((audit_scene(path) for path in directories), key=lambda scene: (scene["acquisition_date"] or "", scene["product_id"]))
    found_ids = {scene["product_id"] for scene in scenes}
    missing = sorted(set(EXPECTED_IDS) - found_ids)
    summary = {
        "scenes_expected": len(EXPECTED_IDS), "scenes_found": len(scenes),
        "required_files_expected": len(EXPECTED_IDS) * len(SUFFIXES),
        "required_files_found": sum(sum(scene["required_files"].values()) for scene in scenes),
        "scenes_passed": sum(scene["status"] == "PASS" for scene in scenes),
        "scenes_failed": sum(scene["status"] == "FAIL" for scene in scenes),
    }
    summary["overall_status"] = "PASS" if not missing and summary["scenes_found"] == summary["scenes_expected"] and summary["scenes_failed"] == 0 else "FAIL"
    result = {"audit_type": "source_integrity_only", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_directory": SOURCE.relative_to(ROOT).as_posix(), "expected_product_ids": list(EXPECTED_IDS),
              "missing_product_ids": missing, "summary": summary, "scenes": scenes}
    PROVENANCE.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    (PROVENANCE / "landsat_quality_audit_2025.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (PROVENANCE / "landsat_quality_audit_2025.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "product_id", "satellite", "cloud_cover_percent", "crs", "resolution_x_m", "resolution_y_m", "required_files_found", "required_files_expected", "validation_status", "errors", "file_name", "file_path", "file_bytes", "sha256"])
        writer.writeheader()
        for scene in scenes:
            st = scene["rasters"].get("ST_B10.TIF", {})
            resolution = st.get("resolution_m") or [None, None]
            for name, file in scene["files"].items():
                writer.writerow({"date": scene["acquisition_date"], "product_id": scene["product_id"], "satellite": scene["satellite"],
                                 "cloud_cover_percent": scene["cloud_cover_percent"], "crs": st.get("crs"),
                                 "resolution_x_m": resolution[0], "resolution_y_m": resolution[1],
                                 "required_files_found": sum(scene["required_files"].values()), "required_files_expected": len(SUFFIXES),
                                 "validation_status": scene["status"], "errors": "; ".join(scene["errors"]),
                                 "file_name": name, "file_path": file["path"], "file_bytes": file["bytes"], "sha256": file["sha256"]})
    REPORT.write_text(render_markdown(result), encoding="utf-8")
    print(f"Landsat source audit: {summary['overall_status']} ({summary['scenes_passed']}/{summary['scenes_expected']} scenes passed)")
    print(f"Reports: {PROVENANCE / 'landsat_quality_audit_2025.json'}, {PROVENANCE / 'landsat_quality_audit_2025.csv'}, {REPORT}")
    return 0 if summary["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
