"""Import authority-supplied PMC/PCMC ward vectors without inventing geometry."""

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


def _read_authority_geojson(path: Path, municipality: str, id_field: str, name_field: str) -> list[dict]:
    if path.suffix.lower() != ".geojson":
        raise ValueError(f"{municipality}: an authority-supplied GeoJSON is required; PDF/image maps are not GIS boundaries")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        raise ValueError(f"{municipality}: expected a non-empty GeoJSON FeatureCollection")
    crs = document.get("crs")
    if crs and "4326" not in json.dumps(crs):
        raise ValueError(f"{municipality}: input must be EPSG:4326 GeoJSON")
    result = []
    for index, feature in enumerate(document["features"], 1):
        props = feature.get("properties") or {}
        ward_id, ward_name = props.get(id_field), props.get(name_field)
        if ward_id is None or not str(ward_id).strip() or ward_name is None or not str(ward_name).strip():
            raise ValueError(f"{municipality}: feature {index} lacks {id_field!r} or {name_field!r}")
        geometry = shape(feature.get("geometry"))
        if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"{municipality}: feature {index} is not a valid polygon")
        minx, miny, maxx, maxy = geometry.bounds
        if not (72 <= minx <= maxx <= 75 and 17 <= miny <= maxy <= 20):
            raise ValueError(f"{municipality}: feature {index} is outside the Pune EPSG:4326 region")
        result.append({"type": "Feature", "properties": {"municipality": municipality,
                       "ward_id": str(ward_id).strip(), "ward_name": str(ward_name).strip()},
                       "geometry": mapping(geometry)})
    return result


def import_boundaries(pmc: Path, pcmc: Path, provenance_path: Path, *,
                      pmc_id: str, pmc_name: str, pcmc_id: str, pcmc_name: str,
                      output_dir: Path) -> dict:
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for municipality in ("PMC", "PCMC"):
        entry = provenance.get(municipality)
        if not isinstance(entry, dict):
            raise ValueError(f"provenance must contain a {municipality} object")
        missing = [key for key in REQUIRED_PROVENANCE if not isinstance(entry.get(key), str) or not entry[key].strip()]
        if missing:
            raise ValueError(f"{municipality} provenance missing: {', '.join(missing)}")
        date.fromisoformat(entry["effective_date"])
    features = (_read_authority_geojson(pmc, "PMC", pmc_id, pmc_name) +
                _read_authority_geojson(pcmc, "PCMC", pcmc_id, pcmc_name))
    ids = [(f["properties"]["municipality"], f["properties"]["ward_id"]) for f in features]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate municipality/ward_id in supplied boundaries")
    output_dir.mkdir(parents=True, exist_ok=True)
    wards_path = output_dir / "pmc_pcmc_wards.geojson"
    wards_doc = {"type": "FeatureCollection", "features": features}
    wards_path.write_text(json.dumps(wards_doc, separators=(",", ":")) + "\n", encoding="utf-8")
    outlines = []
    for municipality in ("PMC", "PCMC"):
        merged = unary_union([shape(f["geometry"]) for f in features if f["properties"]["municipality"] == municipality])
        outlines.append({"type": "Feature", "properties": {"municipality": municipality}, "geometry": mapping(merged)})
    boundary_path = output_dir / "pmc_pcmc.geojson"
    boundary_path.write_text(json.dumps({"type": "FeatureCollection", "features": outlines}, separators=(",", ":")) + "\n", encoding="utf-8")
    evidence = {"imported_at": date.today().isoformat(), "sources": provenance,
                "input_sha256": {"PMC": hashlib.sha256(pmc.read_bytes()).hexdigest(),
                                  "PCMC": hashlib.sha256(pcmc.read_bytes()).hexdigest()},
                "ward_count": len(features)}
    evidence_path = output_dir / "pmc_pcmc_boundary_provenance.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return {"wards": wards_path, "boundary": boundary_path, "provenance": evidence_path}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import official PMC/PCMC ward polygons")
    parser.add_argument("--pmc-wards", required=True, type=Path)
    parser.add_argument("--pcmc-wards", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--pmc-id-field", required=True); parser.add_argument("--pmc-name-field", required=True)
    parser.add_argument("--pcmc-id-field", required=True); parser.add_argument("--pcmc-name-field", required=True)
    args = parser.parse_args()
    result = import_boundaries(args.pmc_wards, args.pcmc_wards, args.provenance,
                               pmc_id=args.pmc_id_field, pmc_name=args.pmc_name_field,
                               pcmc_id=args.pcmc_id_field, pcmc_name=args.pcmc_name_field,
                               output_dir=ROOT / "data" / "boundaries")
    print("Imported verified boundary files:")
    for path in result.values(): print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
