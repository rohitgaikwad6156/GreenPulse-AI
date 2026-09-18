"""Build real WorldCover, OSM, and WorldPop features on the LST grid."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.sentinel2_indices import validate_reference  # noqa: E402
from backend.app.geospatial.urban_morphology import (  # noqa: E402
    building_fraction_grid,
    discover_worldcover_tiles,
    green_distance_grid,
    load_osm_geometries,
    road_density_grid,
    save_layers,
    worldcover_fractions,
    worldpop_density_grid,
)


def main() -> int:
    """Write separate aligned 30 m layers only when all real inputs are valid."""
    parser = argparse.ArgumentParser(description="Build real-source PMC/PCMC morphology layers; no demo data")
    parser.add_argument("--lst", type=Path, default=ROOT / "data" / "processed" / "lst_pune_30m.tif")
    parser.add_argument("--boundary", type=Path, default=ROOT / "data" / "boundaries" / "pmc_pcmc.geojson")
    parser.add_argument("--worldcover-dir", type=Path, default=ROOT / "data" / "raw" / "worldcover")
    parser.add_argument("--osm-roads", type=Path, default=ROOT / "data" / "raw" / "osm" / "roads.geojson")
    parser.add_argument("--osm-green", type=Path, default=ROOT / "data" / "raw" / "osm" / "green_spaces.geojson")
    parser.add_argument("--osm-buildings", type=Path, help="Optional complete OSM building inventory GeoJSON")
    parser.add_argument("--worldpop", type=Path, required=True, help="Official WorldPop population raster GeoTIFF")
    parser.add_argument("--worldpop-kind", choices=("counts", "density"), default="counts",
                        help="Source pixel units: people/pixel or people/km²")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "interim" / "morphology")
    args = parser.parse_args()
    try:
        transform, height, width, inside = validate_reference(args.lst, args.boundary)
        tiles = discover_worldcover_tiles(args.worldcover_dir)
        roads = load_osm_geometries(args.osm_roads, "roads")
        green = load_osm_geometries(args.osm_green, "green")
        buildings = load_osm_geometries(args.osm_buildings, "buildings") if args.osm_buildings else None
        if not args.worldpop.is_file():
            raise ValueError(f"WorldPop raster is missing: {args.worldpop}")
        tree, built, worldcover_count = worldcover_fractions(tiles, transform, height, width, inside)
        layers = {"tree_canopy_pct": tree, "built_pct": built,
                  "road_density": road_density_grid(roads, transform, height, width, inside),
                  "distance_green_m": green_distance_grid(green, transform, height, width, inside),
                  "population_density": worldpop_density_grid(args.worldpop, transform, height, width, inside, args.worldpop_kind)}
        if buildings:
            layers["building_fraction"] = building_fraction_grid(buildings, transform, height, width, inside)
        sources = {"tree_canopy_pct": "; ".join(str(p) for p in tiles),
                   "built_pct": "; ".join(str(p) for p in tiles),
                   "road_density": str(args.osm_roads), "distance_green_m": str(args.osm_green),
                   "population_density": f"{args.worldpop} ({args.worldpop_kind})"}
        if args.osm_buildings:
            sources["building_fraction"] = str(args.osm_buildings)
        stats = save_layers(layers, transform, inside, args.output_dir, sources, worldcover_count)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Urban morphology pipeline stopped: {exc}\n")
    for name, summary in stats.items():
        print(f"Saved {args.output_dir / f'{name}_pune_30m.tif'}")
        print(f"  min={summary['min']:.4f}, max={summary['max']:.4f}, mean={summary['mean']:.4f}, nodata={summary['nodata_percent']:.2f}%")
    print(f"WorldCover valid 10 m subpixels: min={worldcover_count[inside].min()}, max={worldcover_count[inside].max()} of 9")
    print(f"QC maps: {args.output_dir / 'morphology_qc_maps.png'}")
    print(f"QC histograms: {args.output_dir / 'morphology_qc_histograms.png'}")
    print(f"QC report: {args.output_dir / 'morphology_qc.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
