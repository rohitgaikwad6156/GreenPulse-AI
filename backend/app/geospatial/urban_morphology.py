"""Real-source urban morphology layers on the exact GreenPulse LST grid.

No demo data, training, or invented Pune measurements are used here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from affine import Affine
from pyproj import Geod, Transformer
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds, transform as window_transform
from rasterio.warp import reproject, transform_bounds
from shapely import distance as geometry_distance, points as geometry_points
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, shape
from shapely.ops import transform as transform_geometry, unary_union
from shapely.strtree import STRtree

from backend.app.geospatial.landsat_lst import OUTPUT_NODATA, TARGET_CRS

WORLDCOVER_CLASSES = {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100}
MOTOR_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
               "residential", "service", "living_street", "motorway_link", "trunk_link",
               "primary_link", "secondary_link", "tertiary_link"}
GREEN_TAGS = {("leisure", "park"), ("leisure", "garden"), ("landuse", "forest"),
              ("landuse", "grass"), ("landuse", "recreation_ground"),
              ("natural", "wood"), ("natural", "grassland")}


def discover_worldcover_tiles(directory: Path) -> list[Path]:
    """Find original ESA WorldCover 2021 v200 map TIFFs; reject absent tiles."""
    if not directory.is_dir():
        raise ValueError(f"WorldCover directory is missing: {directory}")
    paths = sorted(p for p in directory.rglob("*.tif") if p.name.startswith("ESA_WorldCover_10m_2021_v200_") and p.name.endswith("_Map.tif"))
    if not paths:
        raise ValueError(f"No original ESA WorldCover 2021 v200 Map TIFFs in {directory}")
    return paths


def worldcover_fractions(paths: list[Path], transform: Affine, height: int, width: int,
                         inside: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Area fractions of 10 m tree-cover (10) and built-up (50) classes.

    Returns percent [0,100] and valid 10 m subpixel count [0,9]. Categorical
    input is nearest-neighbour warped to an aligned 10 m grid. A 30 m cell
    needs at least five of nine valid subpixels; missing cells remain NaN.
    """
    if not paths or inside.shape != (height, width):
        raise ValueError("WorldCover paths and municipal mask are required")
    tree = np.full((height, width), np.nan, dtype=np.float32)
    built = np.full_like(tree, np.nan)
    valid_count = np.zeros((height, width), dtype=np.uint8)
    transform10 = Affine(10, 0, transform.c, 0, -10, transform.f)
    for start in range(0, height, 64):
        rows = min(64, height - start)
        window = Window(0, start * 3, width * 3, rows * 3)
        mosaic = np.zeros((rows * 3, width * 3), dtype=np.uint8)
        for path in paths:
            with rasterio.open(path) as source:
                if source.count != 1 or source.crs is None or source.dtypes[0] not in ("uint8", "uint16"):
                    raise ValueError(f"Expected georeferenced one-band WorldCover class TIFF: {path}")
                with WarpedVRT(source, crs=TARGET_CRS, transform=transform10, width=width * 3,
                               height=height * 3, src_nodata=0, nodata=0,
                               resampling=Resampling.nearest) as vrt:
                    layer = vrt.read(1, window=window)
                if np.any(~np.isin(layer, list(WORLDCOVER_CLASSES))):
                    raise ValueError(f"Unexpected ESA WorldCover class in {path}")
                take = (mosaic == 0) & (layer != 0)
                mosaic[take] = layer[take]
        blocks = mosaic.reshape(rows, 3, width, 3)
        count = np.count_nonzero(blocks != 0, axis=(1, 3)).astype(np.uint8)
        valid_count[start:start + rows] = count
        good = count >= 5
        for output, code in ((tree, 10), (built, 50)):
            fraction = np.full((rows, width), np.nan, dtype=np.float32)
            hits = np.count_nonzero(blocks == code, axis=(1, 3))
            fraction[good] = (100.0 * hits[good] / count[good]).astype(np.float32)
            output[start:start + rows] = fraction
    tree[~inside] = np.nan
    built[~inside] = np.nan
    valid_count[~inside] = 0
    if not np.isfinite(tree[inside]).any():
        raise ValueError("WorldCover tiles do not provide valid PMC/PCMC coverage")
    return tree, built, valid_count


def _geojson_features(path: Path):
    if not path.is_file():
        raise ValueError(f"OSM GeoJSON is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read OSM GeoJSON: {path}") from exc
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise ValueError(f"OSM GeoJSON must be a FeatureCollection: {path}")
    for feature in document["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
            raise ValueError(f"OSM feature lacks a geometry object in {path}")
        try:
            geometry = shape(feature["geometry"])
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise ValueError(f"Invalid OSM geometry in {path}") from exc
        if geometry.is_empty or not geometry.is_valid or not all(math.isfinite(v) for v in geometry.bounds):
            raise ValueError(f"Invalid OSM geometry in {path}")
        min_x, min_y, max_x, max_y = geometry.bounds
        if not (-180 <= min_x <= max_x <= 180 and -90 <= min_y <= max_y <= 90):
            raise ValueError(f"OSM input must be WGS84 longitude/latitude: {path}")
        yield geometry, feature.get("properties") or {}


def _has_tag(properties: dict, key: str, allowed: set[str]) -> bool:
    values = properties.get(key)
    if isinstance(values, str):
        values = [values]
    return isinstance(values, list) and any(str(value).lower() in allowed for value in values)


def load_osm_geometries(path: Path, kind: str) -> list:
    """Read WGS84 OSM GeoJSON roads, green polygons, or buildings in UTM43N.

    Roads require motorable `highway` tags. Green polygons require selected
    leisure/landuse/natural tags. Buildings require a nonempty building tag.
    Unsupported geometries/tags are skipped. Empty inventories fail closed.
    """
    if kind not in ("roads", "green", "buildings"):
        raise ValueError("kind must be roads, green, or buildings")
    transformer = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    geometries = []
    for geometry, props in _geojson_features(path):
        if kind == "roads":
            if not isinstance(geometry, (LineString, MultiLineString)) or not _has_tag(props, "highway", MOTOR_ROADS):
                continue
        else:
            if not isinstance(geometry, (Polygon, MultiPolygon)):
                continue
            if kind == "green" and not any(_has_tag(props, key, {value}) for key, value in GREEN_TAGS):
                continue
            if kind == "buildings" and not props.get("building"):
                continue
        projected = transform_geometry(transformer.transform, geometry)
        if not projected.is_empty and projected.is_valid:
            geometries.append(projected)
    if not geometries:
        raise ValueError(f"No usable OSM {kind} geometries in {path}; check tags and export completeness")
    return geometries


def _cell_range(bounds: tuple[float, float, float, float], transform: Affine,
                height: int, width: int) -> tuple[range, range]:
    min_x, min_y, max_x, max_y = bounds
    col0 = max(0, math.floor((min_x - transform.c) / 30))
    col1 = min(width - 1, math.floor((max_x - transform.c) / 30))
    row0 = max(0, math.floor((transform.f - max_y) / 30))
    row1 = min(height - 1, math.floor((transform.f - min_y) / 30))
    return range(row0, row1 + 1), range(col0, col1 + 1)


def _cell_polygon(row: int, col: int, transform: Affine) -> Polygon:
    left = transform.c + col * 30
    top = transform.f - row * 30
    return box(left, top - 30, left + 30, top)


def road_density_grid(roads: list, transform: Affine, height: int, width: int,
                      inside: np.ndarray) -> np.ndarray:
    """Clip unique motor-road centreline lengths to cells; return km/km².

    Uses metric EPSG:32643 lengths and 900 m² cell area. Outside municipal
    cells are NaN; zero inside means no mapped motor road, not proof of absence.
    """
    if not roads or inside.shape != (height, width):
        raise ValueError("Road geometries and municipal mask are required")
    result = np.zeros((height, width), dtype=np.float64)
    unique = unary_union(roads)  # remove overlapping/duplicated linework
    lines = [unique] if isinstance(unique, LineString) else list(unique.geoms)
    for line in lines:
        if not isinstance(line, LineString):
            continue
        coords = list(line.coords)
        for first, second in zip(coords[:-1], coords[1:]):
            if first == second:
                continue
            segment = LineString((first, second))
            rows, cols = _cell_range(segment.bounds, transform, height, width)
            # Assign a road exactly on a grid edge to one adjacent cell.
            # Polygon intersection would otherwise count its full length twice.
            if abs(first[0] - second[0]) < 1e-7:
                grid_col = (first[0] - transform.c) / 30
                if abs(grid_col - round(grid_col)) < 1e-7:
                    assigned = math.floor(grid_col)
                    cols = range(assigned, assigned + 1) if 0 <= assigned < width else range(0)
            if abs(first[1] - second[1]) < 1e-7:
                grid_row = (transform.f - first[1]) / 30
                if abs(grid_row - round(grid_row)) < 1e-7:
                    assigned = math.floor(grid_row)
                    rows = range(assigned, assigned + 1) if 0 <= assigned < height else range(0)
            for row in rows:
                for col in cols:
                    if inside[row, col]:
                        result[row, col] += segment.intersection(_cell_polygon(row, col, transform)).length
    output = (result / 900.0 * 1000.0).astype(np.float32)
    output[~inside] = np.nan
    return output


def green_distance_grid(green: list, transform: Affine, height: int, width: int,
                        inside: np.ndarray) -> np.ndarray:
    """Grid-centre Euclidean distance to nearest mapped green polygon, metres."""
    if not green or inside.shape != (height, width):
        raise ValueError("Green polygons and municipal mask are required")
    green_union = unary_union(green)
    parts = list(green_union.geoms) if isinstance(green_union, MultiPolygon) else [green_union]
    tree = STRtree(parts)
    output = np.full((height, width), np.nan, dtype=np.float32)
    indexed_parts = np.asarray(parts, dtype=object)
    for row in range(height):
        cols = np.flatnonzero(inside[row])
        if not cols.size:
            continue
        y = transform.f - (row + 0.5) * 30
        centres = geometry_points(transform.c + (cols + 0.5) * 30, np.full(cols.size, y))
        nearest = indexed_parts[tree.nearest(centres)]
        output[row, cols] = geometry_distance(centres, nearest).astype(np.float32)
    return output


def building_fraction_grid(buildings: list, transform: Affine, height: int, width: int,
                           inside: np.ndarray) -> np.ndarray:
    """Optional mapped building-footprint area / 900 m² in [0,1].

    This is roof/footprint coverage, distinct from WorldCover's broad built
    class. It is meaningful only with a sufficiently complete OSM inventory.
    """
    if not buildings or inside.shape != (height, width):
        raise ValueError("Building polygons and municipal mask are required")
    area = np.zeros((height, width), dtype=np.float64)
    unique = unary_union(buildings)
    polygons = list(unique.geoms) if isinstance(unique, MultiPolygon) else [unique]
    for polygon in polygons:
        rows, cols = _cell_range(polygon.bounds, transform, height, width)
        for row in rows:
            for col in cols:
                if inside[row, col]:
                    area[row, col] += polygon.intersection(_cell_polygon(row, col, transform)).area
    output = np.clip(area / 900.0, 0, 1).astype(np.float32)
    output[~inside] = np.nan
    return output


def worldpop_density_grid(path: Path, transform: Affine, height: int, width: int,
                          inside: np.ndarray, source_kind: str = "counts") -> np.ndarray:
    """Align WorldPop counts or density to people/km² on the 30 m grid.

    Counts (people/source pixel) are first divided by source pixel area. For
    WGS84 WorldPop, area is geodesic by source row. Density inputs are already
    people/km². Bilinear reprojection smooths continuous density only; it does
    not create independent 30 m population observations.
    """
    if source_kind not in ("counts", "density") or inside.shape != (height, width):
        raise ValueError("WorldPop kind must be counts or density, with matching municipal mask")
    if not path.is_file():
        raise ValueError(f"WorldPop raster is missing: {path}")
    destination = np.full((height, width), np.nan, dtype=np.float32)
    west, north = transform.c, transform.f
    east, south = west + width * 30, north - height * 30
    with rasterio.open(path) as source:
        if source.count != 1 or source.crs is None or source.transform.b != 0 or source.transform.d != 0:
            raise ValueError("Expected georeferenced north-up one-band WorldPop GeoTIFF")
        if source_kind == "counts" and source.crs.to_string() not in ("EPSG:4326", TARGET_CRS):
            raise ValueError("WorldPop counts must use EPSG:4326 or EPSG:32643 for area conversion")
        bounds = transform_bounds(TARGET_CRS, source.crs, west, south, east, north, densify_pts=21)
        raw_window = from_bounds(*bounds, transform=source.transform)
        col0 = math.floor(raw_window.col_off)
        row0 = math.floor(raw_window.row_off)
        col1 = math.ceil(raw_window.col_off + raw_window.width)
        row1 = math.ceil(raw_window.row_off + raw_window.height)
        window = Window(col0, row0, col1 - col0, row1 - row0)
        try:
            window = window.intersection(Window(0, 0, source.width, source.height))
        except rasterio.errors.WindowError as exc:
            raise ValueError("WorldPop raster does not overlap PMC/PCMC grid") from exc
        data = source.read(1, window=window, masked=True).astype(np.float64)
        values = np.asarray(data.filled(np.nan), dtype=np.float64)
        if not np.isfinite(values).any():
            raise ValueError("WorldPop raster has no valid pixels over PMC/PCMC")
        if np.any(np.isfinite(values) & (values < 0)):
            raise ValueError("WorldPop population counts/density cannot be negative")
        source_transform = window_transform(window, source.transform)
        if source_kind == "counts":
            if source.crs.to_string() == TARGET_CRS:
                pixel_area_km2 = abs(source_transform.a * source_transform.e) / 1_000_000
                values /= pixel_area_km2
            else:
                geod = Geod(ellps="WGS84")
                left, right = source_transform.c, source_transform.c + source_transform.a
                for row in range(values.shape[0]):
                    top = source_transform.f + row * source_transform.e
                    bottom = top + source_transform.e
                    area_m2, _ = geod.polygon_area_perimeter(
                        [left, right, right, left], [top, top, bottom, bottom])
                    values[row] /= abs(area_m2) / 1_000_000
        reproject(values.astype(np.float32), destination, src_transform=source_transform,
                  src_crs=source.crs, src_nodata=np.nan, dst_transform=transform,
                  dst_crs=TARGET_CRS, dst_nodata=np.nan, resampling=Resampling.bilinear)
    destination[~inside] = np.nan
    if not np.isfinite(destination[inside]).any():
        raise ValueError("WorldPop has no valid coverage inside PMC/PCMC")
    return destination


def summarize_layer(array: np.ndarray, inside: np.ndarray, low: float = 0,
                    high: float = math.inf) -> dict[str, int | float]:
    """Report measured min/max/mean and missing percentage inside PMC/PCMC."""
    if array.shape != inside.shape:
        raise ValueError("Layer and municipal mask shapes differ")
    selected = array[inside]
    valid = selected[np.isfinite(selected)]
    if not valid.size or np.any((valid < low - 1e-5) | (valid > high + 1e-5)):
        raise ValueError("Layer is empty or outside its scientifically valid range")
    return {"municipal_grid_cells": int(selected.size), "valid_grid_cells": int(valid.size),
            "nodata_percent": float(100 * (selected.size - valid.size) / selected.size),
            "min": float(valid.min()), "max": float(valid.max()),
            "mean": float(valid.mean(dtype=np.float64))}


def save_layers(layers: dict[str, np.ndarray], transform: Affine, inside: np.ndarray,
                output_dir: Path, sources: dict[str, str],
                worldcover_valid_count: np.ndarray | None = None) -> dict[str, dict]:
    """Save aligned GeoTIFFs, coverage, source/QC JSON, maps and histograms."""
    expected = {"tree_canopy_pct": (0, 100, "%"), "built_pct": (0, 100, "%"),
                "road_density": (0, math.inf, "km/km2"), "distance_green_m": (0, math.inf, "m"),
                "population_density": (0, math.inf, "people/km2"), "building_fraction": (0, 1, "fraction")}
    if not set(layers).issubset(expected) or not set(expected) - {"building_fraction"} <= set(layers):
        raise ValueError("Required morphology layers missing or unknown")
    stats = {name: summarize_layer(array, inside, *expected[name][:2]) for name, array in layers.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", height=inside.shape[0], width=inside.shape[1], count=1,
                   crs=TARGET_CRS, transform=transform, dtype="float32", nodata=OUTPUT_NODATA,
                   compress="DEFLATE", tiled=True, blockxsize=256, blockysize=256)
    for name, array in layers.items():
        with rasterio.open(output_dir / f"{name}_pune_30m.tif", "w", **profile) as dst:
            dst.write(np.where(np.isfinite(array), array, OUTPUT_NODATA).astype(np.float32), 1)
            dst.update_tags(units=expected[name][2], source=sources.get(name, ""),
                            note="30 m output grid; source resolution and completeness documented in QC JSON")
    if worldcover_valid_count is not None:
        if worldcover_valid_count.shape != inside.shape or np.any(worldcover_valid_count > 9):
            raise ValueError("WorldCover valid subpixel count must be on the target grid in [0,9]")
        count_profile = dict(profile, dtype="uint8", nodata=0)
        with rasterio.open(output_dir / "worldcover_valid_subpixels_pune_30m.tif", "w", **count_profile) as dst:
            dst.write(worldcover_valid_count.astype(np.uint8), 1)
            dst.update_tags(units="valid 10 m subpixels of 9")
    report = {"data_type": "REAL-SOURCE URBAN MORPHOLOGY FEATURES", "crs": TARGET_CRS,
              "pixel_size_m": 30, "worldcover_classes": {"tree_cover": 10, "built_up": 50},
              "source_files": sources, "statistics": stats,
              "caution": "WorldCover tree cover is a canopy proxy; population is not independently resolved at 30 m; OSM coverage may be incomplete"}
    (output_dir / "morphology_qc.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    names = list(layers)
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for ax, name in zip(axes.flat, names):
        shown = np.ma.masked_invalid(layers[name])
        image = ax.imshow(shown, cmap="YlGn" if name == "tree_canopy_pct" else "viridis", interpolation="nearest")
        ax.set(title=name.replace("_", " "), xlabel="30 m column", ylabel="30 m row")
        fig.colorbar(image, ax=ax, label=expected[name][2])
    for ax in list(axes.flat)[len(names):]:
        ax.axis("off")
    fig.savefig(output_dir / "morphology_qc_maps.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(14, 7), constrained_layout=True)
    for ax, name in zip(axes.flat, names):
        values = layers[name][inside & np.isfinite(layers[name])]
        ax.hist(values, bins=35, color="#427b64", edgecolor="white")
        ax.set(title=name.replace("_", " "), xlabel=expected[name][2], ylabel="30 m grid cells")
    for ax in list(axes.flat)[len(names):]:
        ax.axis("off")
    fig.savefig(output_dir / "morphology_qc_histograms.png", dpi=150)
    plt.close(fig)
    return stats
