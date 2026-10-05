"""Read-only intake audit for the six Sentinel-2 L2A products in discovery_2025.json."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import rasterio


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.sentinel2_indices import read_boa_calibration  # noqa: E402


DISCOVERY = ROOT / "data" / "provenance" / "discovery_2025.json"
SOURCE = ROOT / "data" / "raw" / "sentinel2"
JSON_REPORT = ROOT / "data" / "provenance" / "sentinel_quality_audit_2025.json"
CSV_REPORT = ROOT / "data" / "provenance" / "sentinel_quality_audit_2025.csv"
MARKDOWN_REPORT = ROOT / "docs" / "sentinel_quality_audit.md"
PRODUCT_PATTERN = re.compile(r"^S2[ABC]_MSIL2A_(\d{8})T\d{6}_N\d{4}_R\d{3}_T(\d{2}[A-Z]{3})_\d{8}T\d{6}$")
BANDS = {"B04_10m": ("B04", 10), "B08_10m": ("B08", 10),
         "B11_20m": ("B11", 20), "SCL_20m": ("SCL", 20)}
REQUIRED = ("MTD_MSIL2A.xml", *BANDS)


def load_selected_items(discovery_path: Path = DISCOVERY) -> list[dict]:
    document = json.loads(discovery_path.read_text(encoding="utf-8"))
    items = document["sentinel2"]["items"]
    if not isinstance(items, list) or len(items) != 6:
        raise ValueError("Discovery must contain exactly six selected Sentinel-2 items")
    product_ids = [item["product_id"] for item in items]
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("Duplicate Sentinel-2 product ID in discovery")
    return items


def product_fields(item: dict) -> tuple[str, str, str, list[str]]:
    product_id = item["product_id"]
    errors: list[str] = []
    match = PRODUCT_PATTERN.fullmatch(product_id)
    if match is None:
        errors.append("Selected product ID is not a Sentinel-2 Level-2A product name")
    try:
        acquisition_date = date.fromisoformat(item["acquisition_datetime"].split("T", 1)[0]).isoformat()
    except (KeyError, ValueError):
        acquisition_date = ""
        errors.append("Discovery acquisition date is missing or invalid")
    tile = item.get("mgrs_tile", "")
    if match:
        if match.group(1) != acquisition_date.replace("-", ""):
            errors.append("Product acquisition date disagrees with discovery")
        if tile != f"MGRS-{match.group(2)}":
            errors.append("Product MGRS tile disagrees with discovery")
        if not date(2025, 3, 1) <= date.fromisoformat(match.group(1)) <= date(2025, 5, 31):
            errors.append("Selected product is outside March-May 2025")
    return product_id, acquisition_date, tile, errors


def backend_band_matches(granule: Path, band: str, resolution: int) -> list[Path]:
    """Mirror the production suffix match, including its uniqueness requirement."""
    folder = granule / "IMG_DATA" / f"R{resolution}m"
    suffix = f"_{band}_{resolution}m.jp2"
    return [path for path in folder.glob("*") if path.name.lower().endswith(suffix.lower())]


def band_candidates(granule: Path, product_date: str, tile_code: str, band: str, resolution: int) -> list[Path]:
    """Use the backend layout and suffix, then enforce source tile/date identity."""
    matches = backend_band_matches(granule, band, resolution)
    if not product_date or not tile_code:
        return matches
    prefix = re.compile(rf"^T{re.escape(tile_code)}_{product_date.replace('-', '')}T\d{{6}}_{band}_{resolution}m\.jp2$", re.IGNORECASE)
    return [path for path in matches if prefix.fullmatch(path.name)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path | None, label: str, *, resolution: int | None = None) -> dict:
    record = {"label": label, "path": str(path) if path else None, "present": bool(path and path.is_file()),
              "size_bytes": None, "sha256": None, "readable": None,
              "crs": None, "resolution_m": None, "transform": None, "width": None, "height": None,
              "dtype": None, "errors": []}
    if not record["present"]:
        return record
    assert path is not None
    try:
        record["size_bytes"] = path.stat().st_size
        record["sha256"] = sha256_file(path)
        if resolution is not None:
            with rasterio.open(path) as raster:
                record.update(crs=str(raster.crs) if raster.crs else None,
                              resolution_m=[abs(raster.transform.a), abs(raster.transform.e)],
                              transform=list(raster.transform)[:6],
                              width=raster.width, height=raster.height,
                              dtype=raster.dtypes[0] if raster.count else None)
                if raster.count != 1:
                    record["errors"].append("Expected one raster band")
                if raster.crs is None or not raster.crs.is_projected or raster.crs.linear_units.lower() not in ("metre", "meter", "metres", "meters"):
                    record["errors"].append("Raster CRS is absent or not projected in metres")
                if not (math.isclose(raster.transform.a, resolution, abs_tol=1e-6)
                        and math.isclose(raster.transform.e, -resolution, abs_tol=1e-6)
                        and math.isclose(raster.transform.b, 0, abs_tol=1e-9)
                        and math.isclose(raster.transform.d, 0, abs_tol=1e-9)):
                    record["errors"].append(f"Expected north-up {resolution} m pixels")
                expected_dtypes = ("uint8", "uint16") if label == "SCL_20m" else ("uint16",)
                if record["dtype"] not in expected_dtypes:
                    record["errors"].append(f"Expected {expected_dtypes} pixel type")
                if raster.count == 1:
                    for _, window in raster.block_windows(1):
                        raster.read(1, window=window)
            record["readable"] = True
    except (OSError, rasterio.errors.RasterioError, ValueError) as exc:
        record["readable"] = False
        record["errors"].append(f"Cannot read/hash file: {exc}")
    return record


def audit_product(item: dict, source: Path = SOURCE) -> dict:
    product_id, acquisition_date, tile, errors = product_fields(item)
    safe = source / f"{product_id}.SAFE"
    result = {"product_id": product_id, "acquisition_date": acquisition_date,
              "mgrs_tile": tile, "safe_directory": str(safe),
              "safe_directory_present": safe.is_dir(), "metadata": file_record(safe / "MTD_MSIL2A.xml", "MTD_MSIL2A.xml"),
              "granules": [], "required_files": {key: False for key in REQUIRED},
              "status": "FAIL", "errors": errors}
    if not safe.is_dir():
        result["errors"].append("SAFE directory missing")
        return result
    metadata = safe / "MTD_MSIL2A.xml"
    result["required_files"]["MTD_MSIL2A.xml"] = result["metadata"]["present"]
    if not result["metadata"]["present"]:
        result["errors"].append("MTD_MSIL2A.xml missing")
    else:
        try:
            read_boa_calibration(metadata)
            xml_root = ElementTree.parse(metadata).getroot()
            for element in xml_root.iter():
                if element.tag.rsplit("}", 1)[-1] in ("PRODUCT_URI", "PRODUCT_URI_2A"):
                    value = (element.text or "").strip()
                    if value and Path(value).name != safe.name:
                        result["errors"].append(f"Metadata product URI differs from selected SAFE: {value}")
        except ValueError as exc:
            result["errors"].append(f"Product metadata calibration invalid: {exc}")
        except ElementTree.ParseError as exc:
            result["errors"].append(f"Product metadata XML unreadable: {exc}")
    result["errors"].extend(result["metadata"]["errors"])

    granule_root = safe / "GRANULE"
    directories = sorted(path for path in granule_root.iterdir() if path.is_dir()) if granule_root.is_dir() else []
    if not directories:
        result["errors"].append("No GRANULE/<granule-id> directory")
    for granule in directories:
        band_records: dict[str, dict] = {}
        prefixes: set[str] = set()
        for label, (band, resolution) in BANDS.items():
            backend_matches = backend_band_matches(granule, band, resolution)
            matches = band_candidates(granule, acquisition_date, tile.removeprefix("MGRS-"), band, resolution)
            if len(backend_matches) != 1:
                result["errors"].append(f"{granule.name}: backend expects exactly one {label} JP2; found {len(backend_matches)}")
            if len(matches) != 1:
                result["errors"].append(f"{granule.name}: expected one matching {label} JP2; found {len(matches)}")
                band_records[label] = file_record(None, label, resolution=resolution)
                continue
            record = file_record(matches[0], label, resolution=resolution)
            band_records[label] = record
            result["errors"].extend(f"{granule.name}/{label}: {error}" for error in record["errors"])
            prefixes.add(re.sub(rf"_{band}_{resolution}m\.jp2$", "", matches[0].name, flags=re.IGNORECASE).upper())
        if len(prefixes) > 1:
            result["errors"].append(f"{granule.name}: band filename acquisition prefixes differ")
        # 10 m peers and 20 m peers must align; 10 m and 20 m dimensions may differ.
        for left, right in (("B04_10m", "B08_10m"), ("B11_20m", "SCL_20m")):
            a, b = band_records[left], band_records[right]
            if a["readable"] and b["readable"] and (a["crs"], a["width"], a["height"], a["transform"]) != (b["crs"], b["width"], b["height"], b["transform"]):
                result["errors"].append(f"{granule.name}: {left} and {right} grid size/CRS differ")
        crss = {record["crs"] for record in band_records.values() if record["crs"]}
        if len(crss) > 1:
            result["errors"].append(f"{granule.name}: raster CRS differs between bands")
        result["granules"].append({"granule_id": granule.name, "bands": band_records})
    for label in BANDS:
        result["required_files"][label] = bool(directories) and all(
            granule["bands"][label]["present"] for granule in result["granules"]
        )
    result["status"] = "PASS" if not result["errors"] and all(result["required_files"].values()) else "FAIL"
    return result


def run_audit(source: Path = SOURCE, discovery_path: Path = DISCOVERY) -> dict:
    items = load_selected_items(discovery_path)
    products = [audit_product(item, source) for item in items]
    expected_safe_names = {f"{item['product_id']}.SAFE" for item in items}
    unexpected = sorted(path.name for path in source.rglob("*.SAFE") if path.is_dir() and path.name not in expected_safe_names) if source.is_dir() else []
    passed = sum(product["status"] == "PASS" for product in products)
    return {"audit_type": "manual_sentinel2_l2a_source_intake", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(source), "discovery_file": str(discovery_path),
            "expected_product_count": len(items), "safe_directories_found": sum(p["safe_directory_present"] for p in products),
            "minimum_required_files_expected": len(items) * len(REQUIRED),
            "required_file_slots_found": sum(sum(p["required_files"].values()) for p in products),
            "products_passed": passed, "products_failed": len(items) - passed,
            "unexpected_safe_directories": unexpected,
            "overall_status": "PASS" if passed == len(items) and not unexpected else "FAIL",
            "intake_state": "READY" if passed == len(items) and not unexpected else "PENDING",
            "products": products}


def _file_rows(product: dict) -> list[tuple[str, str | None, dict | None]]:
    rows = [("MTD_MSIL2A.xml", None, product["metadata"])]
    if product["granules"]:
        for granule in product["granules"]:
            rows.extend((label, granule["granule_id"], granule["bands"][label]) for label in BANDS)
    else:
        rows.extend((label, None, None) for label in BANDS)
    return rows


def render_markdown(result: dict) -> str:
    lines = ["# Sentinel-2 L2A manual source intake: March-May 2025", "",
             "This report audits only local files selected in `data/provenance/discovery_2025.json`. No data was downloaded or created, and source verification status was not changed.", "",
             "## Backend path contract", "",
             "The production `discover_granules()` looks recursively below `data/raw/sentinel2/` for `*.SAFE` directories whose names contain `MSIL2A` and a March-May acquisition date. Inside each SAFE it reads `MTD_MSIL2A.xml` and each directory under `GRANULE/`. For **each** granule it requires exactly one matching JP2 at:", "",
             "- `GRANULE/<original-granule-id>/IMG_DATA/R10m/*_B04_10m.jp2`",
             "- `GRANULE/<original-granule-id>/IMG_DATA/R10m/*_B08_10m.jp2`",
             "- `GRANULE/<original-granule-id>/IMG_DATA/R20m/*_B11_20m.jp2`",
             "- `GRANULE/<original-granule-id>/IMG_DATA/R20m/*_SCL_20m.jp2`", "",
             "The audit additionally checks that JP2 filenames carry the selected tile and acquisition date and share a granule prefix. Preserve the original SAFE and granule names from the manual download. Metadata must supply the BOA quantification and offsets required by the existing backend.", "",
             "## Selected products", "",
             "| Date | MGRS tile | Exact product ID | SAFE | XML | B04 10 m | B08 10 m | B11 20 m | SCL 20 m | Status |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for product in result["products"]:
        markers = ["present" if product["required_files"][key] else "missing" for key in REQUIRED]
        lines.append(f"| {product['acquisition_date'] or 'unknown'} | {product['mgrs_tile']} | `{product['product_id']}` | {'present' if product['safe_directory_present'] else 'missing'} | " + " | ".join(markers) + f" | {product['status']} |")
    lines += ["", "## Exact placement", "",
              "Place each manually obtained, extracted original SAFE directly under `data/raw/sentinel2/`:", ""]
    for product in result["products"]:
        lines.append(f"- `data/raw/sentinel2/{product['product_id']}.SAFE/`")
    lines += ["", "Within **each** SAFE, retain `MTD_MSIL2A.xml` at the SAFE root and the original `GRANULE/<original-granule-id>/IMG_DATA/R10m` and `R20m` directories with the four JP2 files listed above. Do not rename imagery into a different product or invent a granule ID.", "",
              "## Missing manual files", ""]
    for product in result["products"]:
        missing = [label for label, present in product["required_files"].items() if not present]
        if missing:
            lines.append(f"- `{product['product_id']}.SAFE`: {', '.join(missing)}")
    if all(all(product["required_files"].values()) for product in result["products"]):
        lines.append("- None")
    lines += ["",
              "## Current intake status", "",
              f"- Expected products: **{result['expected_product_count']}**",
              f"- SAFE directories found: **{result['safe_directories_found']}**",
              f"- Minimum required files expected: **{result['minimum_required_files_expected']}**",
              f"- Required file slots found: **{result['required_file_slots_found']}**",
              f"- Products passed: **{result['products_passed']}**",
              f"- Products failed: **{result['products_failed']}**",
              f"- Overall: **{result['overall_status']} / {result['intake_state']}**", ""]
    if result["unexpected_safe_directories"]:
        lines.append(f"Unexpected SAFE directories: {', '.join(result['unexpected_safe_directories'])}.")
        lines.append("")
    lines += ["The JSON and CSV contain per-file presence, size, SHA-256, readability, CRS, resolution, and dimensions when a real file exists. A missing file has null measurements; no values are inferred.", ""]
    return "\n".join(lines)


def write_reports(result: dict, json_path: Path = JSON_REPORT, csv_path: Path = CSV_REPORT, markdown_path: Path = MARKDOWN_REPORT) -> None:
    for path in (json_path, csv_path, markdown_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    fields = ["product_id", "acquisition_date", "mgrs_tile", "safe_directory", "safe_directory_present",
              "granule_id", "required_file", "present", "path", "size_bytes", "sha256", "readable",
              "crs", "resolution_m", "transform", "width", "height", "dtype", "file_errors", "validation_status", "product_errors"]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for product in result["products"]:
            for label, granule_id, record in _file_rows(product):
                record = record or {}
                writer.writerow({"product_id": product["product_id"], "acquisition_date": product["acquisition_date"],
                                 "mgrs_tile": product["mgrs_tile"], "safe_directory": product["safe_directory"],
                                 "safe_directory_present": product["safe_directory_present"],
                                 "granule_id": granule_id, "required_file": label, "present": bool(record.get("present")),
                                 "path": record.get("path"), "size_bytes": record.get("size_bytes"),
                                 "sha256": record.get("sha256"), "readable": record.get("readable"),
                                 "crs": record.get("crs"), "resolution_m": json.dumps(record["resolution_m"]) if record.get("resolution_m") else None,
                                 "transform": json.dumps(record["transform"]) if record.get("transform") else None,
                                 "width": record.get("width"), "height": record.get("height"), "dtype": record.get("dtype"),
                                 "file_errors": "; ".join(record.get("errors", [])), "validation_status": product["status"],
                                 "product_errors": "; ".join(product["errors"])})
    markdown_path.write_text(render_markdown(result), encoding="utf-8")


def main() -> int:
    result = run_audit()
    write_reports(result)
    print(f"Sentinel source intake: {result['overall_status']} / {result['intake_state']} ({result['products_passed']}/{result['expected_product_count']} passed)")
    print(f"Reports: {JSON_REPORT}, {CSV_REPORT}, {MARKDOWN_REPORT}")
    return 0 if result["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
