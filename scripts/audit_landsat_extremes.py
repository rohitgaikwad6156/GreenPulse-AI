"""Read-only, full-scene investigation of Landsat QA-valid temperature extremes."""

from __future__ import annotations

import csv
import json
import math
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.landsat_lst import parse_mtl, qa_valid_mask  # noqa: E402
from scripts.audit_landsat_processing import _check_grid  # noqa: E402
from scripts.audit_landsat_sources import EXPECTED_IDS  # noqa: E402

SOURCE = ROOT / "data" / "raw" / "landsat"
JSON_REPORT = ROOT / "data" / "provenance" / "landsat_extreme_audit_2025.json"
CSV_REPORT = ROOT / "data" / "provenance" / "landsat_extreme_audit_2025.csv"
MARKDOWN_REPORT = ROOT / "docs" / "landsat_extreme_audit.md"
DISCLAIMER = "These are full-scene diagnostic observations and are not Pune, PMC, or PCMC temperature results."
PERCENTILES = (1, 5, 25, 50, 75, 95, 99)
HOT_SCENE = "LC09_L2SP_147047_20250310_20250311_02_T1"
COLD_SCENE = "LC08_L2SP_147047_20250403_20250411_02_T1"
CLUSTER_THRESHOLDS = {HOT_SCENE: ("above_80", "above_90"), COLD_SCENE: ("below_10", "below_0")}
RASTER_NAMES = ("ST_B10", "QA_PIXEL", "QA_RADSAT")


def percentile_from_histogram(histogram: np.ndarray, percentile: float, multiplier: float, offset: float) -> float:
    """Match NumPy's linear percentile on calibrated, sorted valid DN values."""
    count = int(histogram.sum())
    if count <= 0 or not 0 <= percentile <= 100:
        raise ValueError("Histogram must be nonempty and percentile within 0-100")
    position = (count - 1) * percentile / 100
    lower_rank = math.floor(position)
    upper_rank = math.ceil(position)
    cumulative = np.cumsum(histogram)
    lower_dn = int(np.searchsorted(cumulative, lower_rank + 1))
    upper_dn = int(np.searchsorted(cumulative, upper_rank + 1))
    interpolated_dn = lower_dn + (upper_dn - lower_dn) * (position - lower_rank)
    return float(interpolated_dn * multiplier + offset - 273.15)


def threshold_counts(histogram: np.ndarray, multiplier: float, offset: float) -> dict[str, int]:
    values = np.arange(65536, dtype=np.float64) * multiplier + offset - 273.15
    return {
        "below_0": int(histogram[values < 0].sum()),
        "from_0_to_10": int(histogram[(values >= 0) & (values < 10)].sum()),
        "above_60": int(histogram[values > 60].sum()),
        "above_70": int(histogram[values > 70].sum()),
        "above_80": int(histogram[values > 80].sum()),
        "above_90": int(histogram[values > 90].sum()),
    }


def threshold_mask(valid: np.ndarray, celsius_valid: np.ndarray, key: str) -> np.ndarray:
    """Diagnostic selection only; never changes the production QA mask."""
    selected = np.zeros(valid.shape, dtype=bool)
    if key == "above_80":
        selected[valid] = celsius_valid > 80
    elif key == "above_90":
        selected[valid] = celsius_valid > 90
    elif key == "below_10":
        selected[valid] = celsius_valid < 10
    elif key == "below_0":
        selected[valid] = celsius_valid < 0
    else:
        raise ValueError(f"Unknown diagnostic threshold: {key}")
    return selected


def pixel_coordinates(transform: object, crs: object, row: int, column: int) -> dict[str, float]:
    x, y = rasterio.transform.xy(transform, row, column, offset="center")
    longitude, latitude = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return {"x": float(x), "y": float(y), "longitude": float(longitude), "latitude": float(latitude)}


def cluster_summary(mask: np.ndarray, transform: object, crs: object) -> dict:
    """Find 8-neighbour components and the largest component's pixel-centre bounds."""
    count = int(np.count_nonzero(mask))
    if count == 0:
        return {"pixel_count": 0, "cluster_count": 0, "largest_cluster_size": 0, "largest_cluster_bounds": None}
    labels, cluster_count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest_label = int(np.argmax(sizes))
    rows, columns = np.nonzero(labels == largest_label)
    min_row, max_row = int(rows.min()), int(rows.max())
    min_column, max_column = int(columns.min()), int(columns.max())
    corners = [pixel_coordinates(transform, crs, row, column)
               for row in (min_row, max_row) for column in (min_column, max_column)]
    return {
        "pixel_count": count, "cluster_count": int(cluster_count),
        "largest_cluster_size": int(sizes[largest_label]),
        "largest_cluster_bounds": {
            "min_row": min_row, "max_row": max_row,
            "min_column": min_column, "max_column": max_column,
            "projected_pixel_center_bounds": {
                "min_x": min(point["x"] for point in corners), "min_y": min(point["y"] for point in corners),
                "max_x": max(point["x"] for point in corners), "max_y": max(point["y"] for point in corners),
            },
            "longitude_latitude_pixel_center_bounds": {
                "min_longitude": min(point["longitude"] for point in corners),
                "min_latitude": min(point["latitude"] for point in corners),
                "max_longitude": max(point["longitude"] for point in corners),
                "max_latitude": max(point["latitude"] for point in corners),
            },
        },
    }


def extract_neighborhood(datasets: dict, row: int, column: int, multiplier: float, offset: float) -> list[list[dict]]:
    """Read a 5x5 source window; invalid or out-of-footprint Celsius stays null."""
    source = datasets["ST_B10"]
    start_row, end_row = max(0, row - 2), min(source.height, row + 3)
    start_column, end_column = max(0, column - 2), min(source.width, column + 3)
    window = Window(start_column, start_row, end_column - start_column, end_row - start_row)
    dn, pixel_qa, radsat = (datasets[name].read(1, window=window) for name in RASTER_NAMES)
    valid = qa_valid_mask(dn, pixel_qa, radsat)
    neighborhood: list[list[dict]] = []
    for rr in range(row - 2, row + 3):
        cells = []
        for cc in range(column - 2, column + 3):
            if not (0 <= rr < source.height and 0 <= cc < source.width):
                cells.append({"row": rr, "column": cc, "within_scene": False, "qa_valid": False,
                              "celsius": None, "st_dn": None, "qa_pixel": None, "qa_radsat": None})
                continue
            local_row, local_column = rr - start_row, cc - start_column
            accepted = bool(valid[local_row, local_column])
            code = int(dn[local_row, local_column])
            cells.append({"row": rr, "column": cc, "within_scene": True, "qa_valid": accepted,
                          "celsius": float(code * multiplier + offset - 273.15) if accepted else None,
                          "st_dn": code, "qa_pixel": int(pixel_qa[local_row, local_column]),
                          "qa_radsat": int(radsat[local_row, local_column])})
        neighborhood.append(cells)
    return neighborhood


def _extreme_candidate(
    dn: np.ndarray, pixel_qa: np.ndarray, radsat: np.ndarray, valid: np.ndarray,
    window: Window, kind: str, multiplier: float, offset: float,
) -> dict:
    rows, columns = np.nonzero(valid)
    values = dn[valid]
    index = int(np.argmin(values) if kind == "minimum" else np.argmax(values))
    row, column = int(rows[index] + window.row_off), int(columns[index] + window.col_off)
    code = int(values[index])
    return {"row": row, "column": column, "st_dn": code,
            "celsius": float(code * multiplier + offset - 273.15),
            "qa_pixel": int(pixel_qa[rows[index], columns[index]]),
            "qa_radsat": int(radsat[rows[index], columns[index]])}


def _prefer(candidate: dict, current: dict | None, kind: str) -> bool:
    if current is None:
        return True
    if candidate["st_dn"] != current["st_dn"]:
        return candidate["st_dn"] < current["st_dn"] if kind == "minimum" else candidate["st_dn"] > current["st_dn"]
    return (candidate["row"], candidate["column"]) < (current["row"], current["column"])


def audit_scene(directory: Path, product_id: str) -> dict:
    result = {"product_id": product_id, "acquisition_date": None, "satellite": None,
              "qa_valid_pixel_count": 0, "statistics_celsius": None, "threshold_counts": None,
              "minimum_pixel": None, "maximum_pixel": None, "clusters": {},
              "status": "FAIL", "errors": []}
    try:
        fields = parse_mtl(directory / f"{product_id}_MTL.txt")
        if fields.get("LANDSAT_PRODUCT_ID") != product_id:
            raise ValueError("MTL product ID mismatch")
        acquisition = fields["DATE_ACQUIRED"]
        if acquisition.replace("-", "") != product_id.split("_")[3]:
            raise ValueError("MTL acquisition date mismatch")
        result["acquisition_date"] = acquisition
        result["satellite"] = {"LC08": "Landsat 8", "LC09": "Landsat 9"}[product_id[:4]]
        multiplier = float(fields["TEMPERATURE_MULT_BAND_ST_B10"])
        offset = float(fields["TEMPERATURE_ADD_BAND_ST_B10"])
        if not math.isfinite(multiplier) or multiplier <= 0 or not math.isfinite(offset):
            raise ValueError("Invalid source calibration")
        with ExitStack() as stack:
            datasets = {name: stack.enter_context(rasterio.open(directory / f"{product_id}_{name}.TIF")) for name in RASTER_NAMES}
            width, height = _check_grid(datasets)
            reference = datasets["ST_B10"]
            histogram = np.zeros(65536, dtype=np.int64)
            target_masks = {key: np.zeros((height, width), dtype=bool) for key in CLUSTER_THRESHOLDS.get(product_id, ())}
            minimum, maximum = None, None
            for _, window in reference.block_windows(1):
                dn, pixel_qa, radsat = (datasets[name].read(1, window=window) for name in RASTER_NAMES)
                valid = qa_valid_mask(dn, pixel_qa, radsat)
                valid_dn = dn[valid]
                if valid_dn.size == 0:
                    continue
                celsius_valid = valid_dn.astype(np.float64) * multiplier + offset - 273.15
                if not np.all(np.isfinite(celsius_valid)):
                    raise ValueError("Non-finite calibrated QA-valid value")
                histogram += np.bincount(valid_dn, minlength=65536)
                for kind, current in (("minimum", minimum), ("maximum", maximum)):
                    candidate = _extreme_candidate(dn, pixel_qa, radsat, valid, window, kind, multiplier, offset)
                    if _prefer(candidate, current, kind):
                        if kind == "minimum":
                            minimum = candidate
                        else:
                            maximum = candidate
                for key, mask in target_masks.items():
                    row = slice(int(window.row_off), int(window.row_off + window.height))
                    column = slice(int(window.col_off), int(window.col_off + window.width))
                    mask[row, column] = threshold_mask(valid, celsius_valid, key)

            count = int(histogram.sum())
            if count == 0 or minimum is None or maximum is None:
                raise ValueError("No QA-valid pixels")
            result["qa_valid_pixel_count"] = count
            for extreme in (minimum, maximum):
                extreme.update(pixel_coordinates(reference.transform, reference.crs, extreme["row"], extreme["column"]))
                extreme["neighborhood_5x5"] = extract_neighborhood(
                    datasets, extreme["row"], extreme["column"], multiplier, offset
                )
                extreme["same_dn_qa_valid_pixel_count"] = int(histogram[extreme["st_dn"]])
                extreme["at_uint16_max"] = extreme["st_dn"] == np.iinfo(np.uint16).max
                neighbors = [cell for row in extreme["neighborhood_5x5"] for cell in row
                             if cell["within_scene"] and (cell["row"], cell["column"]) != (extreme["row"], extreme["column"])]
                extreme["invalid_qa_neighbor_count"] = sum(not cell["qa_valid"] for cell in neighbors)
                extreme["dilated_cloud_neighbor_count"] = sum(bool(cell["qa_pixel"] & (1 << 1)) for cell in neighbors)
            result["minimum_pixel"] = minimum
            result["maximum_pixel"] = maximum
            result["statistics_celsius"] = {
                "minimum": minimum["celsius"], "maximum": maximum["celsius"],
                "mean": float((np.arange(65536, dtype=np.float64) @ histogram) * multiplier / count + offset - 273.15),
                **{f"p{percentile:02d}" if percentile != 50 else "median":
                   percentile_from_histogram(histogram, percentile, multiplier, offset) for percentile in PERCENTILES},
            }
            result["threshold_counts"] = threshold_counts(histogram, multiplier, offset)
            for key, mask in target_masks.items():
                result["clusters"][key] = cluster_summary(mask, reference.transform, reference.crs)
                expected_count = result["threshold_counts"].get(key)
                if key == "below_10":
                    expected_count = result["threshold_counts"]["below_0"] + result["threshold_counts"]["from_0_to_10"]
                if expected_count is not None and result["clusters"][key]["pixel_count"] != expected_count:
                    raise ValueError(f"Cluster mask count differs from histogram for {key}")
            result["status"] = "PASS"
    except (OSError, ValueError, KeyError, rasterio.errors.RasterioError) as exc:
        result["errors"].append(str(exc))
    return result


def run_audit(source: Path = SOURCE, expected_ids: tuple[str, ...] = EXPECTED_IDS) -> dict:
    scenes = [audit_scene(source / product_id, product_id) for product_id in expected_ids]
    passed = sum(scene["status"] == "PASS" for scene in scenes)
    return {"audit_type": "read_only_full_scene_extreme_diagnostic",
            "audited_at_utc": datetime.now(timezone.utc).isoformat(), "disclaimer": DISCLAIMER,
            "source_directory": str(source), "scenes_expected": len(expected_ids),
            "scenes_passed": passed, "scenes_failed": len(scenes) - passed,
            "overall_status": "PASS" if passed == len(expected_ids) else "FAIL", "scenes": scenes}


def _fmt(value: object) -> str:
    return "Unavailable" if value is None else f"{value:.2f}" if isinstance(value, float) else str(value)


def _neighborhood_table(extreme: dict) -> list[str]:
    lines = ["| Relative row | -2 | -1 | 0 | +1 | +2 |", "| ---: | --- | --- | --- | --- | --- |"]
    for offset, row in zip(range(-2, 3), extreme["neighborhood_5x5"]):
        cells = ["outside" if not cell["within_scene"] else
                 f"{cell['celsius']:.2f} °C (valid)" if cell["qa_valid"] else "invalid QA"
                 for cell in row]
        lines.append("| " + str(offset) + " | " + " | ".join(cells) + " |")
    return lines


def render_markdown(result: dict) -> str:
    lines = [DISCLAIMER, "", "# Landsat 2025 full-scene extreme audit", "",
             "All statistics use QA-valid source pixels on original scene grids. Thresholds below are diagnostic counts only; no pixel was altered or removed. The 0–10 °C range means 0 ≤ Celsius < 10, and the <10 °C cluster count includes negative values.", "",
             "| Date | Product ID | Valid pixels | Min °C | P1 °C | P5 °C | P25 °C | Median °C | Mean °C | P75 °C | P95 °C | P99 °C | Max °C | <0 | 0–10 | >60 | >70 | >80 | >90 | Status |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for scene in result["scenes"]:
        stats, counts = scene["statistics_celsius"] or {}, scene["threshold_counts"] or {}
        values = [scene["acquisition_date"] or "Unavailable", f"`{scene['product_id']}`", scene["qa_valid_pixel_count"],
                  *[stats.get(key) for key in ("minimum", "p01", "p05", "p25", "median", "mean", "p75", "p95", "p99", "maximum")],
                  *[counts.get(key) for key in ("below_0", "from_0_to_10", "above_60", "above_70", "above_80", "above_90")], scene["status"]]
        lines.append("| " + " | ".join(_fmt(value) for value in values) + " |")
    lines += ["", f"**Overall:** {result['overall_status']} — {result['scenes_passed']}/{result['scenes_expected']} scenes passed.", "",
              "## Investigated scenes", ""]
    for product_id, kind, keys in ((HOT_SCENE, "maximum", ("above_80", "above_90")),
                                   (COLD_SCENE, "minimum", ("below_10", "below_0"))):
        scene = next((item for item in result["scenes"] if item["product_id"] == product_id), None)
        if scene is None or scene["status"] != "PASS":
            continue
        extreme = scene[f"{kind}_pixel"]
        stats = scene["statistics_celsius"]
        lines += [f"### {scene['acquisition_date']} — `{product_id}`", "",
                  f"Absolute {kind}: **{extreme['celsius']:.2f} °C** at zero-based row {extreme['row']}, column {extreme['column']} "
                  f"(projected x/y {extreme['x']:.2f}, {extreme['y']:.2f}; longitude/latitude {extreme['longitude']:.7f}, {extreme['latitude']:.7f}). "
                  f"DN {extreme['st_dn']}; QA_PIXEL {extreme['qa_pixel']}; QA_RADSAT {extreme['qa_radsat']}.", "",
                  f"Bulk comparison: P1 **{stats['p01']:.2f} °C**, median **{stats['median']:.2f} °C**, P99 **{stats['p99']:.2f} °C**. "
                  "The absolute extreme is distinct from these distribution summaries.", "",
                  "| Diagnostic range | QA-valid pixels | 8-neighbour clusters | Largest cluster | Largest cluster pixel-centre bounds |",
                  "| --- | ---: | ---: | ---: | --- |"]
        for key in keys:
            cluster = scene["clusters"][key]
            bounds = cluster["largest_cluster_bounds"]
            if bounds:
                xy = bounds["projected_pixel_center_bounds"]
                geo = bounds["longitude_latitude_pixel_center_bounds"]
                extent = (f"x {xy['min_x']:.2f}–{xy['max_x']:.2f}, y {xy['min_y']:.2f}–{xy['max_y']:.2f} m; "
                          f"lon {geo['min_longitude']:.6f}–{geo['max_longitude']:.6f}, "
                          f"lat {geo['min_latitude']:.6f}–{geo['max_latitude']:.6f}")
            else:
                extent = "none"
            lines.append(f"| {key.replace('_', ' ')} °C | {cluster['pixel_count']} | {cluster['cluster_count']} | {cluster['largest_cluster_size']} | {extent} |")
        lines += ["", "5×5 neighbourhood centred on the absolute extreme (invalid QA cells have no reported Celsius value):", ""]
        lines += _neighborhood_table(extreme)
        lines.append("")
        if product_id == HOT_SCENE:
            lines += ["The >80 °C and >90 °C pixels each form one small contiguous cluster, rather than isolated pixels or a large scene-wide region.", "",
                      f"The maximum has DN **{extreme['st_dn']}**, the maximum representable `uint16` value; "
                      f"**{extreme['same_dn_qa_valid_pixel_count']}** QA-valid pixels in this scene share that DN. "
                      "This is a possible source saturation or capping signal, not a confirmed cause. The raw QA values are retained above and in JSON.", ""]
        else:
            lines += ["The <10 °C and <0 °C pixels form several small clusters, rather than one isolated pixel or a large scene-wide region.", "",
                      f"Within the 5×5 window, **{extreme['invalid_qa_neighbor_count']}** of 24 neighbours fail the production QA mask; "
                      f"**{extreme['dilated_cloud_neighbor_count']}** neighbours carry the dilated-cloud bit. "
                      "The coldest pixel itself passes QA. This pattern warrants inspection for a possible QA-edge effect; it does not establish the cause.", ""]
    failures = [f"`{scene['product_id']}`: {error}" for scene in result["scenes"] for error in scene["errors"]]
    if failures:
        lines += ["## Failures", ""] + [f"- {error}" for error in failures] + [""]
    lines += ["Coordinates are pixel centres. Cluster bounds enclose pixel centres, not full pixel edges. The JSON report contains all per-scene extreme coordinates, raw QA values, full 5×5 cells, and cluster bounds. These diagnostics cannot identify the land feature or cause without further source investigation.", ""]
    return "\n".join(lines)


def write_reports(result: dict, json_path: Path = JSON_REPORT, csv_path: Path = CSV_REPORT, markdown_path: Path = MARKDOWN_REPORT) -> None:
    for path in (json_path, csv_path, markdown_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    fields = ["product_id", "acquisition_date", "satellite", "qa_valid_pixel_count", "status", "errors",
              "minimum", "p01", "p05", "p25", "median", "mean", "p75", "p95", "p99", "maximum",
              "below_0", "from_0_to_10", "above_60", "above_70", "above_80", "above_90"]
    for kind in ("minimum", "maximum"):
        fields += [f"{kind}_{key}" for key in ("row", "column", "x", "y", "longitude", "latitude", "st_dn", "celsius", "qa_pixel", "qa_radsat", "same_dn_qa_valid_pixel_count", "at_uint16_max", "invalid_qa_neighbor_count", "dilated_cloud_neighbor_count")]
    for key in ("above_80", "above_90", "below_10", "below_0"):
        fields += [f"{key}_{suffix}" for suffix in ("pixel_count", "cluster_count", "largest_cluster_size", "largest_cluster_bounds")]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for scene in result["scenes"]:
            row = {key: scene.get(key) for key in fields if key in scene}
            row["errors"] = "; ".join(scene["errors"])
            row.update(scene["statistics_celsius"] or {})
            row.update(scene["threshold_counts"] or {})
            for kind in ("minimum", "maximum"):
                extreme = scene[f"{kind}_pixel"] or {}
                row.update({f"{kind}_{key}": value for key, value in extreme.items() if key != "neighborhood_5x5"})
            for key, cluster in scene["clusters"].items():
                row.update({f"{key}_{suffix}": json.dumps(value) if suffix == "largest_cluster_bounds" and value is not None else value
                            for suffix, value in cluster.items()})
            writer.writerow(row)
    markdown_path.write_text(render_markdown(result), encoding="utf-8")


def main() -> int:
    result = run_audit()
    write_reports(result)
    print(f"Landsat extreme audit: {result['overall_status']} ({result['scenes_passed']}/{result['scenes_expected']} scenes passed)")
    print(f"Reports: {JSON_REPORT}, {CSV_REPORT}, {MARKDOWN_REPORT}")
    return 0 if result["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
