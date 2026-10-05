"""One-command real-source Pune/PCMC heat-map build; no synthetic fallback.

Uses the existing geospatial processors, five-fold spatial validation and
XGBoost trainer. Production files are replaced only after every stage succeeds.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.data_intake.manifest import (  # noqa: E402 - ROOT must be on sys.path first
    validate_manifest,
    verified_ward_path,
)

SOURCE_IDS = {"municipal_boundary", "landsat_lst_scenes",
              "sentinel2_l2a_scenes", "esa_worldcover", "osm_roads"}


def preflight(root: Path, manifest: Path, year: int) -> dict:
    """Validate only inputs needed for this five-predictor model, including hashes."""
    report = validate_manifest(manifest, root, source_ids=SOURCE_IDS)
    result = report.as_dict()
    result["errors"] = list(result["errors"])
    if not report.ok:
        return result
    document = json.loads(manifest.read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in document["sources"] if item["id"] in SOURCE_IDS}
    try:
        if verified_ward_path(manifest, root) is not None:
            sources["ward_boundaries"] = next(item for item in document["sources"]
                                                if item["id"] == "ward_boundaries")
            result["verified_sources"].append("ward_boundaries")
    except (OSError, ValueError) as exc:
        result["warnings"].append(str(exc) + "; ward reporting disabled for this build")
    expected = {"start": f"{year}-03-01", "end": f"{year}-05-31"}
    for name in ("landsat_lst_scenes", "sentinel2_l2a_scenes"):
        if sources[name].get("scene_date_range") != expected:
            result["errors"].append(f"{name}: requested year differs from verified March-May source period")
    result["ok"] = not result["errors"]
    result["sources"] = sources
    return result


def _publish(stage: Path, root: Path) -> Path:
    """Keep a recoverable backup and roll back replacements on a write failure."""
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    backup_parent = root / "data" / "interim" / "heat_map_backups"
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="previous-", dir=backup_parent))
    existing = set()
    for source in files:
        relative = source.relative_to(stage)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            existing.add(relative)
    replaced = []
    try:
        for source in files:
            relative = source.relative_to(stage)
            os.replace(source, root / relative)
            replaced.append(relative)
    except OSError:
        for relative in reversed(replaced):
            if relative in existing:
                shutil.copy2(backup / relative, root / relative)
            else:
                (root / relative).unlink()
        raise
    return backup


def _rewrite_paths(value, stage: Path, root: Path):
    if isinstance(value, dict):
        return {key: _rewrite_paths(item, stage, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_paths(item, stage, root) for item in value]
    if isinstance(value, str):
        return value.replace(str(stage), str(root)).replace(stage.as_posix(), root.as_posix())
    return value


def run_pipeline(root: Path, manifest: Path, year: int, trials: int = 8, jobs: int = 2) -> dict:
    if trials < 1 or jobs < 1:
        raise ValueError("trials and jobs must be positive")
    print("1/7 Checking real source provenance, checksums and acquisition period", flush=True)
    check = preflight(root, manifest, year)
    if not check["ok"]:
        raise ValueError("Source preflight failed:\n" + "\n".join(check["errors"]))
    sources = check["sources"]
    def source_path(name):
        return root / sources[name]["local_path"]
    from backend.app.geospatial import landsat_lst as landsat
    from backend.app.geospatial import sentinel2_indices as sentinel
    from backend.app.geospatial import urban_morphology as morphology
    from backend.app.geospatial.ml_dataset import build_ml_dataset
    from backend.app.ml.baselines import evaluate_baselines
    from backend.app.ml.spatial_cv import build_cv_artifacts
    from backend.app.ml.xgboost_lst import train_xgboost_lst

    scratch = root / "data" / "interim"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="heat-map-build-", dir=scratch) as temporary:
        stage = Path(temporary)
        processed = stage / "data" / "processed"
        models = stage / "models"
        boundaries = stage / "data" / "boundaries"
        boundaries.mkdir(parents=True)
        shutil.copy2(source_path("municipal_boundary"), boundaries / "pmc_pcmc.geojson")
        ward_path = None
        if "ward_boundaries" in sources:
            ward_path = boundaries / "pmc_pcmc_wards.geojson"
            shutil.copy2(source_path("ward_boundaries"), ward_path)
        boundary = landsat.load_municipal_boundary(boundaries / "pmc_pcmc.geojson")
        print("2/7 QA-mask Landsat 8/9 L2SP and composite measured LST in Celsius", flush=True)
        scenes = landsat.discover_scenes(source_path("landsat_lst_scenes"), year)
        composite, count, transform, inside, used = landsat.build_composite(scenes, boundary)
        landsat.save_outputs(composite, count, transform, inside, used, scenes, year,
                             processed / "lst_pune_30m.tif")
        del composite, count
        print("3/7 Align Sentinel-2 NDVI/NDBI to the same EPSG:32643 30 m grid", flush=True)
        granules = sentinel.discover_granules(source_path("sentinel2_l2a_scenes"), year)
        height, width = inside.shape
        ndvi, ndbi, ndvi_count, ndbi_count, used = sentinel.build_composites(
            granules, transform, height, width, inside)
        sentinel.save_outputs(ndvi, ndbi, ndvi_count, ndbi_count, transform, inside,
                              granules, used, year, processed)
        del ndvi, ndbi, ndvi_count, ndbi_count
        print("4/7 Aggregate WorldCover classes and intersect mapped OSM road lengths", flush=True)
        tiles = morphology.discover_worldcover_tiles(source_path("esa_worldcover"))
        tree, built, valid_count = morphology.worldcover_fractions(tiles, transform, height, width, inside)
        roads = morphology.load_osm_geometries(source_path("osm_roads"), "roads")
        layers = {"tree_canopy_pct": tree, "built_pct": built,
                  "road_density": morphology.road_density_grid(roads, transform, height, width, inside)}
        morphology.save_layers(layers, transform, inside, stage / "data" / "interim" / "morphology",
                               {"tree_canopy_pct": str(source_path("esa_worldcover")),
                                "built_pct": str(source_path("esa_worldcover")),
                                "road_density": str(source_path("osm_roads"))}, valid_count, profile="heat-map")
        del layers, tree, built, valid_count, roads
        print("5/7 Write complete-case grid and source provenance", flush=True)
        dataset = processed / "greenpulse_ml_grid.parquet"
        grid_metadata = processed / "metadata.json"
        report = build_ml_dataset(stage, ward_path, dataset,
                                  grid_metadata, profile="heat-map")
        report.update(data_classification="real", source="Verified Landsat/Sentinel-2/WorldCover/OSM",
                      verified_sources=sources, pipeline="scripts/build_heat_map_pipeline.py")
        grid_metadata.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print("6/7 Train XGBoost with five held-out 5 km spatial blocks folds", flush=True)
        build_cv_artifacts(dataset, processed)
        # Reuse the existing trainer's baseline contract instead of introducing a second model format.
        evaluate_baselines(dataset, processed, models / "baseline_metrics.json", rf_jobs=jobs)
        model_report = train_xgboost_lst(dataset, processed, models / "baseline_metrics.json",
                                        models / "xgboost_lst.joblib", models / "model_metadata.json",
                                        n_trials=trials, jobs=jobs)
        model_report.update(data_classification="real", verified_sources=sources,
                            feature_profile="heat-map", pipeline="scripts/build_heat_map_pipeline.py")
        (models / "model_metadata.json").write_text(json.dumps(model_report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print("7/7 Recheck sources and publish verified artifacts with backup", flush=True)
        recheck = preflight(root, manifest, year)
        if not recheck["ok"] or recheck.get("sources") != sources:
            raise ValueError("Source files or manifest changed during processing; nothing published")
        for path in stage.rglob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps(_rewrite_paths(value, stage, root), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        backup = _publish(stage, root)
    return {"status": "complete", "row_count": report["row_count"],
            "date_range": report["date_range"], "features": report["features"],
            "spatial_cv_metrics": model_report["spatial_cv_metrics"], "backup": str(backup),
            "finished_at_utc": datetime.now(timezone.utc).isoformat()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025, help="March-May year (default: existing 2025 research season)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, help="Source manifest; defaults to ROOT/data/source_manifest.json")
    parser.add_argument("--check-only", action="store_true", help="Validate inputs without changing artifacts")
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = args.manifest or root / "data" / "source_manifest.json"
    try:
        if args.check_only:
            result = preflight(root, manifest, args.year)
            result.pop("sources", None)
            print(json.dumps(result, indent=2))
            return 0 if result["ok"] else 2
        result = run_pipeline(root, manifest, args.year, args.trials, args.jobs)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Real heat-map pipeline stopped: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
