"""Command-line entry point for the real Landsat-only LST pipeline."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.landsat_lst import (  # noqa: E402
    build_composite,
    discover_scenes,
    load_municipal_boundary,
    save_outputs,
)


def main() -> int:
    """Build a March–May LST GeoTIFF from local, original USGS scene files."""
    parser = argparse.ArgumentParser(description="Build real Pune/PCMC Landsat L2SP LST; no demo inputs")
    parser.add_argument("--year", required=True, type=int, help="March–May acquisition year")
    parser.add_argument("--scenes-dir", type=Path, default=ROOT / "data" / "raw" / "landsat")
    parser.add_argument("--boundary", type=Path, default=ROOT / "data" / "boundaries" / "pmc_pcmc.geojson")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "lst_pune_30m.tif")
    args = parser.parse_args()
    try:
        boundary = load_municipal_boundary(args.boundary)
        scenes = discover_scenes(args.scenes_dir, args.year)
        composite, count, transform, inside, used_ids = build_composite(scenes, boundary)
        summary = save_outputs(composite, count, transform, inside, used_ids, scenes, args.year, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Landsat LST pipeline stopped: {exc}\n")
    print(f"Saved real-data LST GeoTIFF: {args.output}")
    print(f"QA-accepted scenes: {len(used_ids)}")
    print(f"Minimum LST (deg C): {summary['min_lst_c']:.3f}")
    print(f"Maximum LST (deg C): {summary['max_lst_c']:.3f}")
    print(f"Mean LST (deg C): {summary['mean_lst_c']:.3f}")
    print(f"No-data inside PMC/PCMC: {summary['nodata_percent']:.2f}%")
    print(f"QA JSON: {args.output.with_suffix('.json')}")
    print(f"Histogram: {args.output.with_name(args.output.stem + '_histogram.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
