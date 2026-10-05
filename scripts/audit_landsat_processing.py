"""Non-production, full-scene Landsat L2SP decoding and calibration smoke test."""

from __future__ import annotations

import csv
import json
import math
import sys
from contextlib import ExitStack
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.landsat_lst import parse_mtl, qa_valid_mask  # noqa: E402
from scripts.audit_landsat_sources import EXPECTED_IDS  # noqa: E402

SOURCE = ROOT / "data" / "raw" / "landsat"
JSON_REPORT = ROOT / "data" / "provenance" / "landsat_processing_audit_2025.json"
CSV_REPORT = ROOT / "data" / "provenance" / "landsat_processing_audit_2025.csv"
MARKDOWN_REPORT = ROOT / "docs" / "landsat_processing_audit.md"
DISCLAIMER = (
    "These are full-scene source-processing diagnostics. They are not PMC/PCMC or Pune "
    "temperature results because the verified municipal boundary is not yet available."
)
SUFFIXES = ("ST_B10", "QA_PIXEL", "QA_RADSAT")


def _finite_calibration(fields: dict[str, str], key: str, *, positive: bool = False) -> float:
    try:
        value = float(fields[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Missing or invalid {key}") from exc
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"Non-finite or invalid {key}: {value}")
    return value


def _check_grid(datasets: dict[str, rasterio.io.DatasetReader]) -> tuple[int, int]:
    reference = datasets["ST_B10"]
    for suffix, dataset in datasets.items():
        if dataset.driver != "GTiff" or dataset.count != 1 or dataset.dtypes[0] != "uint16":
            raise ValueError(f"{suffix}: expected one-band uint16 GeoTIFF")
        if dataset.crs is None or not dataset.crs.is_projected or dataset.crs.linear_units.lower() not in ("metre", "meter", "metres", "meters"):
            raise ValueError(f"{suffix}: expected a projected CRS in metres")
        transform = dataset.transform
        if not (math.isclose(transform.a, 30, abs_tol=1e-6)
                and math.isclose(transform.e, -30, abs_tol=1e-6)
                and math.isclose(transform.b, 0, abs_tol=1e-9)
                and math.isclose(transform.d, 0, abs_tol=1e-9)):
            raise ValueError(f"{suffix}: expected a north-up 30 m grid")
        if dataset.width <= 0 or dataset.height <= 0:
            raise ValueError(f"{suffix}: empty raster")
        if (dataset.width, dataset.height, dataset.crs, dataset.transform) != (
            reference.width, reference.height, reference.crs, reference.transform
        ):
            raise ValueError(f"{suffix}: dimensions, CRS, or transform differ from ST_B10")
    return reference.width, reference.height


def _histogram_median(histogram: np.ndarray, count: int, multiplier: float, offset: float) -> float:
    cumulative = np.cumsum(histogram)
    lower = int(np.searchsorted(cumulative, (count - 1) // 2 + 1))
    upper = int(np.searchsorted(cumulative, count // 2 + 1))
    return float(((lower + upper) / 2) * multiplier + offset - 273.15)


def audit_scene(directory: Path, product_id: str) -> dict:
    """Process one original footprint in small windows, with no spatial clipping."""
    result = {
        "product_id": product_id, "acquisition_date": None, "satellite": None,
        "total_raster_pixels": None, "nonzero_st_pixels": None,
        "qa_valid_pixel_count": None, "qa_valid_percent": None,
        "finite_celsius_pixel_count": None, "minimum_celsius": None,
        "maximum_celsius": None, "mean_celsius": None, "median_celsius": None,
        "processing_status": "FAIL", "errors": [],
    }
    try:
        if directory.name != product_id or not directory.is_dir():
            raise ValueError(f"Selected scene directory missing: {directory}")
        metadata_path = directory / f"{product_id}_MTL.txt"
        fields = parse_mtl(metadata_path)
        if fields.get("LANDSAT_PRODUCT_ID") != product_id:
            raise ValueError("MTL LANDSAT_PRODUCT_ID differs from selected product ID")
        if fields.get("PROCESSING_LEVEL") != "L2SP" or fields.get("COLLECTION_NUMBER") != "02" or fields.get("COLLECTION_CATEGORY") != "T1":
            raise ValueError("MTL is not Collection 02 L2SP Tier 1")
        if fields.get("WRS_PATH") != "147" or fields.get("WRS_ROW") != "47":
            raise ValueError("MTL WRS Path/Row is not 147/047")
        satellite_code = product_id.split("_", 1)[0]
        spacecraft = {"LC08": ("LANDSAT_8", "Landsat 8"), "LC09": ("LANDSAT_9", "Landsat 9")}.get(satellite_code)
        if spacecraft is None or fields.get("SPACECRAFT_ID") != spacecraft[0]:
            raise ValueError("MTL spacecraft differs from selected Landsat 8/9 product")
        result["satellite"] = spacecraft[1]
        acquisition = date.fromisoformat(fields["DATE_ACQUIRED"])
        if not date(2025, 3, 1) <= acquisition <= date(2025, 5, 31) or acquisition.strftime("%Y%m%d") != product_id.split("_")[3]:
            raise ValueError("MTL acquisition date differs from selected March-May 2025 product")
        result["acquisition_date"] = acquisition.isoformat()
        multiplier = _finite_calibration(fields, "TEMPERATURE_MULT_BAND_ST_B10", positive=True)
        offset = _finite_calibration(fields, "TEMPERATURE_ADD_BAND_ST_B10")

        with ExitStack() as stack:
            datasets = {
                suffix: stack.enter_context(rasterio.open(directory / f"{product_id}_{suffix}.TIF"))
                for suffix in SUFFIXES
            }
            width, height = _check_grid(datasets)
            total = width * height
            result["total_raster_pixels"] = total
            nonzero = 0
            valid_count = 0
            finite_count = 0
            minimum = math.inf
            maximum = -math.inf
            celsius_sum = 0.0
            dn_histogram = np.zeros(65536, dtype=np.int64)
            for _, window in datasets["ST_B10"].block_windows(1):
                dn = datasets["ST_B10"].read(1, window=window)
                qa_pixel = datasets["QA_PIXEL"].read(1, window=window)
                qa_radsat = datasets["QA_RADSAT"].read(1, window=window)
                nonzero += int(np.count_nonzero(dn))
                valid = qa_valid_mask(dn, qa_pixel, qa_radsat)
                if valid.shape != dn.shape or np.any(valid & (dn == 0)):
                    raise ValueError("QA mask accepted invalid source pixels")
                valid_dn = dn[valid]
                count = int(valid_dn.size)
                valid_count += count
                if count == 0:
                    continue
                # Calibration is applied only to QA-valid source DNs. No clipping.
                celsius = valid_dn.astype(np.float64) * multiplier + offset - 273.15
                if not np.all(np.isfinite(celsius)):
                    raise ValueError("NaN or infinity among QA-valid Celsius values")
                finite_count += int(np.count_nonzero(np.isfinite(celsius)))
                minimum = min(minimum, float(celsius.min()))
                maximum = max(maximum, float(celsius.max()))
                celsius_sum += float(celsius.sum(dtype=np.float64))
                dn_histogram += np.bincount(valid_dn, minlength=65536)

        result["nonzero_st_pixels"] = nonzero
        result["qa_valid_pixel_count"] = valid_count
        result["qa_valid_percent"] = float(100 * valid_count / total)
        result["finite_celsius_pixel_count"] = finite_count
        if valid_count == 0 or finite_count != valid_count or int(dn_histogram.sum()) != valid_count:
            raise ValueError("No QA-valid pixels or Celsius/count mismatch")
        result["minimum_celsius"] = minimum
        result["maximum_celsius"] = maximum
        result["mean_celsius"] = float(celsius_sum / valid_count)
        result["median_celsius"] = _histogram_median(dn_histogram, valid_count, multiplier, offset)
        if not all(math.isfinite(result[key]) for key in ("minimum_celsius", "maximum_celsius", "mean_celsius", "median_celsius")):
            raise ValueError("Non-finite reported Celsius statistic")
        result["processing_status"] = "PASS"
    except (OSError, ValueError, KeyError, rasterio.errors.RasterioError) as exc:
        result["errors"].append(str(exc))
    return result


def run_audit(source: Path = SOURCE, expected_ids: tuple[str, ...] = EXPECTED_IDS) -> dict:
    scenes = [audit_scene(source / product_id, product_id) for product_id in expected_ids]
    unexpected = sorted(path.name for path in source.iterdir() if path.is_dir() and path.name not in expected_ids) if source.is_dir() else []
    passed = sum(scene["processing_status"] == "PASS" for scene in scenes)
    return {
        "audit_type": "non_production_full_scene_source_processing_diagnostic",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "disclaimer": DISCLAIMER, "source_directory": str(source),
        "expected_scene_count": len(expected_ids),
        "scenes_processed": sum(scene["total_raster_pixels"] is not None for scene in scenes),
        "scenes_passed": passed, "scenes_failed": len(scenes) - passed,
        "unexpected_scene_directories": unexpected,
        "overall_status": "PASS" if passed == len(expected_ids) and not unexpected else "FAIL",
        "scenes": scenes,
    }


def _display(value: object, decimals: int = 2) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def render_markdown(result: dict) -> str:
    lines = ["# Landsat processing smoke test: March-May 2025", "", DISCLAIMER, "",
             "The figures below use QA-valid pixels over each original scene footprint. No municipal crop or production raster was created.", "",
             "| Date | Product ID | Satellite | Total pixels | Nonzero ST | QA-valid pixels | QA-valid % | Finite Celsius | Min °C | Max °C | Mean °C | Median °C | Status |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for scene in result["scenes"]:
        columns = [scene["acquisition_date"] or "Unavailable", f"`{scene['product_id']}`", scene["satellite"] or "Unavailable",
                   _display(scene["total_raster_pixels"]), _display(scene["nonzero_st_pixels"]),
                   _display(scene["qa_valid_pixel_count"]), _display(scene["qa_valid_percent"], 4),
                   _display(scene["finite_celsius_pixel_count"]), _display(scene["minimum_celsius"]),
                   _display(scene["maximum_celsius"]), _display(scene["mean_celsius"]),
                   _display(scene["median_celsius"]), scene["processing_status"]]
        lines.append("| " + " | ".join(columns) + " |")
    lines += ["", "## Summary", "",
              f"- Expected scenes: **{result['expected_scene_count']}**",
              f"- Scenes processed: **{result['scenes_processed']}**",
              f"- Scenes passed: **{result['scenes_passed']}**",
              f"- Scenes failed: **{result['scenes_failed']}**",
              f"- Overall: **{result['overall_status']}**", ""]
    findings = [f"Unexpected scene directory: `{name}`" for name in result["unexpected_scene_directories"]]
    findings += [f"`{scene['product_id']}`: {error}" for scene in result["scenes"] for error in scene["errors"]]
    if findings:
        lines += ["## Failures for investigation", ""] + [f"- {finding}" for finding in findings] + [""]
    passed = [scene for scene in result["scenes"] if scene["processing_status"] == "PASS"]
    if passed:
        coldest = min(passed, key=lambda scene: scene["minimum_celsius"])
        hottest = max(passed, key=lambda scene: scene["maximum_celsius"])
        lines += ["## Observed full-scene extremes for review", "",
                  f"- Lowest QA-valid Celsius value: **{coldest['minimum_celsius']:.2f} °C** in `{coldest['product_id']}`.",
                  f"- Highest QA-valid Celsius value: **{hottest['maximum_celsius']:.2f} °C** in `{hottest['product_id']}`.",
                  "- These extremes are preserved without clipping or extra QA rules. Their location and cause have not been established.", ""]
    lines += ["No temperature range filter was applied. A PASS means the source files decoded, matched grids, and yielded finite QA-valid values; it does not verify municipal coverage or support a city temperature claim.", ""]
    return "\n".join(lines)


def write_reports(result: dict, json_path: Path = JSON_REPORT, csv_path: Path = CSV_REPORT, markdown_path: Path = MARKDOWN_REPORT) -> None:
    for path in (json_path, csv_path, markdown_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    fieldnames = ["product_id", "acquisition_date", "satellite", "total_raster_pixels", "nonzero_st_pixels",
                  "qa_valid_pixel_count", "qa_valid_percent", "finite_celsius_pixel_count", "minimum_celsius",
                  "maximum_celsius", "mean_celsius", "median_celsius", "processing_status", "errors"]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for scene in result["scenes"]:
            writer.writerow({**scene, "errors": "; ".join(scene["errors"])})
    markdown_path.write_text(render_markdown(result), encoding="utf-8")


def main() -> int:
    result = run_audit()
    write_reports(result)
    print(f"Landsat processing smoke test: {result['overall_status']} ({result['scenes_passed']}/{result['expected_scene_count']} passed)")
    print(f"Reports: {JSON_REPORT}, {CSV_REPORT}, {MARKDOWN_REPORT}")
    return 0 if result["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
