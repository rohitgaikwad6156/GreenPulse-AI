"""Import two authority-supplied municipal outlines without using ward geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PROVENANCE = ("source_organization", "source_url", "dataset_identifier", "license", "effective_date")


def _outline(path: Path, municipality: str) -> dict:
    if path.suffix.lower() != ".geojson":
        raise ValueError(f"{municipality}: authority-supplied EPSG:4326 GeoJSON is required")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        raise ValueError(f"{municipality}: expected a non-empty GeoJSON FeatureCollection")
    if document.get("crs") and "4326" not in json.dumps(document["crs"]):
        raise ValueError(f"{municipality}: input must be EPSG:4326")
    geometries = []
    for feature in document["features"]:
        properties = feature.get("properties") or {}
        if properties.get("municipality") not in (None, municipality):
            raise ValueError(f"{municipality}: mismatched municipality property")
        geometry = shape(feature.get("geometry"))
        if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"{municipality}: invalid polygon")
        minx, miny, maxx, maxy = geometry.bounds
        if not (72 <= minx <= maxx <= 75 and 17 <= miny <= maxy <= 20):
            raise ValueError(f"{municipality}: polygon outside Pune EPSG:4326 region")
        geometries.append(geometry)
    merged = unary_union(geometries)
    if merged.is_empty or not merged.is_valid:
        raise ValueError(f"{municipality}: invalid merged outline")
    return {"type": "Feature", "properties": {"municipality": municipality}, "geometry": mapping(merged)}


def import_outlines(pmc: Path, pcmc: Path, provenance_path: Path, *, output_dir: Path) -> dict:
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for municipality in ("PMC", "PCMC"):
        entry = provenance.get(municipality)
        if not isinstance(entry, dict):
            raise ValueError(f"provenance must contain a {municipality} object")
        missing = [key for key in REQUIRED_PROVENANCE if not isinstance(entry.get(key), str) or not entry[key].strip()]
        if missing:
            raise ValueError(f"{municipality} provenance missing: {', '.join(missing)}")
        date.fromisoformat(entry["effective_date"])
    features = [_outline(pmc, "PMC"), _outline(pcmc, "PCMC")]
    output_dir.mkdir(parents=True, exist_ok=True)
    boundary_path = output_dir / "pmc_pcmc.geojson"
    boundary_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")) + "\n", encoding="utf-8")
    evidence_path = output_dir / "pmc_pcmc_boundary_provenance.json"
    evidence_path.write_text(json.dumps({"imported_at": date.today().isoformat(), "source_kind": "official_municipal_outlines",
        "sources": provenance, "input_sha256": {"PMC": hashlib.sha256(pmc.read_bytes()).hexdigest(),
        "PCMC": hashlib.sha256(pcmc.read_bytes()).hexdigest()}}, indent=2) + "\n", encoding="utf-8")
    return {"boundary": boundary_path, "provenance": evidence_path}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import official PMC and PCMC municipal outlines")
    parser.add_argument("--pmc-outline", required=True, type=Path)
    parser.add_argument("--pcmc-outline", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    args = parser.parse_args()
    for path in import_outlines(args.pmc_outline, args.pcmc_outline, args.provenance,
                                output_dir=ROOT / "data" / "boundaries").values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
