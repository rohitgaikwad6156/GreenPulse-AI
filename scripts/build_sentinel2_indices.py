"""Command-line entry point for real Sentinel-2 L2A NDVI/NDBI processing."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.sentinel2_indices import (  # noqa: E402
    build_composites,
    discover_granules,
    save_outputs,
    validate_reference,
)


def main() -> int:
    """Produce measured March-May NDVI/NDBI on the existing LST grid."""
    parser = argparse.ArgumentParser(description="Build real Pune/PCMC Sentinel-2 L2A indices; no demo inputs")
    parser.add_argument("--year", type=int, required=True, help="March-May acquisition year")
    parser.add_argument("--scenes-dir", type=Path, default=ROOT / "data" / "raw" / "sentinel2")
    parser.add_argument("--boundary", type=Path, default=ROOT / "data" / "boundaries" / "pmc_pcmc.geojson")
    parser.add_argument("--lst", type=Path, default=ROOT / "data" / "processed" / "lst_pune_30m.tif")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "processed")
    args = parser.parse_args()
    try:
        transform, height, width, inside = validate_reference(args.lst, args.boundary, args.year)
        granules = discover_granules(args.scenes_dir, args.year)
        ndvi, ndbi, ndvi_count, ndbi_count, used = build_composites(granules, transform, height, width, inside)
        stats = save_outputs(ndvi, ndbi, ndvi_count, ndbi_count, transform, inside, granules, used, args.year, args.output_dir)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Sentinel-2 index pipeline stopped: {exc}\n")
    for name in ("ndvi", "ndbi"):
        summary = stats[name]
        print(f"Saved {args.output_dir / f'{name}_pune_30m.tif'}")
        print(f"{name.upper()}: min={summary['min']:.4f}, max={summary['max']:.4f}, mean={summary['mean']:.4f}, nodata={summary['nodata_percent']:.2f}%")
    print(f"QA-accepted granules: {len(used)}")
    print(f"Maps: {args.output_dir / 'sentinel2_indices_pune_30m_maps.png'}")
    print(f"Histograms: {args.output_dir / 'sentinel2_indices_pune_30m_histograms.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
